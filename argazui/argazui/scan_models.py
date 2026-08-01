"""Build the model registry from SITL_Models/Gazebo/docs/*.md.

Uretilen dosya: argazui/config/models.json

Bu dosya "hibrit" bir kayit defteridir: otomatik uretilir ama elle
duzenlenebilir. Yeniden uretim yaparken (--force) elle eklenmis modeller ve
elle degistirilmis alanlar KORUNUR (bkz. merge_registry).

Kullanim:
    python3 -m argazui.scan_models            # rapor + models.json yoksa uret
    python3 -m argazui.scan_models --force    # yeniden tara, elle eklenenleri koru
    python3 -m argazui.scan_models --dry-run  # sadece raporla, yazma
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import paths

# Bu arayuz sadece Copter/Plane/VTOL kapsiyor. Rover, Boat, Quadruped vb.
# bilincli olarak disarida birakiliyor.
SUPPORTED_VEHICLES = {"ArduCopter", "ArduPlane"}

RE_GZ_SIM = re.compile(r"^\s*gz\s+sim\b.*?([\w\-.]+\.sdf)", re.IGNORECASE)
RE_SIM_VEHICLE = re.compile(r"^\s*sim_vehicle\.py\s+(.*)$")
RE_VEHICLE_ARG = re.compile(r"-v\s+(\w+)")
RE_FRAME_ARG = re.compile(r"-f\s+([\w\-]+)")
RE_PARAM_FILE = re.compile(r"--add-param-file=(\S+)")
RE_CUSTOM_LOCATION = re.compile(r"--custom-location=(?:'([^']+)'|\"([^\"]+)\"|(\S+))")
RE_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
# Bazi modeller (ornek: Hexapod Copter, FRAME_CLASS 17 "Dynamic Scripting
# Matrix") motor karistiricisini bir Lua scriptinden alir. Dokuman bunu
# "Copy the script ...lua to the SITL scripts directory" diye belirtir.
# Bu adim atlanirsa arac ARM olmaz: "PreArm: Motors: Check frame class and type"
RE_LUA_SCRIPT = re.compile(r"([\w\-.]+\.lua)")
# Param dosyalarinda hem "Q_ENABLE,1" hem "Q_ENABLE   1" bicimi kullaniliyor.
RE_Q_ENABLE = re.compile(r"^\s*Q_ENABLE\s*[,\s]\s*([\d.]+)", re.MULTILINE)
RE_ANY_Q_PARAM = re.compile(r"^\s*Q_\w+", re.MULTILINE)

VTOL_KEYWORDS = ("quadplane", "quad plane", "vtol", "tailsitter", "tilt")


@dataclass
class ScannedModel:
    id: str
    name: str
    vehicle_class: str          # Copter | Plane | VTOL
    method: str                 # gz_plus_sitl_paramfile | gz_plus_sitl_frame | ros2_launch
    env: str                    # source edilecek dosya (argaz koku baz alinir)
    world: Optional[str] = None
    vehicle: Optional[str] = None
    frame: Optional[str] = None
    param_file: Optional[str] = None
    extra_sitl_args: list = field(default_factory=list)
    lua_scripts: list = field(default_factory=list)
    has_ros2: bool = False
    ros2: Optional[dict] = None
    source: str = ""
    classification_reason: str = ""
    needs_review: bool = False


def _strip_html_and_links(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _classify_plane(param_path: Optional[Path], hints: str) -> tuple[str, str, bool]:
    """ArduPlane modelini Plane / VTOL olarak ayirir.

    Donus: (sinif, gerekce, elle_gozden_gecirilmeli)
    """
    if param_path and param_path.is_file():
        text = param_path.read_text(errors="replace")
        m = RE_Q_ENABLE.search(text)
        if m:
            enabled = float(m.group(1)) > 0
            return (
                ("VTOL" if enabled else "Plane"),
                f"Q_ENABLE={m.group(1)} in {param_path.name}",
                False,
            )
        if RE_ANY_Q_PARAM.search(text):
            return ("VTOL", f"{param_path.name} has Q_ prefixed parameters "
                            "(no Q_ENABLE found)", True)
        return ("Plane", f"no Q_ parameters in {param_path.name}", False)

    low = hints.lower()
    for kw in VTOL_KEYWORDS:
        if kw in low:
            return ("VTOL", f"no parameter file; matched the '{kw}' keyword in the name/title", True)
    return ("Plane", "no parameter file and no VTOL keyword found", True)


def scan_docs(docs_dir: Path = paths.SITL_MODELS_DOCS):
    """docs/*.md tarar. Donus: (kabul_edilen, atlanan) listeleri."""
    accepted: list[ScannedModel] = []
    skipped: list[dict] = []

    if not docs_dir.is_dir():
        return accepted, [{"doc": str(docs_dir), "reason": "docs directory not found"}]

    for md in sorted(docs_dir.glob("*.md")):
        raw = md.read_text(errors="replace")
        lines = raw.splitlines()

        # "Copy the script <ad>.lua to the SITL scripts directory" gibi
        # on kosullari yakala; bu scriptler olmadan model ARM olmuyor.
        doc_lua: list[str] = []
        for ln in lines:
            if "lua" not in ln.lower():
                continue
            if not re.search(r"cop(y|ied)|scripts (dir|folder)", ln, re.IGNORECASE):
                continue
            for name in RE_LUA_SCRIPT.findall(ln):
                cand = paths.SITL_MODELS_SCRIPTS / Path(name).name
                if cand.is_file() and cand.name not in doc_lua:
                    doc_lua.append(cand.name)

        title = md.stem
        current_world: Optional[str] = None
        current_heading = ""
        variants_in_doc = 0

        # Once H1 basligini bul (gorunen isim icin)
        for ln in lines:
            h = RE_HEADING.match(ln)
            if h and len(h.group(1)) == 1:
                title = _strip_html_and_links(h.group(2))
                break

        pending: list[ScannedModel] = []
        for ln in lines:
            h = RE_HEADING.match(ln)
            if h:
                current_heading = _strip_html_and_links(h.group(2)).strip("`")
                continue

            gz = RE_GZ_SIM.search(ln)
            if gz:
                current_world = gz.group(1)
                continue

            sv = RE_SIM_VEHICLE.match(ln)
            if not sv:
                continue

            args = sv.group(1)
            vm = RE_VEHICLE_ARG.search(args)
            vehicle = vm.group(1) if vm else None
            if vehicle not in SUPPORTED_VEHICLES:
                skipped.append({
                    "doc": md.name,
                    "vehicle": vehicle or "?",
                    "reason": "vehicle type other than Copter/Plane (out of scope)",
                })
                continue

            fm = RE_FRAME_ARG.search(args)
            frame = fm.group(1) if fm else None
            pm = RE_PARAM_FILE.search(args)
            param_rel = None
            param_path = None
            if pm:
                param_name = Path(pm.group(1)).name
                param_path = paths.SITL_MODELS_CONFIG / param_name
                param_rel = f"$SITL_MODELS/Gazebo/config/{param_name}"

            extra = []
            cl = RE_CUSTOM_LOCATION.search(args)
            if cl:
                loc = cl.group(1) or cl.group(2) or cl.group(3)
                extra.append(f"--custom-location={loc}")

            # id: param dosyasi > world > doc adi
            if param_path is not None:
                mid = param_path.stem
            elif current_world:
                mid = Path(current_world).stem
            else:
                mid = md.stem.lower()

            if vehicle == "ArduCopter":
                vclass = "Copter"
                reason = "sim_vehicle.py -v ArduCopter"
                review = False
            else:
                hints = f"{title} {current_heading} {mid}"
                vclass, reason, review = _classify_plane(param_path, hints)

            if param_path is not None and not param_path.is_file():
                review = True
                reason += f" | WARNING: {param_path} not found"

            world_ok = True
            if current_world:
                wp = paths.SITL_MODELS_WORLDS / current_world
                if not wp.is_file():
                    world_ok = False
                    review = True
                    reason += f" | WARNING: world {current_world} not found"
            else:
                world_ok = False
                review = True
                reason += " | WARNING: no gz sim world line found"

            name = title
            variants_in_doc += 1

            if doc_lua:
                reason += (f" | requires Lua: {', '.join(doc_lua)} "
                           "(ArgazUI copies it into the working directory)")

            pending.append(ScannedModel(
                id=mid,
                name=name,
                vehicle_class=vclass,
                method="gz_plus_sitl_paramfile" if param_rel else "gz_plus_sitl_frame",
                env="quadplane_env.sh",
                world=current_world if world_ok else current_world,
                vehicle=vehicle,
                frame=frame,
                param_file=param_rel,
                extra_sitl_args=extra,
                lua_scripts=list(doc_lua),
                has_ros2=False,
                source=f"SITL_Models/Gazebo/docs/{md.name}",
                classification_reason=reason,
                needs_review=review,
            ))

        # Ayni dokumanda birden fazla varyant varsa isimleri ayirt et
        if variants_in_doc > 1:
            for p in pending:
                p.name = f"{p.name} ({p.id})"
        accepted.extend(pending)

    return accepted, skipped


def builtin_models() -> list[ScannedModel]:
    """SITL_Models'ta olmayan, ardu_ws'den gelen modeller (elle tanimli)."""
    return [
        ScannedModel(
            id="iris",
            name="Iris Quadcopter (ROS2 + RViz)",
            vehicle_class="Copter",
            method="ros2_launch",
            env="env.sh",
            vehicle="ArduCopter",
            has_ros2=True,
            ros2={
                "package": "ardupilot_gz_bringup",
                "launch_file": "iris_runway.launch.py",
                "args": ["console:=True", "map:=True", "rviz:=True"],
            },
            source="ardu_ws / ardupilot_gz_bringup (defined manually)",
            classification_reason="ardupilot_gz_bringup iris_runway.launch.py -> arducopter",
        ),
        ScannedModel(
            id="zephyr",
            name="Zephyr Delta Wing",
            vehicle_class="Plane",
            method="gz_plus_sitl_frame",
            env="env.sh",
            world="zephyr_runway.sdf",
            vehicle="ArduPlane",
            frame="gazebo-zephyr",
            has_ros2=False,
            source="ardu_ws / ardupilot_gazebo (defined manually)",
            classification_reason="the gazebo-zephyr frame is a fixed-wing plane (no Q_ parameters)",
        ),
    ]


def build_registry() -> tuple[dict, list[dict]]:
    scanned, skipped = scan_docs()
    models = builtin_models() + scanned
    registry = {
        "_comment": (
            "ArgazUI model registry. Generated automatically "
            "(python3 -m argazui.scan_models --force) but safe to edit by hand. "
            "Models marked '_manually_added': true survive a rescan."
        ),
        "_fields": {
            "vehicle_class": "Copter | Plane | VTOL (selects the button set)",
            "method": "ros2_launch | gz_plus_sitl_paramfile | gz_plus_sitl_frame",
            "env": "environment file to source, relative to the argaz root",
            "has_ros2": "true when ROS2/DDS/RViz are available for this model",
            "lua_scripts": "Lua scripts copied into the model's working directory",
            "sitl_param_overrides": "parameters applied at boot as a second param file",
            "needs_review": "true when the classification is a guess — verify by hand",
        },
        "models": [asdict(m) for m in models],
    }
    return registry, skipped


def merge_registry(new: dict, old: dict) -> dict:
    """Preserve anything the user changed by hand across a rescan."""
    old_by_id = {m.get("id"): m for m in old.get("models", [])}
    merged = []
    for m in new["models"]:
        prev = old_by_id.pop(m["id"], None)
        if prev and prev.get("_manually_edited"):
            merged.append(prev)          # locked by the user — leave it alone
        elif prev:
            # keep any extra fields the user added
            keep = {k: v for k, v in prev.items() if k not in m}
            m = {**m, **keep}
            merged.append(m)
        else:
            merged.append(m)
    # Keep models that exist in the registry but were not found by the scan
    for leftover in old_by_id.values():
        leftover.setdefault("_manually_added", True)
        merged.append(leftover)
    new["models"] = merged
    return new


def print_report(registry: dict, skipped: list[dict]) -> None:
    models = registry["models"]
    by_class: dict[str, list] = {}
    for m in models:
        by_class.setdefault(m["vehicle_class"], []).append(m)

    print("=" * 74)
    print(f"ArgazUI model scan — {len(models)} models in the registry")
    print("=" * 74)
    for cls in ("Copter", "Plane", "VTOL"):
        items = by_class.get(cls, [])
        print(f"\n[{cls}] — {len(items)} models")
        for m in items:
            flag = "  <-- VERIFY BY HAND" if m.get("needs_review") else ""
            print(f"  - {m['id']:<24} {m['name']}{flag}")
            print(f"      method : {m['method']}   env: {m['env']}")
            if m.get("world"):
                print(f"      world  : {m['world']}")
            if m.get("param_file"):
                print(f"      param  : {m['param_file']}")
            if m.get("frame"):
                print(f"      frame  : {m['frame']}")
            print(f"      reason : {m['classification_reason']}")

    if skipped:
        print(f"\n[OUT OF SCOPE] — {len(skipped)} entries skipped")
        seen = set()
        for s in skipped:
            key = (s["doc"], s.get("vehicle"))
            if key in seen:
                continue
            seen.add(key)
            print(f"  - {s['doc']:<28} vehicle={s.get('vehicle')}  ({s['reason']})")
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the model registry from the SITL_Models docs")
    ap.add_argument("--force", action="store_true", help="regenerate even if models.json exists (merging)")
    ap.add_argument("--dry-run", action="store_true", help="Report only, do not write the file")
    args = ap.parse_args(argv)

    registry, skipped = build_registry()
    print_report(registry, skipped)

    if args.dry_run:
        print("(--dry-run: models.json not written)")
        return 0

    paths.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if paths.MODELS_JSON.exists() and not args.force:
        print(f"{paths.MODELS_JSON} already exists — not overwritten. "
              f"Use --force to regenerate.")
        return 0

    if paths.MODELS_JSON.exists():
        try:
            old = json.loads(paths.MODELS_JSON.read_text())
            registry = merge_registry(registry, old)
            print("Merged with the existing models.json (manual entries preserved).")
        except json.JSONDecodeError as exc:
            print(f"WARNING: could not read the existing models.json ({exc}); writing a fresh one.")

    paths.MODELS_JSON.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    print(f"Written: {paths.MODELS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
