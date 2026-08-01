"""Merkezi yol tanimlari.

ArgazUI, argaz kurulumunu SADECE OKUR. Bu dosyadaki hicbir yol yazma amacli
kullanilmaz; tek istisna ARGAZUI_DIR altindaki config/ klasorudur.
"""
from pathlib import Path

# .../argaz/argazui/argazui/paths.py -> .../argaz
ARGAZUI_DIR = Path(__file__).resolve().parent.parent
ARGAZ = ARGAZUI_DIR.parent

# Salt-okunur argaz kurulumu
ENV_SH = ARGAZ / "env.sh"
QUADPLANE_ENV_SH = ARGAZ / "quadplane_env.sh"
ARDUPILOT = ARGAZ / "ardupilot"
ARDU_WS = ARGAZ / "ardu_ws"
SITL_MODELS = ARGAZ / "SITL_Models"
SITL_MODELS_DOCS = SITL_MODELS / "Gazebo" / "docs"
SITL_MODELS_CONFIG = SITL_MODELS / "Gazebo" / "config"
SITL_MODELS_WORLDS = SITL_MODELS / "Gazebo" / "worlds"
SITL_MODELS_SCRIPTS = SITL_MODELS / "Gazebo" / "scripts"

# ArgazUI'ye ait, yazilabilir alanlar
CONFIG_DIR = ARGAZUI_DIR / "config"
STATIC_DIR = ARGAZUI_DIR / "static"
# Her model kendi calisma klasorunde kosar. Boylece SITL'in urettigi
# eeprom.bin / logs / terrain dosyalari ardupilot agacina DEGIL buraya yazilir
# (ardupilot/ salt-okunur kalmali) ve modeller birbirinin eeprom'unu bozmaz.
RUN_DIR = ARGAZUI_DIR / "run"
MODELS_JSON = CONFIG_DIR / "models.json"
BUTTONS_JSON = CONFIG_DIR / "buttons.json"
# Declarative takeoff/landing procedures. The UI button and the regression
# test run the SAME file through the same runner — see procedures/SCHEMA.md.
PROCEDURES_DIR = ARGAZUI_DIR / "procedures"

# Kullanicinin gorev scriptleri
SCRIPTS_DIR = ARGAZ / "scripts"

# MAVLink port ayrimi:
#   14550 -> ArgazUI'nin kendi komut/telemetri baglantisi
#   14551 -> kullanicinin gorev scriptleri (scripts/*.py)
UI_MAVLINK_PORT = 14550
SCRIPT_MAVLINK_PORT = 14551
