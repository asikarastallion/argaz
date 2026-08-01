"""ArgazUI backend — FastAPI + WebSocket.

Sadece 127.0.0.1 uzerinde dinler (tek kullanicilik lokal arac).
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import paths
from .i18n import t, set_language, get_language, LANGUAGES
from .mavlink_link import MavlinkLink, substitute
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

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    # -- thread'lerden cagrilir --
    def push_output(self, stream: str, data: bytes) -> None:
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
        self.mav = MavlinkLink(port=paths.UI_MAVLINK_PORT, on_log=hub.push_log)
        self.active_model: Optional[dict] = None
        self.lock = threading.Lock()

    def session(self, stream: str) -> TerminalSession:
        return self.sim if stream == SIM else self.shell

    # -- kayit defteri --
    def registry(self) -> dict:
        if not paths.MODELS_JSON.exists():
            from .scan_models import build_registry
            reg, _ = build_registry()
            paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            paths.MODELS_JSON.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
        return json.loads(paths.MODELS_JSON.read_text())

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
            if self.active_model is not None:
                hub.push_log(t("closing_previous", id=self.active_model["id"]))
                self._stop_locked()

            hub.push_log(t("starting", name=model["name"], method=model["method"]))
            for line in build_launch_commands(model):
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
        self.mav.stop()
        if self.sim.is_alive():
            self.sim.stop_children(log=hub.push_log)
        # Arac kapaninca ona baglanan gorev scriptlerini de birakmayalim
        if self.shell.is_alive():
            self.shell.stop_children(
                log=lambda s: hub.push_log(t("shell_prefix", msg=s), stream=SHELL))
        self.active_model = None
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
            "script_port": paths.SCRIPT_MAVLINK_PORT,
            "ui_port": paths.UI_MAVLINK_PORT,
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
    hub.bind_loop(asyncio.get_running_loop())
    mgr.ensure_terminal()
    asyncio.create_task(_status_pump())


@app.on_event("shutdown")
async def _shutdown():
    mgr.mav.stop()
    mgr.sim.close()
    mgr.shell.close()


# --------------------------------------------------------------------------- statik
@app.get("/")
def index():
    return FileResponse(paths.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(paths.STATIC_DIR)), name="static")
