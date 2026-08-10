"""ArgazUI backend — FastAPI + WebSocket.

Sadece 127.0.0.1 uzerinde dinler (tek kullanicilik lokal arac).
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from html import escape as html_escape
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis as analysislib
from . import campaign as campaignlib
from . import coverage as coveragelib
from . import docs
from . import evidence as evidencelib
from . import experiments as experimentlib
from . import failures as failurelib
from . import faults as faultlib
from . import limitations as limitslib
from . import metrics as metricslib
from . import paths
from . import procedures as procs
from . import regression
from . import runs as runlib
from . import trace as tracelib
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
        # Repeatability campaign state (v1.4). A campaign owns START and STOP
        # for as long as it runs, which is why it is tracked here beside them
        # rather than in a module of its own.
        self.campaign: Optional[campaignlib.CampaignRunner] = None
        self.campaign_thread: Optional[threading.Thread] = None
        self.last_campaign: Optional[str] = None
        # Experiment state (v1.6). An experiment owns START and STOP for even
        # longer than a campaign does — it is several campaigns in sequence —
        # so it is tracked beside them for the same reason.
        self.experiment: Optional[experimentlib.ExperimentRunner] = None
        self.experiment_thread: Optional[threading.Thread] = None
        self.last_experiment: Optional[str] = None
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
    def start_model(self, model_id: str,
                    campaign: Optional[dict] = None,
                    experiment: Optional[dict] = None) -> dict:
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
                                       on_log=hub.push_log,
                                       campaign=campaign,
                                       experiment=experiment)
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
        out = {"capabilities": caps, "roles": {}, "scenarios": [],
               "last_result": self.last_result,
               "running": bool(self.proc_thread and self.proc_thread.is_alive())}
        if caps is None:
            return out
        # Only takeoff and land are auto-selected. A scenario injects a fault,
        # and a fault must never start because a capability heuristic thought
        # it applied — see procedures.scenarios().
        for role in procs.AUTO_ROLES:
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
        try:
            out["scenarios"] = [p.as_dict(lang) for p in procs.scenarios(caps)]
        except procs.ProcedureError as exc:
            out["scenarios_error"] = str(exc)
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
        self.proc_thread = threading.Thread(
            target=self.execute_procedure, args=(proc, values or {}),
            name="procedure", daemon=True)
        self.proc_thread.start()
        return {"ok": True, "started": proc.id, "name": proc.label(lang),
                "text": t("proc_running", name=proc.label(lang))}

    def execute_procedure(self, proc, values: dict) -> dict:
        """Runs a procedure on the CALLING thread and records it.

        Split out of `run_procedure` so a campaign can drive it in sequence
        without a second implementation. The browser path still gets a thread;
        what both share is this body, for the same reason the button and the
        regression test share `ProcedureRunner` — a second copy would drift.
        """
        lang = get_language()
        hub.push_log(t("proc_selected", role=proc.role, id=proc.id,
                       name=proc.label(lang)))
        self.runner = ProcedureRunner(self.mav, on_event=self._on_proc_event, lang=lang)
        hub.push_log(t("proc_running", name=proc.label(lang)))
        result = self.runner.run(proc, values or {})
        self.last_result = result
        # Ayni YAML hem butonu hem testi suruyor; kosu dizinine giren de
        # bu dosyanin kendisi oluyor (bkz. runs.RunRecorder.add_procedure).
        run = self.run
        if run is not None:
            run.add_procedure(proc, result, values=values or {})
        hub.push_log(result["text"])
        return result

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
        elif kind == "fault":
            # An injected fault is announced in the terminal with its mechanism,
            # so the operator watching the console sees the same declaration the
            # run directory records — never a silent degradation.
            fault = event.get("fault") or {}
            if event.get("state") == "injected":
                hub.push_log(t("fault_injected", label=fault.get("label"),
                               target=fault.get("target"),
                               mechanism=fault.get("mechanism") or "—"))
            elif event.get("state") == "cleared":
                hub.push_log(t("fault_cleared", label=fault.get("label"),
                               target=fault.get("target")))
        elif kind == "fault_done":
            fault = event.get("fault") or {}
            hub.push_log(f"  fault [{'OK' if fault.get('passed') else 'FAIL'}] "
                         f"{fault.get('id')} — {fault.get('text')}")
        elif kind in ("fault_expect", "fault_recovery"):
            exp = event.get("expect") or {}
            mark = "OK" if exp.get("passed") else "FAIL"
            hub.push_log(f"  {kind.split('_')[1]} [{mark}] {exp.get('label')} "
                         f"— {exp.get('text')}")

    # -- repeatability campaigns ------------------------------------------
    # A campaign is N ordinary runs of one procedure on one model, linked by a
    # campaign id. It owns START and STOP while it runs, because "each run gets
    # independent evidence" means a real launch and a real shutdown per
    # iteration — not one session with the procedure sent five times.
    CAMPAIGN_MAX_RUNS = 50
    CAMPAIGN_READY_TIMEOUT = 300.0
    CAMPAIGN_PREARM_TIMEOUT = 240.0

    def start_campaign(self, model_id: str, procedure_id: str, runs: int,
                       values: Optional[dict] = None, note: str = "") -> dict:
        if self.campaign_thread and self.campaign_thread.is_alive():
            return {"ok": False, "text": t("campaign_busy")}
        if self.find_model(model_id) is None:
            return {"ok": False, "text": t("campaign_no_model", id=model_id)}
        if procs.get(procedure_id) is None:
            return {"ok": False, "text": t("proc_not_found", id=procedure_id)}
        if not 2 <= int(runs) <= self.CAMPAIGN_MAX_RUNS:
            return {"ok": False,
                    "text": t("campaign_bad_runs", max=self.CAMPAIGN_MAX_RUNS)}

        definition = campaignlib.Definition(
            id=campaignlib.campaign_id(model_id, procedure_id),
            model_id=model_id, procedure_id=procedure_id, runs=int(runs),
            values=dict(values or {}), note=note)
        self.campaign = campaignlib.CampaignRunner(
            definition, launch=lambda index: _CampaignIteration(self, definition, index),
            on_progress=self._on_campaign_event)
        self.campaign_thread = threading.Thread(
            target=self._campaign_loop, args=(definition,),
            name=f"campaign-{definition.id}", daemon=True)
        self.campaign_thread.start()
        hub.push_log(t("campaign_started", id=definition.id, model=model_id,
                       procedure=procedure_id, runs=definition.runs))
        return {"ok": True, "campaign": definition.as_dict(),
                "text": t("campaign_started", id=definition.id, model=model_id,
                          procedure=procedure_id, runs=definition.runs)}

    def _campaign_loop(self, definition: campaignlib.Definition) -> None:
        runner = self.campaign
        try:
            runner.run()
        finally:
            # The document is written whether the campaign finished, failed or
            # was cancelled. A campaign that stopped after three of five is a
            # result about three runs, and it belongs on disk.
            document = campaignlib.aggregate(definition.id, paths.RUNS_DIR,
                                             definition=definition)
            as_json, _ = campaignlib.write(definition.id, document, paths.RUNS_DIR)
            self.last_campaign = definition.id
            counts = document["counts"]
            hub.push_log(t("campaign_finished", id=definition.id,
                           passed=counts["passed"], failed=counts["failed"],
                           flaky=counts["flaky"], total=document["runs_recorded"],
                           path=str(as_json.parent)))
            hub.push_json({"type": "campaign", "event": "written",
                           "campaign": definition.id, "document": document})

    def _on_campaign_event(self, event: dict) -> None:
        hub.push_json(event)
        kind = event.get("event")
        if kind == "iteration_start":
            hub.push_log(t("campaign_iteration", id=event["campaign"],
                           index=event["index"], total=event["of"]))
        elif kind == "iteration_done":
            row = event.get("row") or {}
            failure = row.get("failure") or {}
            # An iteration that never started is announced rather than left to
            # be discovered in the summary: it is a fact about repeatability,
            # and the operator watching the terminal is the one who can act on
            # it while the campaign is still running.
            if failure.get("code") == "iteration-launch-failed":
                hub.push_log(t("campaign_launch_failed", id=event["campaign"],
                               index=row.get("index"),
                               err=row.get("text") or failure.get("detail", "")))

    def cancel_campaign(self) -> dict:
        if not (self.campaign_thread and self.campaign_thread.is_alive()):
            return {"ok": False, "text": t("campaign_none")}
        self.campaign.cancel()
        done = len(self.campaign.iterations)
        return {"ok": True, "text": t("campaign_cancelled",
                                      id=self.campaign.definition.id, done=done)}

    def campaign_status(self) -> dict:
        runner = self.campaign
        running = bool(self.campaign_thread and self.campaign_thread.is_alive())
        if runner is None:
            return {"running": False, "last": self.last_campaign}
        return {"running": running, "last": self.last_campaign,
                "definition": runner.definition.as_dict(),
                "done": len(runner.iterations),
                "iterations": runner.iterations}

    # -- experiments -------------------------------------------------------
    # An experiment is a controlled set of campaigns: one model, one or more
    # arms, each arm a procedure flown N times. Nothing here executes anything
    # — `ExperimentRunner` hands each arm to `CampaignRunner`, which hands each
    # iteration to the same START/STOP path the button uses.
    def start_experiment(self, experiment_id: str) -> dict:
        if self.experiment_thread and self.experiment_thread.is_alive():
            return {"ok": False, "text": t("experiment_busy")}
        if self.campaign_thread and self.campaign_thread.is_alive():
            return {"ok": False, "text": t("campaign_busy")}
        experiment = experimentlib.get(experiment_id)
        if experiment is None:
            return {"ok": False, "text": t("experiment_unknown", id=experiment_id)}
        # Checked here rather than at load time: a definition stays readable on
        # a checkout whose registry has not been scanned yet, and what cannot
        # be allowed is flying one against an aircraft that is not there.
        if self.find_model(experiment.model_id) is None:
            return {"ok": False, "text": t("experiment_no_model",
                                           id=experiment.model_id,
                                           experiment=experiment.id)}

        run_id = experimentlib.experiment_run_id(experiment.id)
        self.experiment = experimentlib.ExperimentRunner(
            experiment, run_id,
            launch=lambda arm, definition, index: _CampaignIteration(
                self, definition, index,
                experiment=experiment.stamp(run_id, arm, index)),
            on_progress=self._on_experiment_event)
        self.experiment_thread = threading.Thread(
            target=self._experiment_loop, args=(experiment, run_id),
            name=f"experiment-{run_id}", daemon=True)
        self.experiment_thread.start()
        text = t("experiment_started", id=run_id, experiment=experiment.id,
                 model=experiment.model_id, arms=len(experiment.arms),
                 runs=experiment.total_runs)
        hub.push_log(text)
        return {"ok": True, "run": run_id,
                "experiment": experiment.as_dict(get_language()), "text": text}

    def _experiment_loop(self, experiment: experimentlib.Experiment,
                         run_id: str) -> None:
        runner = self.experiment
        try:
            runner.run()
        finally:
            # Written whether the experiment finished, failed or was cancelled.
            # An experiment that stopped after its first arm is a result about
            # one arm, and it belongs on disk — with the document saying which
            # arms are short, which is exactly what `arms_short` is for.
            document = analysislib.collect(run_id, paths.RUNS_DIR, experiment,
                                           get_language())
            as_json, _ = analysislib.write(run_id, document, paths.RUNS_DIR)
            self.last_experiment = run_id
            acceptance = document["acceptance"]
            hub.push_log(t("experiment_finished", id=run_id,
                           verdict=document["verdict"],
                           passed=acceptance["passed"],
                           failed=acceptance["failed"],
                           unjudged=acceptance["not_evaluated"],
                           runs=document["runs_recorded"],
                           path=str(as_json.parent)))
            hub.push_json({"type": "experiment", "event": "written",
                           "run": run_id, "document": document})

    def _on_experiment_event(self, event: dict) -> None:
        # A campaign's own events pass through this callback unchanged, because
        # an arm really is a campaign; they are handed to the campaign reporter
        # so the terminal shows one vocabulary for one thing. It does its own
        # broadcast, so this one must not — a browser that received every
        # iteration twice would show a campaign of ten runs as twenty.
        if event.get("type") == "campaign":
            self._on_campaign_event(event)
            return
        hub.push_json(event)
        if event.get("event") == "arm_start":
            hub.push_log(t("experiment_arm", id=event["run"],
                           arm=event["arm"], procedure=event["procedure"],
                           runs=event["runs"], campaign=event["campaign"]))

    def cancel_experiment(self) -> dict:
        if not (self.experiment_thread and self.experiment_thread.is_alive()):
            return {"ok": False, "text": t("experiment_none")}
        self.experiment.cancel()
        return {"ok": True, "text": t("experiment_cancelled",
                                      id=self.experiment.run_id,
                                      done=self.experiment.done)}

    def experiment_status(self) -> dict:
        runner = self.experiment
        running = bool(self.experiment_thread and self.experiment_thread.is_alive())
        if runner is None:
            return {"running": False, "last": self.last_experiment}
        return {"running": running, "last": self.last_experiment,
                "run": runner.run_id,
                "experiment_id": runner.experiment.id,
                "definition": runner.experiment.as_dict(get_language()),
                "done": runner.done,
                "total": runner.experiment.total_runs,
                "arms": {arm: len(rows)
                         for arm, rows in runner.iterations.items()}}

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
            # Whether a link fault is being injected right now. The interface
            # shows it, because a status bar reporting "no telemetry" during a
            # deliberate blackout would otherwise look like a broken tool.
            "link_fault": self.mav.link_fault,
            "campaign": self.campaign_status(),
            "experiment": self.experiment_status(),
            "lang": get_language(),
        }


class _CampaignIteration:
    """One iteration of a campaign, driven through the ordinary START/STOP path.

    WHY IT REUSES START AND STOP RATHER THAN A LIGHTER LAUNCH
    --------------------------------------------------------
    A campaign's claim is that it repeated *the thing the button does*. Booting
    the vehicle some cheaper way would make it a claim about a code path nobody
    uses, and the run directories it produced would not be comparable with the
    ones a person's flight leaves behind.
    """

    def __init__(self, manager: "Manager", definition: campaignlib.Definition,
                 index: int, experiment: Optional[dict] = None) -> None:
        self.manager = manager
        # `experiment` is the stamp an experiment's arm adds beside the campaign
        # one. One iteration class for both, because an arm of an experiment IS
        # a campaign iteration and a second class would be a second answer to
        # "how is a run started".
        res = manager.start_model(definition.model_id,
                                  campaign=definition.stamp(index),
                                  experiment=experiment)
        if not res.get("ok"):
            raise RuntimeError(res.get("text", "the model could not be started"))
        if not manager.mav.wait_ready(timeout=manager.CAMPAIGN_READY_TIMEOUT):
            raise RuntimeError(
                f"no MAVLink heartbeat within "
                f"{manager.CAMPAIGN_READY_TIMEOUT:.0f}s of starting "
                f"{definition.model_id}")
        # Pre-arm is waited for here rather than left to the `arm` step's own
        # retry window: a cold Gazebo boot regularly needs longer than 35 s,
        # and a campaign that recorded that as a vehicle-readiness failure
        # would be measuring how fast the machine is.
        deadline = time.time() + manager.CAMPAIGN_PREARM_TIMEOUT
        while time.time() < deadline:
            state = manager.mav.state
            if state.prearm_known and state.prearm_ok:
                break
            time.sleep(1.0)

    def run(self, procedure_id: str, values: dict) -> tuple[dict, Optional[Path]]:
        proc = procs.get(procedure_id)
        if proc is None:
            raise RuntimeError(f"there is no procedure named '{procedure_id}'")
        self.manager.execute_procedure(proc, values)
        run = self.manager.run
        return ({"run_id": run.run_id if run else None},
                run.dir if run else None)

    def close(self) -> None:
        self.manager.stop()


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


# --------------------------------------------------------------------- v1.4
class CampaignReq(BaseModel):
    model_id: str
    procedure_id: str
    runs: int = campaignlib.DEFAULT_RUNS
    values: dict = {}
    note: str = ""


@app.post("/api/campaign")
def api_campaign(req: CampaignReq):
    """Fly one procedure N times, each with its own run directory and evidence."""
    return JSONResponse(mgr.start_campaign(req.model_id, req.procedure_id,
                                           req.runs, req.values, req.note))


@app.post("/api/campaign/cancel")
def api_campaign_cancel():
    return JSONResponse(mgr.cancel_campaign())


@app.get("/api/campaigns")
def api_campaigns():
    """Every campaign the runs root holds, plus the one running now if any."""
    return {"schema": campaignlib.SCHEMA, "root": str(paths.RUNS_DIR),
            "default_runs": campaignlib.DEFAULT_RUNS,
            "max_runs": Manager.CAMPAIGN_MAX_RUNS,
            "active": mgr.campaign_status(),
            "campaigns": campaignlib.list_campaigns()}


@app.get("/api/campaigns/{campaign_id}")
def api_campaign_detail(campaign_id: str):
    """The aggregate for one campaign, recomputed from its runs every time."""
    if not campaignlib.CAMPAIGN_ID_PATTERN.match(campaign_id):
        return JSONResponse({"ok": False, "text": t("campaign_unknown",
                                                    id=campaign_id)},
                            status_code=404)
    document = campaignlib.aggregate(campaign_id)
    if not document["runs_recorded"]:
        return JSONResponse({"ok": False, "text": t("campaign_unknown",
                                                    id=campaign_id)},
                            status_code=404)
    return {"ok": True, "campaign": document,
            "markdown": campaignlib.render(document)}


# --------------------------------------------------------------------- v1.6
class ExperimentReq(BaseModel):
    experiment_id: str


@app.get("/api/experiments")
def api_experiments():
    """What this project declares as experiments, and what has been run.

    Both lists, because they answer different questions. A declared experiment
    nobody has flown is a question this project asked and never answered, and
    it is invisible in a listing that only shows results.
    """
    try:
        declared = [item.as_dict(get_language())
                    for item in experimentlib.load_all().values()]
        error = ""
    except experimentlib.ExperimentError as exc:
        declared, error = [], str(exc)
    return {"schema": experimentlib.SCHEMA_VERSION,
            "root": str(paths.RUNS_DIR),
            "dir": str(paths.EXPERIMENTS_DIR),
            "policies": list(experimentlib.POLICIES),
            "active": mgr.experiment_status(),
            "experiments": declared,
            "experiments_error": error,
            "runs": analysislib.list_experiment_runs()}


@app.post("/api/experiment")
def api_experiment(req: ExperimentReq):
    """Fly every arm of one experiment, each as an ordinary campaign."""
    return JSONResponse(mgr.start_experiment(req.experiment_id))


@app.post("/api/experiment/cancel")
def api_experiment_cancel():
    return JSONResponse(mgr.cancel_experiment())


@app.get("/api/experiments/{identifier}")
def api_experiment_detail(identifier: str):
    """One experiment run, recomputed from its runs every time.

    Accepts either an experiment run id or a definition id; a definition id
    resolves to its newest recorded run. Both are things a person legitimately
    has in their hand, and making them guess which one the route wants would be
    an interface detail leaking into a URL.
    """
    resolved = _resolve_experiment_run(identifier)
    if resolved is None:
        return JSONResponse({"ok": False,
                             "text": t("experiment_no_runs", id=identifier)},
                            status_code=404)
    # The definition is looked up by `collect` from the stamp the runs carry,
    # so an experiment whose file was renamed still produces a document — with
    # fewer facts in it, and saying which ones are missing.
    document = analysislib.collect(resolved, paths.RUNS_DIR,
                                   lang=get_language())
    return {"ok": True, "experiment": document,
            "markdown": analysislib.render(document, get_language())}


def _resolve_experiment_run(identifier: str) -> Optional[str]:
    """An experiment run id, from either an id or a definition name."""
    if experimentlib.EXPERIMENT_RUN_PATTERN.match(identifier):
        return identifier if analysislib.runs_of(identifier) else None
    newest = [entry for entry in analysislib.list_experiment_runs()
              if entry["experiment_id"] == identifier]
    return newest[0]["run"] if newest else None


@app.get("/api/limitations")
def api_limitations():
    """The four limitation categories and the statements that always apply.

    Served rather than duplicated in the interface, for the same reason the
    fault and metric catalogues are: a standing limitation added to the module
    must not be able to go missing from the page that shows them.
    """
    return {"schema": limitslib.SCHEMA,
            "categories": limitslib.catalogue(get_language())}


@app.get("/api/faults")
def api_faults():
    """The fault catalogue: what each one does, how, and what to watch for.

    Served from `faults.py` rather than duplicated in the interface, for the
    same reason the metric catalogue is: a fault added to the module must not
    be able to appear under a name only the front end knows.
    """
    return {"schema": faultlib.SCHEMA, "faults": faultlib.catalogue(get_language())}


@app.get("/api/failure-categories")
def api_failure_categories():
    """The failure taxonomy, with what each category means and where to look."""
    return {"schema": failurelib.SCHEMA,
            "categories": failurelib.catalogue(get_language())}


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


@app.get("/api/runs/{run_id}/compare")
def api_run_compare(run_id: str, baseline: Optional[str] = None,
                    ignore_config_drift: bool = False):
    """Compare a run's metrics against a baseline run of the same model.

    With no `baseline`, the newest earlier run of the same model is used. That
    is a convenience for the panel and nothing else: CI names its baseline, so
    that what a comparison was made against is a decision in a file rather than
    whatever happened to be on disk that day.
    """
    directory = runlib.run_dir(run_id)
    if directory is None:
        return JSONResponse({"ok": False, "text": t("run_unknown", id=run_id)},
                            status_code=404)
    try:
        current = regression.load_run(directory)
        if baseline:
            other = runlib.run_dir(baseline)
            if other is None:
                return JSONResponse(
                    {"ok": False, "text": t("run_unknown", id=baseline)},
                    status_code=404)
            reference = regression.load_run(other)
        else:
            reference = regression.previous_run_for(current)
            if reference is None:
                # 200, not 404. The endpoint exists and answered; the answer is
                # "this is the first run of this model, so there is nothing to
                # compare it against". That is an ordinary outcome, and a 404
                # would make the browser log an error for it — on a page whose
                # first promise is a clean console.
                return JSONResponse(
                    {"ok": False, "text": t("regression_no_baseline",
                                            model=current["model_id"])})
    except regression.RunNotReadable as exc:
        return JSONResponse({"ok": False, "text": str(exc)}, status_code=409)

    comparison = regression.compare(reference, current,
                                    ignore_config_drift=ignore_config_drift)
    # Written as well as returned: a comparison a browser made is evidence too,
    # and it belongs beside the run rather than only in a tab someone closed.
    regression.write(directory, comparison)
    return {"ok": True, "comparison": comparison}


@app.get("/api/runs/{run_id}/evidence")
def api_run_evidence(run_id: str):
    """The manifest of what this run was expected to leave behind, and did.

    Served rather than only written so the panel can say "complete" or name
    what is missing without the reader opening a file — which is the whole
    point of having a manifest instead of a directory listing.
    """
    directory = runlib.run_dir(run_id)
    if directory is None:
        return JSONResponse({"ok": False, "text": t("run_unknown", id=run_id)},
                            status_code=404)
    manifest = evidencelib.read(directory)
    if not manifest:
        # 200, not 404. The endpoint exists and answered; the answer is "this
        # run predates the manifest". That is an ordinary outcome — every run
        # recorded before v1.5 has one — and a 404 would make the browser log
        # an error for it, on a page whose first promise is a clean console.
        # 404 stays for a run id that does not exist.
        return JSONResponse({"ok": False,
                             "text": t("run_no_evidence", id=run_id)})
    return {"ok": True, "evidence": manifest,
            "problems": evidencelib.problems(manifest)}


@app.get("/api/runs/{run_id}/trace")
def api_run_trace(run_id: str):
    """Intent -> procedure -> step -> criterion -> metric -> evidence -> verdict.

    Computed from the run record every time it is asked for. Nothing about the
    chain is stored, so it cannot drift from the run it describes.
    """
    directory = runlib.run_dir(run_id)
    if directory is None:
        return JSONResponse({"ok": False, "text": t("run_unknown", id=run_id)},
                            status_code=404)
    path = directory / "result.json"
    if not path.is_file():
        # Same rule as the manifest above: a session that never finished is an
        # ordinary thing to open, not a client error.
        return JSONResponse({"ok": False, "text": t("run_no_result", id=run_id)})
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JSONResponse({"ok": False, "text": str(exc)}, status_code=409)
    chain = tracelib.chain(result)
    return {"ok": True, "trace": chain,
            "problems": tracelib.integrity(result, chain),
            "derived_ids": tracelib.derived_ids(chain)}


@app.get("/api/coverage")
def api_coverage():
    """What this project declares, what has been run, and what has not.

    The uncovered lists are the payload. A percentage on its own invites a
    reader to stop, and the point of the endpoint is the names underneath it.
    """
    document = coveragelib.collect([paths.RUNS_DIR])
    return {"schema": coveragelib.SCHEMA, "coverage": document}


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


# --------------------------------------------------------------------------- docs
# The documentation portal. These endpoints only read files that are already in
# the repository — see docs.py for why the portal holds no prose of its own.
@app.get("/api/docs")
def api_docs():
    """The navigation tree, with each page's headings for the search box."""
    return docs.index(get_language())


@app.get("/api/docs/{page_id}")
def api_docs_page(page_id: str):
    document = docs.read(page_id, get_language())
    if not document.get("ok"):
        return JSONResponse(document, status_code=404)
    return document


@app.get("/api/metrics")
def api_metrics():
    """The metric catalogue: what each key means, its unit and its source.

    The interface labels a run's metrics from this rather than from a copy of
    the list, so a metric added to `metrics.py` cannot end up displayed under a
    name only the front end knows.
    """
    return {"schema": metricslib.SCHEMA,
            "metrics": metricslib.catalogue(get_language())}


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
