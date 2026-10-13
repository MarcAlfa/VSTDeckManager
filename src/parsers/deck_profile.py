"""Legge il profilo Stream Deck e restituisce la struttura navigabile."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import STUDIO_ONE_PROFILE

_PROFILES_DIR = STUDIO_ONE_PROFILE / "Profiles"

_UUID_BACK   = "com.elgato.streamdeck.profile.backtoparent"
_UUID_FOLDER = "com.elgato.streamdeck.profile.openchild"
_UUID_HOTKEY = "com.elgato.streamdeck.system.hotkey"
_UUID_MIDI   = "se.trevligaspel.midi"


@dataclass
class SDSlot:
    pos:         str
    col:         int
    row:         int
    title:       str
    name:        str        # fallback display (es. "Generic Midi")
    action_type: str        # folder | hotkey | midi | back | empty | other
    child_uuid:  str | None = None
    image_path:  Path | None = None
    raw_action:  dict | None = None


@dataclass
class SDPage:
    uuid:     str
    name:     str
    keypad:   dict[str, SDSlot] = field(default_factory=dict)   # 4x2 bottoni
    encoders: dict[str, SDSlot] = field(default_factory=dict)   # knob riga alta


def _parse_slot(pos: str, data: dict, page_dir: Path | None = None) -> SDSlot:
    col, row = (int(x) for x in pos.split(","))
    states = data.get("States") or []
    title  = (states[0].get("Title", "") or "").strip().replace("\t", "") if states else ""
    name   = (data.get("Name", "") or "").strip()
    uuid   = data.get("UUID", "")

    image_path: Path | None = None
    if states and states[0].get("Image") and page_dir:
        img_candidate = page_dir / states[0].get("Image")
        if img_candidate.exists():
            image_path = img_candidate

    if _UUID_BACK in uuid or name == "Parent Folder":
        return SDSlot(pos=pos, col=col, row=row, title="Back", name=name,
                      action_type="back", image_path=image_path, raw_action=data)

    if _UUID_FOLDER in uuid:
        child_uuid = (data.get("Settings") or {}).get("ProfileUUID")
        return SDSlot(pos=pos, col=col, row=row, title=title, name=name,
                      action_type="folder", child_uuid=child_uuid,
                      image_path=image_path, raw_action=data)

    if _UUID_HOTKEY in uuid:
        return SDSlot(pos=pos, col=col, row=row, title=title, name=name,
                      action_type="hotkey", image_path=image_path, raw_action=data)

    if _UUID_MIDI in uuid:
        return SDSlot(pos=pos, col=col, row=row, title=title, name=name,
                      action_type="midi", image_path=image_path, raw_action=data)

    return SDSlot(pos=pos, col=col, row=row, title=title, name=name,
                  action_type="other", image_path=image_path, raw_action=data)


def _load_page(uuid: str) -> SDPage | None:
    page_dir = _PROFILES_DIR / uuid.upper()
    if not page_dir.exists():
        page_dir = _PROFILES_DIR / uuid.lower()
    path = page_dir / "manifest.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))

    keypad:   dict[str, SDSlot] = {}
    encoders: dict[str, SDSlot] = {}

    for ctrl in data.get("Controllers", []):
        target = keypad if ctrl.get("Type") == "Keypad" else encoders
        for pos, act in (ctrl.get("Actions") or {}).items():
            target[pos] = _parse_slot(pos, act, page_dir)

    return SDPage(uuid=uuid.lower(), name=data.get("Name", ""),
                  keypad=keypad, encoders=encoders)


def get_categories(main_pages: list[SDPage], all_pages: dict[str, SDPage]) -> list[dict]:
    """
    Estrae le categorie dalle pagine principali con conteggio slot live.
    Ogni dict: {name, uuid, used, total}.
    Ordine: per pagina principale, poi colonna/riga.
    """
    result = []
    for mp in main_pages:
        for slot in sorted(mp.keypad.values(), key=lambda s: (s.col, s.row)):
            if slot.action_type != "folder" or not slot.child_uuid:
                continue
            child = all_pages.get(slot.child_uuid.lower())
            if child is None:
                continue
            back_count = sum(1 for s in child.keypad.values() if s.action_type == "back")
            total = 4 * 2 - back_count          # 8 slot - back button(s)
            used  = len(child.keypad) - back_count
            result.append({
                "name":  slot.title,
                "uuid":  slot.child_uuid,
                "used":  used,
                "total": total,
            })
    return result


def load_profile() -> tuple[list[SDPage], dict[str, SDPage], str, str]:
    """
    Legge il profilo SD direttamente dai manifest.json (nessuna cache).
    Restituisce (pagine_principali_ordinate, tutte_le_pagine_per_uuid_lowercase,
                 profile_name, profile_uuid).
    """
    root = json.loads((STUDIO_ONE_PROFILE / "manifest.json").read_text(encoding="utf-8"))
    page_uuids   = [u.lower() for u in root.get("Pages", {}).get("Pages", [])]
    profile_name = root.get("Name", "")
    profile_uuid = STUDIO_ONE_PROFILE.stem   # nome cartella = UUID

    all_pages: dict[str, SDPage] = {}
    for folder in _PROFILES_DIR.iterdir():
        if folder.is_dir():
            page = _load_page(folder.name)
            if page:
                all_pages[page.uuid] = page

    main_pages = [
        all_pages[u] for u in page_uuids
        if u in all_pages and all_pages[u].keypad
    ]
    return main_pages, all_pages, profile_name, profile_uuid
