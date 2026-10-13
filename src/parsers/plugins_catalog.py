"""Legge Plugins-en.settings e restituisce il catalogo completo dei plugin installati.

Prima esecuzione: parsa l'XML (~1-2s) e salva cache in cache/plugins_catalog.json.
Esecuzioni successive: carica dal JSON in millisecondi.
Usa force_refresh=True per ri-parsare l'XML e aggiornare la cache.
"""
import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from src.core.config import PLUGINS_CATALOG, CACHE_DIR
from src.models import Plugin

_CACHE_FILE = CACHE_DIR / "plugins_catalog.json"


# ------------------------------------------------------------------ cache I/O

def _save_cache(plugins: list[Plugin]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "source": str(PLUGINS_CATALOG),
        "count": len(plugins),
        "plugins": [
            {
                "guid":         p.guid,
                "name":         p.name,
                "category":     p.category,
                "sub_category": p.sub_category,
                "vendor":       p.vendor,
            }
            for p in plugins
        ],
    }
    with open(_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_cache() -> list[Plugin] | None:
    if not _CACHE_FILE.exists():
        return None
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return [Plugin(**p) for p in data["plugins"]]
    except Exception:
        return None


# ------------------------------------------------------------------ XML parse

def _parse_xml(path: Path) -> list[Plugin]:
    if not path or not path.exists():
        return []
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception:
        return []
    plugins: list[Plugin] = []
    seen: set[str] = set()

    for section in root.iter("Section"):
        vendor = ""
        version_elem = section.find(".//Version")
        if version_elem is not None:
            vendor = version_elem.get("vendor", "").strip()

        for elem in section.iter("ClassDescription"):
            guid         = elem.get("classID", "").strip()
            name         = elem.get("name", "").strip()
            category     = elem.get("category", "").strip()
            sub_category = elem.get("subCategory", "").strip()

            if not guid or guid in seen:
                continue
            seen.add(guid)

            plugins.append(Plugin(
                guid=guid, name=name,
                category=category, sub_category=sub_category,
                vendor=vendor,
            ))

    return sorted(plugins, key=lambda p: p.name.lower())


# ------------------------------------------------------------------ public API

def load(path: Path = PLUGINS_CATALOG, force_refresh: bool = False) -> list[Plugin]:
    """
    Carica il catalogo plugin. Usa la cache JSON se disponibile.
    force_refresh=True ri-parsa l'XML e sovrascrive la cache.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached is not None:
            return cached

    plugins = _parse_xml(path)
    _save_cache(plugins)
    return plugins


def by_guid(path: Path = PLUGINS_CATALOG, force_refresh: bool = False) -> dict[str, Plugin]:
    """Restituisce il catalogo come dict {guid: Plugin} per lookup rapido."""
    return {p.guid: p for p in load(path, force_refresh=force_refresh)}


def cache_info() -> dict:
    """Restituisce info sulla cache (generata, count) o None se non esiste."""
    if not _CACHE_FILE.exists():
        return {"exists": False}
    try:
        with open(_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {"exists": True, "generated": data.get("generated"), "count": data.get("count")}
    except Exception:
        return {"exists": False}
