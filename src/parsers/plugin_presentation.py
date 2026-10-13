"""Legge PluginPresentation.settings e ritorna {GUID_upper: sortPath}.

La sezione 'plugins' contiene elementi come:
  <PlugInInfo classID="{GUID}" sortPath="CategoryName" .../>

Se sortPath è vuoto, ritorna "" (il caller decide il fallback).
"Special" viene normalizzato a "Special-Fx" per coerenza con le altre categorie.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.core.config import CFG

_PRES_FILE = Path(CFG["fsp"].get("plugin_presentation", ""))

_cache: dict[str, str] | None = None


def _normalize(sort_path: str) -> str:
    if sort_path == "Special":
        return "Special-Fx"
    return sort_path


def load(force_refresh: bool = False) -> dict[str, str]:
    """Ritorna {GUID_upper: sortPath}. Cached dopo la prima lettura, aggiornabile con force_refresh=True."""
    global _cache
    if not force_refresh and _cache is not None:
        return _cache

    _cache = {}

    if not _PRES_FILE or not _PRES_FILE.exists():
        return _cache

    try:
        tree = ET.parse(_PRES_FILE)
        root = tree.getroot()

        # Cerca la Section path="plugins" (può essere annidato)
        plugins_section = None
        for sec in root.iter("Section"):
            if sec.get("path") == "plugins":
                plugins_section = sec
                break

        if plugins_section is None:
            return _cache

        for info in plugins_section.iter("PlugInInfo"):
            cid = info.get("classID", "").strip().upper()
            if not cid:
                continue
            # classID ha forma "{GUID}" — rimuoviamo le graffe se presenti
            if cid.startswith("{") and cid.endswith("}"):
                cid = cid[1:-1]
            sort_path = _normalize(info.get("sortPath", "").strip())
            _cache[cid] = sort_path

    except Exception:
        pass

    return _cache
