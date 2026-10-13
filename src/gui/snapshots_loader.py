"""Carica il mapping guid → immagine da D:\\StudioOne\\Snapshots.

Per ogni plugin ci sono fino a 3 versioni:
  Plugin.png          →  thumbnail bassa (~130x78)
  Plugin@2x.png       →  thumbnail 2x    (~260x156)
  Plugin.original.png →  full-res        (~1000x600)

get_snapshot_map()      → @2x se disponibile, altrimenti .png  (per card thumbnail)
get_snapshot_hires_map() → .original se disponibile, poi @2x, poi .png  (per detail view)
"""
import json
from pathlib import Path

from src.core.config import CFG

_SNAPSHOTS_DIR = Path(CFG["fsp"].get("snapshots_dir", r"D:\StudioOne\Snapshots"))

_thumb_map: dict[str, Path] | None = None
_hires_map: dict[str, Path] | None = None


def _best_path(vendor_dir: Path, base_name: str, prefer_hires: bool) -> Path | None:
    """Ritorna il path migliore disponibile per il plugin dato il nome base."""
    stem = Path(base_name).stem   # es. "Pro-Q 3"
    if prefer_hires:
        candidates = [
            vendor_dir / f"{stem}.original.png",
            vendor_dir / f"{stem}@2x.png",
            vendor_dir / base_name,
        ]
    else:
        candidates = [
            vendor_dir / f"{stem}@2x.png",
            vendor_dir / base_name,
        ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _build_maps():
    global _thumb_map, _hires_map
    _thumb_map = {}
    _hires_map = {}

    if not _SNAPSHOTS_DIR.exists():
        return

    for vendor_dir in _SNAPSHOTS_DIR.iterdir():
        if not vendor_dir.is_dir():
            continue
        json_file = vendor_dir / "snapshots.json"
        if not json_file.exists():
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            for entry in data.get("snapshots", []):
                cid      = entry.get("cid", "").strip().upper()
                img_name = entry.get("default", "")
                if not cid or not img_name:
                    continue
                thumb = _best_path(vendor_dir, img_name, prefer_hires=False)
                hires = _best_path(vendor_dir, img_name, prefer_hires=True)
                if thumb:
                    _thumb_map[cid] = thumb
                if hires:
                    _hires_map[cid] = hires
        except Exception:
            pass


def get_snapshot_map(force_refresh: bool = False) -> dict[str, Path]:
    """GUID → @2x.png (o .png). Per thumbnail nelle card."""
    global _thumb_map
    if force_refresh or _thumb_map is None:
        _build_maps()
    return _thumb_map


def get_snapshot_hires_map(force_refresh: bool = False) -> dict[str, Path]:
    """GUID → .original.png (o @2x o .png). Per la detail view."""
    global _hires_map
    if force_refresh or _hires_map is None:
        _build_maps()
    return _hires_map



def find_plugin_snapshot(guid: str) -> Path | None:
    """Cerca lo snapshot migliore per un GUID plugin (con o senza graffe, hires preferito)."""
    if not guid:
        return None
    guid_clean = guid.strip().upper()
    hires = get_snapshot_hires_map()
    with_braces = f"{{{guid_clean.strip('{}')}}}"
    without_braces = guid_clean.strip("{}")
    for k in (guid_clean, with_braces, without_braces):
        if k in hires:
            return hires[k]
    thumbs = get_snapshot_map()
    for k in (guid_clean, with_braces, without_braces):
        if k in thumbs:
            return thumbs[k]
    return None

