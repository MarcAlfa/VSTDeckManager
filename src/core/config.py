"""Carica config.json e fornisce i path dell'app."""
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _ROOT = Path(sys.executable).parent
else:
    _ROOT = Path(__file__).parent.parent.parent  # root del progetto

_CONFIG_FILE = _ROOT / "config.json"
_EXAMPLE_CONFIG = _ROOT / "config.example.json"

VERSION = "0.9.2"
YEAR = "2026"

_DEFAULT_CONFIG = {
    "fsp": {
        "config_root": "",
        "macros_dir": "",
        "plugins_catalog": "",
        "plugin_presentation": "",
        "keyscheme": "",
        "macro_group": "SdR",
        "macro_prefix": "SdR_",
        "snapshots_dir": ""
    },
    "streamdeck": {
        "profiles_root": "",
        "studio_one_profile_uuid": ""
    },
    "app": {
        "backup_dir": "backups"
    }
}


def load() -> dict:
    if not _CONFIG_FILE.exists():
        if _EXAMPLE_CONFIG.exists():
            try:
                data = json.loads(_EXAMPLE_CONFIG.read_text(encoding="utf-8"))
                with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return data
            except Exception:
                pass
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return _DEFAULT_CONFIG.copy()

    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _DEFAULT_CONFIG.copy()


# Config globale
CFG = load()
CFG["version"] = VERSION
CFG["year"] = YEAR

# Shortcut
FSP = CFG.get("fsp", {})
SD = CFG.get("streamdeck", {})
APP = CFG.get("app", {})

# Path comodi come oggetti Path
MACROS_DIR = Path(FSP.get("macros_dir", ""))
PLUGINS_CATALOG = Path(FSP.get("plugins_catalog", ""))
PLUGIN_PRESENTATION = Path(FSP.get("plugin_presentation", ""))
KEYSCHEME = Path(FSP.get("keyscheme", ""))
PROFILES_ROOT = Path(SD.get("profiles_root", ""))

_uuid = SD.get("studio_one_profile_uuid", "")
STUDIO_ONE_PROFILE = (PROFILES_ROOT / f"{_uuid}.sdProfile") if _uuid else Path()
BACKUP_DIR = _ROOT / APP.get("backup_dir", "backups")
CACHE_DIR  = _ROOT / "cache"

# Prefisso/gruppo delle macro gestite dall'app (es. "SdR_" / "SdR")
MACRO_PREFIX = FSP.get("macro_prefix") or "SdR_"
MACRO_GROUP  = FSP.get("macro_group") or "SdR"


def reload_config() -> dict:
    """Ricarica la configurazione e aggiorna le variabili globali."""
    global CFG, FSP, SD, APP, MACROS_DIR, PLUGINS_CATALOG, PLUGIN_PRESENTATION
    global KEYSCHEME, PROFILES_ROOT, STUDIO_ONE_PROFILE, BACKUP_DIR, MACRO_PREFIX, MACRO_GROUP
    CFG = load()
    FSP = CFG.get("fsp", {})
    SD = CFG.get("streamdeck", {})
    APP = CFG.get("app", {})

    MACROS_DIR = Path(FSP.get("macros_dir", ""))
    PLUGINS_CATALOG = Path(FSP.get("plugins_catalog", ""))
    PLUGIN_PRESENTATION = Path(FSP.get("plugin_presentation", ""))
    KEYSCHEME = Path(FSP.get("keyscheme", ""))
    PROFILES_ROOT = Path(SD.get("profiles_root", ""))
    u = SD.get("studio_one_profile_uuid", "")
    STUDIO_ONE_PROFILE = (PROFILES_ROOT / f"{u}.sdProfile") if u else Path()
    BACKUP_DIR = _ROOT / APP.get("backup_dir", "backups")
    MACRO_PREFIX = FSP.get("macro_prefix") or "SdR_"
    MACRO_GROUP  = FSP.get("macro_group") or "SdR"
    return CFG


def check_path_validity(path_str: str, expect_dir: bool = False) -> tuple[bool, str]:
    """Verifica se una stringa percorso è valida ed esiste. Ritorna (valido, messaggio)."""
    if not path_str or not path_str.strip():
        return False, "Not configured"
    p = Path(path_str.strip())
    if not p.exists():
        return False, "File or folder not found"
    if expect_dir and not p.is_dir():
        return False, "Expected a directory"
    if not expect_dir and not p.is_file():
        return False, "Expected a file"
    return True, "Valid"


def is_configured() -> bool:
    """Verifica se almeno il catalogo plugin o le cartelle essenziali sono configurate ed esistenti."""
    if not PLUGINS_CATALOG or not PLUGINS_CATALOG.is_file():
        return False
    if not STUDIO_ONE_PROFILE or not STUDIO_ONE_PROFILE.is_dir():
        return False
    return True

