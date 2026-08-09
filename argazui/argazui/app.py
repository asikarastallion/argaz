"""ArgazUI backend — FastAPI + WebSocket.

Sadece 127.0.0.1 uzerinde dinler (tek kullanicilik lokal arac).
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
from html import escape as html_escape
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import paths
from . import procedures as procs
from . import runs as runlib
from .i18n import t, set_language, get_language, LANGUAGES
from .mavlink_link import MavlinkLink, substitute
from .procrunner import ProcedureRunner, probe_capabilities
from .runs import RunRecorder
from .versions import argazui_build, pin_static_digest
from .session import TerminalSession, build_launch_commands

app = FastAPI(title="ArgazUI")


# --------------------------------------------------------------------------- yayin
SIM = "sim"        # simulasyonun (Gazebo/SITL/MAVProxy) calistigi terminal
SHELL = "shell"    # gorev scriptleri ve serbest kabuk komutlari icin terminal


class Hub:
    """pty ve MAVLink thread'lerinden gelen mesajlari WebSocket'lere dagitir.

    Iki ayri terminal akisi ("sim" ve "shell") tasinir; her birinin kendi
    gecmisi tutulur ki yeni baglanan tarayici o ana kadarki ciktiyi gorsun.
    """

    MAX_BACKLOG = 256 * 1024

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.backlog: dict[str, list[bytes]] = {SIM: [], SHELL: []}
        self.backlog_bytes: dict[str, int] = {SIM: 0, SHELL: 0}
        # Kosu kaydi varken terminal ciktisi ayni anda console.log'a da akar.
        # Backlog gecicidir (256 KB'lik halka tampon); kosu dosyasi degil.
        self.console_sink: Optional[Callable[[str, bytes], None]] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    # -- thread'lerden cagrilir --
    def push_output(self, stream: str, data: bytes) -> None:
        if self.console_sink is not None:
            try:
                self.console_sink(stream, data)
            except Exception:
                pass
        buf = self.backlog[stream]
        buf.append(data)
        self.backlog_bytes[stream] += len(data)
        while self.backlog_bytes[stream] > self.MAX_BACKLOG and len(buf) > 1:
            self.backlog_bytes[stream] -= len(buf.pop(0))
        self._send({"type": "out", "stream": stream,
                    "data": base64.b64encode(data).decode()})

    def writer(self, stream: str):
        """Belirli bir akisa yazan callback uretir (TerminalSession icin)."""
        return lambda data: self.push_output(stream, data)

    def push_log(self, text: str, stream: str = SIM) -> None:
        """ArgazUI'nin kendi mesaji — terminale renkli satir olarak yazilir."""
        self.push_output(stream, f"\r\n\x1b[36m[ArgazUI]\x1b[0m {text}\r\n".encode())

    def push_json(self, payload: dict) -> None:
        self._send(payload)

    def _send(self, payload: dict) -> None:
        if self.loop is None:
            return
        try:
            self.loop.call_soon_threadsafe(asyncio.ensure_future, self._broadcast(payload))
        except RuntimeError:
            pass

    async def _broadcast(self, payload: dict) -> None:
        dead = []
        text = json.dumps(payload)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


hub = Hub()


# --------------------------------------------------------------------------- durum
class Manager:
    """Iki terminal oturumu ve tek MAVLink baglantisi yonetir.

    NEDEN IKI TERMINAL?
    Simulasyon (ros2 launch / sim_vehicle.py) kabugun on planini isgal eder.
    sim_vehicle.py yolunda MAVProxy'nin etkilesimli kalabilmesi icin bu
    GEREKLIDIR (on planda olmayan surec stdin okuyamaz, SIGTTIN ile durur).
    Ama o sirada kabuk mesgul oldugundan gorev scripti calistirmak ya da elle
    komut yazmak mumkun olmaz. Bu yuzden ikinci, bos bir kabuk daha aciyoruz.
    """

    def __init__(self) -> None:
        self.sim = TerminalSession(on_output=hub.writer(SIM))
        self.shell = TerminalSession(on_output=hub.writer(SHELL))
        self.mav = MavlinkLink(port=paths.UI_MAVLINK_PORT, on_log=hub.push_log,
                               on_event=self._record_event,
                               mirror_port=paths.PLOTJUGGLER_PORT)
        self.active_model: Optional[dict] = None
        self.lock = threading.Lock()
        # Prosedur motoru durumu. Yetenekler araçtan OKUNUR (models.json'dan
        # degil) ve model degisince sifirlanir — bkz. procedures.py.
        self.caps: Optional[dict] = None
        self.runner: Optional[ProcedureRunner] = None
        self.proc_thread: Optional[threading.Thread] = None
        self.last_result: Optional[dict] = None
        # Aktif kosu kaydi (runs.py). START ile acilir, STOP ile kapanir.
        self.run: Optional[RunRecorder] = None
        hub.console_sink = self._record_console

    def session(self, stream: str) -> TerminalSession:
        return self.sim if stream == SIM else self.shell

    # -- kosu kaydi --
    def _record_console(self, stream: str, data: bytes) -> None:
        """Terminal ciktisini kosunun console.log'una tee eder.

        Yalnizca SIMULASYON akisi kaydedilir. Komut kabugu kullanicinin kendi
        calisma alani; oraya yazdiklari ucusun kaydina ait degil.
        """
        run = self.run
        if run is not None and stream == SIM:
            run.console(data)

    def _record_event(self, event: dict) -> None:
        run = self.run
        if run is not None:
            run.event(event)

    # -- kayit defteri --
    def registry(self) -> dict:
        if not paths.MODELS_JSON.exists():
            from .scan_models import build_registry
            reg, _ = build_registry()
            paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            paths.MODELS_JSON.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
        registry = json.loads(paths.MODELS_JSON.read_text())
        return {**registry, "models": [self._with_real_image(m)
                                       for m in registry.get("models", [])]}

    @staticmethod
    def _with_real_image(model: dict) -> dict:
        """Drop an `image` the interface would only fail to load.

        `static/models/` is fetched with `python3 -m argazui.fetch_images` and
        is gitignored, so a fresh clone has none of it while models.json still
        names every file. The page then requested eleven pictures that were not
        there and the browser logged eleven 404s — on a page whose first
        promise is a clean console. The interface already has a "no image for
        this model" state; this is how it gets used.
        """
        image = model.get("image")
        if not image:
            return model
        name = str(image).split("/static/", 1)[-1]
        if (paths.STATIC_DIR / name).is_file():
            return model
        return {**model, "image": None}

    def buttons(self) -> dict:
        return json.loads(paths.BUTTONS_JSON.read_text())

    def find_model(self, model_id: str) -> Optional[dict]:
        for m in self.registry().get("models", []):
            if m.get("id") == model_id:
                return m
        return None

    def scripts(self) -> list[dict]:
        paths.SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        out = []
        for p in sorted(paths.SCRIPTS_DIR.glob("*.py")):
            if p.name.startswith("_"):
                continue
            first_doc = ""
            try:
                for line in p.read_text(errors="replace").splitlines()[:20]:
                    s = line.strip()
                    if s.startswith("#") and not s.startswith("#!"):
                        first_doc = s.lstrip("# ").strip()
                        break
                    if s.startswith(('"""', "'''")):
                        first_doc = s.strip("\"' ")
                        break
            except OSError:
                pass
            out.append({"name": p.name, "description": first_doc})
        return out

    def ensure_terminal(self) -> None:
        if not self.sim.is_alive():
            self.sim.start()
        if not self.shell.is_alive():
            self.shell.start()

    # -- eylemler --
    def start_model(self, model_id: str) -> dict:
        with self.lock:
            model = self.find_model(model_id)
            if model is None:
                return {"ok": False, "text": t("not_in_registry", id=model_id)}

            self.ensure_terminal()
            # `self.run` is also checked: a launch that failed before the
            # vehicle appeared still left a recorder open, and it has to be
            # closed rather than dropped — otherwise its directory stays
            # "incomplete" forever and its files are never flushed.
            if self.active_model is not None or self.run is not None:
                if self.active_model is not None:
                    hub.push_log(t("closing_previous", id=self.active_model["id"]))
                self._stop_locked()

            hub.push_log(t("starting", name=model["name"], method=model["method"]))
            commands = build_launch_commands(model)

            # Kayit, ilk komut yazilmadan ONCE acilir: acilis ciktisi da
            # (Gazebo/SITL hatalari dahil) console.log'a girsin.
            try:
                self.run = RunRecorder(model=model, root=paths.RUNS_DIR,
                                       launch_commands=commands,
                                       work_dir=paths.RUN_DIR / model["id"],
                                       on_log=hub.push_log)
                hub.push_log(t("run_started", id=self.run.run_id))
            except OSError as exc:
                # Artefakt toplayamamak ucusu engellememeli; ama sessiz de
                # kalmamali, yoksa kullanici run dizinini bosuna arar.
                self.run = None
                hub.push_log(t("run_failed", err=exc))

            for line in commands:
                self.sim.run_line(line)

            self.active_model = model
            self.mav.start(vehicle=model.get("vehicle"))
            threading.Thread(target=self._announce_link, args=(model,), daemon=True).start()
            return {"ok": True, "text": t("starting_short", name=model["name"])}

    def _announce_link(self, model: dict) -> None:
        hub.push_log(t("waiting_mavlink", port=paths.UI_MAVLINK_PORT))
        if self.mav.wait_ready(timeout=180):
            hub.push_log(t("mavlink_ready", sysid=self.mav.state.sysid,
                           mode=self.mav.state.mode))
        else:
            hub.push_log(t("mavlink_failed"))

    def _stop_locked(self) -> dict:
        if self.runner:
            self.runner.cancel()
        self.caps = None            # yetenekler araca ait; arac gidince gecersiz
        had_sim = self.sim.is_alive() and self.active_model is not None
        self.mav.stop()
        if self.sim.is_alive():
            self.sim.stop_children(log=hub.push_log)
        if had_sim:
            # Gazebo ve MAVProxy kapanirken iki tanidik hata basiyor. Ikisi de
            # zararsiz; ama terminal gercek bir bash oturumu oldugu icin
            # ciktilarini filtrelemiyoruz — bunun yerine ne olduklarini
            # soyluyoruz. Ayrintili gerekce icin i18n "stop_noise".
            hub.push_log(t("stop_noise"))
        # Arac kapaninca ona baglanan gorev scriptlerini de birakmayalim
        if self.shell.is_alive():
            self.shell.stop_children(
                log=lambda s: hub.push_log(t("shell_prefix", msg=s), stream=SHELL))
        self.active_model = None

        # Artefaktlar SITL oldukten SONRA toplanir: dataflash log ancak surec
        # kapaninca kapatilir, once kopyalanirsa yarim kalir.
        run, self.run = self.run, None
        if run is not None:
            result = run.finish()
            hub.push_log(t("run_saved", id=run.run_id, status=result.get("status"),
                           path=str(run.dir)))
        return {"ok": True, "text": t("stopped")}

    def stop(self) -> dict:
        with self.lock:
            hub.push_log(t("stopping"))
            return self._stop_locked()

    def run_command(self, commands: list[str], values: dict) -> dict:
        results = []
        for raw in commands:
            try:
                cmd = substitute(raw, values)
            except KeyError as exc:
                results.append({"ok": False, "text": t("missing_input", name=exc)})
                break
            res = self.mav.send(cmd)
            if res.get("unsupported") and self.sim.is_alive():
                # MAVLink yorumlayicisinin bilmedigi komutu simulasyon
                # terminaline dusur (sim_vehicle.py yolunda MAVProxy
                # etkilesimlidir ve stdin'den komut alir).
                self.sim.run_line(cmd)
                res = {"ok": True, "text": t("sent_to_terminal", cmd=cmd)}
            hub.push_log(f"{cmd}  ->  {res['text']}")
            results.append(res)
            if not res.get("ok"):
                break
        ok = all(r.get("ok") for r in results) if results else False
        return {"ok": ok, "results": results}

    # -- prosedurler --
    def capabilities(self, refresh: bool = False) -> Optional[dict]:
        """Aracin kendi konfigurasyonundan yeteneklerini okur (bir kez, onbellekli).

        models.json'a GUVENMIYORUZ: SkyCat TVBS orada duz "QuadPlane" yaziyor
        ama param dosyasi Q_TAILSIT_ENABLE=1 veriyor — yani tailsitter. Dogru
        prosedur ancak aracin kendi parametreleri okunarak secilebilir.
        """
        if not self.mav.state.connected:
            return None
        if self.caps is None or refresh:
            vehicle = (self.active_model or {}).get("vehicle")
            self.caps = probe_capabilities(self.mav, vehicle=vehicle)
            shown = ", ".join(f"{k}={v}" for k, v in self.caps.items() if k != "raw")
            hub.push_log(t("proc_caps", caps=shown))
        return self.caps

    def procedure_overview(self) -> dict:
        """UI icin: hangi prosedur secildi, hangi alternatifler var."""
        lang = get_language()
        caps = self.capabilities()
        out = {"capabilities": caps, "roles": {}, "last_result": self.last_result,
               "running": bool(self.proc_thread and self.proc_thread.is_alive())}
        if caps is None:
            return out
        for role in procs.ROLES:
            try:
                chosen = procs.select(role, caps, self.active_model)
                options = procs.candidates(role, caps)
            except procs.ProcedureError as exc:
                out["roles"][role] = {"error": str(exc)}
                continue
            out["roles"][role] = {
                "selected": chosen.id if chosen else None,
                "options": [p.as_dict(lang) for p in options],
            }
        return out

    def resolve_procedure(self, procedure_id: Optional[str], role: Optional[str]):
        """Bir istegi somut bir prosedure cevirir; hatayi metin olarak dondurur."""
        if procedure_id:
            proc = procs.get(procedure_id)
            if proc is None:
                return None, t("proc_not_found", id=procedure_id)
            return proc, ""
        caps = self.capabilities()
        if caps is None:
            return None, t("proc_no_vehicle")
        proc = procs.select(role or "takeoff", caps, self.active_model)
        if proc is None:
            shown = ", ".join(f"{k}={v}" for k, v in caps.items() if k != "raw")
            return None, t("proc_none_for_vehicle", role=role, caps=shown)
        return proc, ""

    def run_procedure(self, procedure_id: Optional[str], role: Optional[str],
                      values: Optional[dict]) -> dict:
        """Prosedur calistirmayi baslatir; ilerleme WebSocket'ten akar."""
        if self.proc_thread and self.proc_thread.is_alive():
            return {"ok": False, "text": t("proc_busy")}
        if not self.mav.state.connected:
            return {"ok": False, "text": t("proc_no_vehicle")}
        try:
            proc, err = self.resolve_procedure(procedure_id, role)
        except procs.ProcedureError as exc:
            return {"ok": False, "text": str(exc)}
        if proc is None:
            return {"ok": False, "text": err}

        lang = get_language()
        hub.push_log(t("proc_selected", role=proc.role, id=proc.id,
                       name=proc.label(lang)))
        self.runner = ProcedureRunner(self.mav, on_event=self._on_proc_event, lang=lang)

        def _go() -> None:
            hub.push_log(t("proc_running", name=proc.label(lang)))
            result = self.runner.run(proc, values or {})
            self.last_result = result
            # Ayni YAML hem butonu hem testi suruyor; kosu dizinine giren de
            # bu dosyanin kendisi oluyor (bkz. runs.RunRecorder.add_procedure).
            run = self.run
            if run is not None:
                run.add_procedure(proc, result, values=values or {})
            hub.push_log(result["text"])

        self.proc_thread = threading.Thread(target=_go, name="procedure", daemon=True)
        self.proc_thread.start()
        return {"ok": True, "started": proc.id, "name": proc.label(lang),
                "text": t("proc_running", name=proc.label(lang))}

    def _on_proc_event(self, event: dict) -> None:
        """Runner olaylarini hem WebSocket'e hem terminale yansitir."""
        hub.push_json(event)
        kind = event.get("event")
        if kind == "step":
            step = event.get("step") or {}
            if step.get("status") in ("passed", "failed", "skipped"):
                mark = {"passed": "OK", "failed": "FAIL", "skipped": "skip"}[step["status"]]
                detail = f" — {step['text']}" if step.get("text") else ""
                hub.push_log(f"  [{mark}] {step.get('label')}{detail}")
        elif kind == "expect":
            exp = event.get("expect") or {}
            mark = "OK" if exp.get("passed") else "FAIL"
            hub.push_log(f"  expect [{mark}] {exp.get('label')} — {exp.get('text')}")
        elif kind == "override":
            # A declared parameter change is announced with its reason, so the
            # terminal shows the same justification the run directory records.
            ovr = event.get("override") or {}
            hub.push_log(t("proc_override_applied", name=ovr.get("param"),
                           value=ovr.get("set_to"), previous=ovr.get("restore_to"),
                           reason=ovr.get("reason")))
        elif kind == "restore_failed":
            ovr = event.get("override") or {}
            hub.push_log(t("proc_restore_failed", name=ovr.get("param"),
                           value=ovr.get("restore_to")))

    def cancel_procedure(self) -> dict:
        if self.runner and self.proc_thread and self.proc_thread.is_alive():
            self.runner.cancel()
            return {"ok": True, "text": t("proc_cancelled")}
        return {"ok": False, "text": t("proc_busy")}

    def run_script(self, name: str) -> dict:
        target = (paths.SCRIPTS_DIR / name).resolve()
        if target.parent != paths.SCRIPTS_DIR.resolve() or not target.is_file():
            return {"ok": False, "text": t("bad_script", name=name)}
        self.ensure_terminal()
        # Scriptler KOMUT terminalinde calisir; simulasyon terminali
        # ros2 launch / sim_vehicle.py tarafindan mesguldur.
        hub.push_log(t("running_script", name=target.name,
                       port=paths.SCRIPT_MAVLINK_PORT), stream=SHELL)
        self.shell.run_line(f"python3 {json.dumps(str(target))}")
        return {"ok": True, "text": t("script_started", name=target.name)}

    def status(self) -> dict:
        return {
            "terminal_alive": self.sim.is_alive() and self.shell.is_alive(),
            "active_model": self.active_model["id"] if self.active_model else None,
            "active_model_name": self.active_model["name"] if self.active_model else None,
            "vehicle_class": self.active_model["vehicle_class"] if self.active_model else None,
            "has_ros2": bool(self.active_model.get("has_ros2")) if self.active_model else False,
            "vehicle": self.mav.state.as_dict(),
            # Whether the MAVLink worker exists at all, as opposed to existing
            # but hearing nothing. The interface distinguishes the two so a
            # blank status bar always has a stated reason.
            "link_running": self.mav.is_running(),
            "procedure_running": bool(self.proc_thread and self.proc_thread.is_alive()),
            "script_port": paths.SCRIPT_MAVLINK_PORT,
            "ui_port": paths.UI_MAVLINK_PORT,
            # Where to point a plotting tool, and whether anything is actually
            # going out of it. The message count is there so the panel can
            # show the stream working rather than assert that it does.
            "plotjuggler": self.mav.mirror.info(),
            "lang": get_language(),
        }


mgr = Manager()


# --------------------------------------------------------------------------- API
class StartReq(BaseModel):
    model_id: str


class CommandReq(BaseModel):
    commands: list[str]
    values: dict = {}


class ScriptReq(BaseModel):
    name: str


class InputReq(BaseModel):
    data: str


class LangReq(BaseModel):
    lang: str


@app.post("/api/lang")
def api_lang(req: LangReq):
    """Arayuz dilini degistirir.

    Backend'in terminale bastigi mesajlar da bu dile gore uretilir, boylece
    arayuz ve terminal ciktisi ayni dilde kalir.
    """
    return {"ok": True, "lang": set_language(req.lang), "available": list(LANGUAGES)}


@app.get("/api/models")
def api_models():
    return mgr.registry()


@app.get("/api/buttons")
def api_buttons():
    return mgr.buttons()


@app.get("/api/scripts")
def api_scripts():
    return {"scripts": mgr.scripts(), "dir": str(paths.SCRIPTS_DIR)}


@app.get("/api/status")
def api_status():
    return mgr.status()


@app.post("/api/start")
def api_start(req: StartReq):
    return JSONResponse(mgr.start_model(req.model_id))


@app.post("/api/stop")
def api_stop():
    return JSONResponse(mgr.stop())


@app.post("/api/command")
def api_command(req: CommandReq):
    return JSONResponse(mgr.run_command(req.commands, req.values))


@app.post("/api/script")
def api_script(req: ScriptReq):
    return JSONResponse(mgr.run_script(req.name))


class ProcedureReq(BaseModel):
    procedure_id: Optional[str] = None
    role: Optional[str] = None
    values: dict = {}


@app.get("/api/procedures")
def api_procedures():
    """Which procedures fit the connected vehicle, and which one is selected."""
    return JSONResponse(mgr.procedure_overview())


@app.post("/api/procedure")
def api_procedure(req: ProcedureReq):
    return JSONResponse(mgr.run_procedure(req.procedure_id, req.role, req.values))


@app.post("/api/procedure/cancel")
def api_procedure_cancel():
    return JSONResponse(mgr.cancel_procedure())


# --------------------------------------------------------------------------- runs
# Every START..STOP leaves a directory under `runs/`. These endpoints only
# read it — a run is written by the Manager and by runs.py, never by a browser.
@app.get("/api/runs")
def api_runs():
    # Read the recorder once: STOP may clear it on another thread between a
    # truth test and an attribute access.
    active = mgr.run
    return {"runs": runlib.list_runs(), "root": str(paths.RUNS_DIR),
            "active": active.run_id if active is not None else None}


@app.get("/api/runs/{run_id}")
def api_run(run_id: str):
    directory = runlib.run_dir(run_id)
    if directory is None:
        return JSONResponse({"ok": False, "text": t("run_unknown", id=run_id)},
                            status_code=404)
    detail = runlib.describe_run(directory)
    report = directory / "report.json"
    if report.is_file():
        try:
            detail["report"] = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            detail["report"] = None
    detail["files"] = sorted(
        str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())
    return detail


@app.get("/api/runs/{run_id}/report")
def api_run_report(run_id: str):
    path = runlib.run_file(run_id, "report.md")
    if path is None:
        return PlainTextResponse(t("run_no_report", id=run_id), status_code=404)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.post("/api/runs/{run_id}/report")
def api_run_report_rebuild(run_id: str):
    return JSONResponse(runlib.regenerate_report(run_id))


@app.get("/api/runs/{run_id}/file/{relative:path}")
def api_run_file(run_id: str, relative: str):
    path = runlib.run_file(run_id, relative)
    if path is None:
        return JSONResponse({"ok": False, "text": t("run_no_file", name=relative)},
                            status_code=404)
    # The dataflash log is the one file people actually save; everything else
    # is small enough that the browser can decide what to do with it.
    disposition = "attachment" if path.suffix.upper() == ".BIN" else "inline"
    return FileResponse(path, filename=path.name,
                        headers={"Content-Disposition":
                                 f'{disposition}; filename="{path.name}"'})


@app.post("/api/rescan")
def api_rescan():
    from .scan_models import build_registry, merge_registry
    reg, skipped = build_registry()
    if paths.MODELS_JSON.exists():
        reg = merge_registry(reg, json.loads(paths.MODELS_JSON.read_text()))
    paths.MODELS_JSON.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    hub.push_log(t("registry_rescanned", count=len(reg["models"]), skipped=len(skipped)))
    return {"ok": True, "count": len(reg["models"])}


# --------------------------------------------------------------------------- WS
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    mgr.ensure_terminal()
    try:
        # Yeni baglanan istemciye o ana kadarki terminal ciktisini gonder
        for stream in (SIM, SHELL):
            if hub.backlog[stream]:
                await ws.send_text(json.dumps({
                    "type": "out", "stream": stream,
                    "data": base64.b64encode(b"".join(hub.backlog[stream])).decode(),
                }))
        await ws.send_text(json.dumps({"type": "status", "status": mgr.status()}))
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            stream = msg.get("stream", SIM)
            if stream not in (SIM, SHELL):
                continue
            if kind == "in":
                mgr.session(stream).write(msg.get("data", ""))
            elif kind == "resize":
                mgr.session(stream).resize(int(msg.get("rows", 30)),
                                           int(msg.get("cols", 110)))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.clients.discard(ws)


async def _status_pump():
    while True:
        await asyncio.sleep(1.0)
        if hub.clients:
            hub.push_json({"type": "status", "status": mgr.status()})


@app.on_event("startup")
async def _startup():
    # Pin the interface-file digest NOW. Computing it lazily on the first
    # /api/version call was wrong: by then a file may already have been
    # edited, so boot and current would agree and the drift check would be
    # silent in exactly the case it exists for.
    pin_static_digest()
    hub.bind_loop(asyncio.get_running_loop())
    mgr.ensure_terminal()
    asyncio.create_task(_status_pump())


@app.on_event("shutdown")
async def _shutdown():
    # Ctrl+C ile kapatilan bir sunucu da kosusunu tamamlamali; aksi halde
    # gercek bir ucusun artefaktlari yarim kalirdi.
    if mgr.active_model is not None or mgr.run is not None:
        mgr.stop()
    mgr.mav.stop()
    mgr.sim.close()
    mgr.shell.close()


# --------------------------------------------------------------------------- statik
@app.get("/api/version")
def api_version():
    """Which ArgazUI is answering, and since when. See versions.argazui_build."""
    return argazui_build()


@app.get("/")
def index():
    """Serves the page with THIS server's build identity stamped into it.

    The static files come off disk, so a server left running from an older
    checkout would otherwise hand the browser a newer interface with no way to
    notice. The stamp is what lets the page compare what it was served with
    against what /api/version reports and tell the user plainly.
    """
    html = (paths.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    build = argazui_build()
    stamp = (f'<meta name="argazui-build" content="{html_escape(build["build_id"])}">\n'
             f'<meta name="argazui-served-by" '
             f'content="{html_escape(build["started_utc"])}">\n')
    html = html.replace("</head>", stamp + "</head>", 1)
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")
