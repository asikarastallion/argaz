"""Model onizleme gorsellerini toplar ve yerel olarak kaydeder.

Kaynaklar (sirayla denenir):
  1. Gazebo model klasorundeki `thumbnails/1.png` (tamamen yerel, en guvenilir)
  2. Modelin geldigi SITL_Models dokumanindaki ILK gorsel (indirilir)

Gorseller `static/models/<id>.png` altina kucultulerek kaydedilir; arayuz
internet olmadan da calissin diye sayfa hicbir seyi uzaktan cekmez.

Kullanim:
    python3 -m argazui.fetch_images            # eksik olanlari indir
    python3 -m argazui.fetch_images --force    # hepsini yeniden indir

ELLE GORSEL EKLEME
------------------
Hicbir kaynakta gorseli olmayan modeller icin (ornek: Iris) simulasyondan
ekran goruntusu alinabilir. Iris'in gorseli soyle uretildi:

    # 1) Modeli ArgazUI'den BASLAT, Gazebo penceresi acilsin
    # 2) Kamerayi araca kilitle:
    source env.sh
    gz service -s /gui/follow --reqtype gz.msgs.StringMsg \
        --reptype gz.msgs.Boolean --timeout 3000 --req 'data: "iris"'
    gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d \
        --reptype gz.msgs.Boolean --timeout 3000 --req 'x: -0.85, y: -0.65, z: 0.38'
    # 3) Pencere kimligini bul ve yakala:
    xwininfo -root -tree | grep "gz-sim-gui"
    import -window <pencere_id> /tmp/ham.png
    # 4) Kirp, 720 px genislige olcekle, static/models/<id>.png olarak kaydet
    #    ve models.json'daki ilgili modele "image": "/static/models/<id>.png" ekle
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

from . import paths

IMAGES_DIR = paths.STATIC_DIR / "models"
MAX_WIDTH = 720          # onizleme icin fazlasi gereksiz

RE_MD_IMG = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
RE_HTML_IMG = re.compile(r"<img[^>]+src=\"(https?://[^\"]+)\"")

# Gazebo model klasoru adlari (registry id'siyle ayni olmayanlar icin)
LOCAL_THUMBNAIL_DIRS = {
    "zephyr": "ardupilot_gazebo/models/zephyr/thumbnails",
}

# Ilk gorselin uygun olmadigi durumlar icin elle secim (0 tabanli sira).
DOC_IMAGE_INDEX: dict[str, int] = {}


def _doc_images(doc_rel: str) -> list[str]:
    """Bir SITL_Models dokumanindaki gorsel URL'lerini sirayla dondurur."""
    doc = paths.ARGAZ / doc_rel
    if not doc.is_file():
        return []
    text = doc.read_text(errors="replace")
    urls: list[str] = []
    for m in re.finditer(r"!\[[^\]]*\]\((https?://[^)\s]+)\)|<img[^>]+src=\"(https?://[^\"]+)\"", text):
        urls.append(m.group(1) or m.group(2))
    return urls


def _save(data: bytes, dest: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:
        dest.write_bytes(data)                     # Pillow yoksa oldugu gibi
        return True
    try:
        img = Image.open(io.BytesIO(data))
        img.seek(0)                                 # GIF ise ilk kare
        img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            h = round(img.height * MAX_WIDTH / img.width)
            img = img.resize((MAX_WIDTH, h), Image.LANCZOS)
        img.save(dest, "PNG", optimize=True)
        return True
    except Exception as exc:
        print(f"      could not process image: {exc}")
        return False


def _from_local_thumbnail(model_id: str, dest: Path) -> bool:
    rel = LOCAL_THUMBNAIL_DIRS.get(model_id)
    if not rel:
        return False
    tdir = paths.ARDU_WS / "src" / rel
    if not tdir.is_dir():
        return False
    for cand in sorted(tdir.glob("*.png")) + sorted(tdir.glob("*.jpg")):
        if _save(cand.read_bytes(), dest):
            print(f"      local thumbnail: {cand.relative_to(paths.ARGAZ)}")
            return True
    return False


def _from_doc(model: dict, dest: Path) -> bool:
    src = model.get("source", "")
    if "SITL_Models" not in src:
        return False
    urls = _doc_images(src)
    if not urls:
        return False
    idx = DOC_IMAGE_INDEX.get(model["id"], 0)
    url = urls[min(idx, len(urls) - 1)]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ArgazUI"})
        data = urllib.request.urlopen(req, timeout=30).read()
    except Exception as exc:
        print(f"      download failed: {exc}")
        return False
    if _save(data, dest):
        print(f"      downloaded from the docs: {url[:70]}...")
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fetch model preview images")
    ap.add_argument("--force", action="store_true", help="Re-download images that already exist")
    args = ap.parse_args(argv)

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    registry = json.loads(paths.MODELS_JSON.read_text())

    changed = 0
    for model in registry["models"]:
        mid = model["id"]
        dest = IMAGES_DIR / f"{mid}.png"
        rel = f"/static/models/{mid}.png"
        print(f"  {mid}")
        if dest.exists() and not args.force:
            print("      already present")
            if model.get("image") != rel:
                model["image"] = rel
                changed += 1
            continue

        if _from_local_thumbnail(mid, dest) or _from_doc(model, dest):
            model["image"] = rel
            changed += 1
        else:
            print("      no image found "
                  "(see the module docstring for capturing one from the simulation)")
            model.pop("image", None)

    paths.MODELS_JSON.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    have = sum(1 for m in registry["models"] if m.get("image"))
    print(f"\n{have}/{len(registry['models'])} models have an image. "
          f"models.json updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
