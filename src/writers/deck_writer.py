"""Writer sicuro per aggiungere pulsanti Hotkey in profili Elgato Stream Deck Plus.

Specifiche tecniche Stream Deck:
- Layout Keypad: 4 colonne x 2 righe (posizioni da "0,0" a "3,1").
- Posizione "0,0": riservata all'azione backtoparent (Parent Folder).
- Slot disponibili per pagina: 7 (da 1,0 a 3,1).
- Backup automatico di manifest.json prima di ogni scrittura.
- Scrittura atomica via file temporaneo.
"""
from __future__ import annotations

import json
import os
import secrets
import string
import uuid
from pathlib import Path

from PIL import Image

from src.core.config import STUDIO_ONE_PROFILE
from src.core.backup import backup


class DeckWriterError(Exception):
    """Errore durante la modifica del profilo Stream Deck."""
    pass


def create_deck_icon(image_source_path: Path, target_dir: Path) -> tuple[str, Path]:
    """Ridimensiona e adatta uno snapshot del plugin dentro una canvas 288x288 RGBA trasparente.

    Salva l'immagine nella cartella target con nome file univoco Stream Deck (27 caratteri alfanumerici maiuscoli)
    e restituisce la tupla (percorso_relativo_manifest, path_assoluto_file).
    """
    target_dir.mkdir(parents=True, exist_ok=True)

    alphabet = string.ascii_uppercase + string.digits
    for _ in range(100):
        name = "".join(secrets.choice(alphabet) for _ in range(27)) + ".png"
        target_path = target_dir / name
        if not target_path.exists():
            break
    else:
        name = f"ICON_{uuid.uuid4().hex[:20].upper()}.png"
        target_path = target_dir / name

    with Image.open(image_source_path) as src:
        src_rgba = src.convert("RGBA")
        src_rgba.thumbnail((288, 288), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (288, 288), (0, 0, 0, 0))
        x = (288 - src_rgba.width) // 2
        y = (288 - src_rgba.height) // 2
        canvas.paste(src_rgba, (x, y), mask=src_rgba)

        canvas.save(target_path, "PNG")

    return f"Images/{name}", target_path


# Mapping dei caratteri/simboli verso i codici tasto Stream Deck (Windows)
# NativeCode / VKeyCode / QTKeyCode
_CHAR_CODE_MAP: dict[str, tuple[int, int, int]] = {
    # Lettere (maiuscole)
    **{chr(c): (c, c, c) for c in range(65, 91)},
    # Cifre 0-9
    **{str(d): (48 + d, 48 + d, 48 + d) for d in range(10)},
    # Tasti Funzione F1-F12
    **{f"F{i}": (111 + i, 111 + i, 111 + i) for i in range(1, 13)},
    # Simboli specifici mappati dai profili reali di Stream Deck
    ";": (186, 59, 186),
    ":": (186, 59, 186),
    "=": (187, 61, 187),
    "+": (187, 43, 187),
    ",": (188, 44, 188),
    "<": (188, 60, 188),
    "-": (189, 45, 189),
    "_": (189, 95, 189),
    ".": (190, 46, 190),
    ">": (190, 62, 190),
    "/": (191, 47, 191),
    "?": (191, 63, 191),
    "`": (192, 96, 192),
    "~": (192, 126, 192),
    "[": (219, 91, 219),
    "{": (219, 123, 219),
    "\\": (220, 92, 220),
    "|": (220, 124, 220),
    "]": (221, 93, 221),
    "}": (221, 125, 221),
    "'": (222, 39, 222),
    "\"": (222, 34, 222),
    # Simboli con Shift (es. tasti numerici US/IT)
    "!": (49, 33, 49),
    "@": (50, 64, 50),
    "#": (51, 35, 51),
    "$": (52, 36, 52),
    "%": (53, 37, 53),
    "^": (54, 94, 54),
    "&": (55, 38, 55),
    "*": (56, 42, 56),
    "(": (57, 40, 57),
    ")": (48, 41, 48),
}

# Ordine standard di scansione slot (riga per riga, da sinistra a destra)
# Riga 0 (superiore): (0,0 = back), 1,0, 2,0, 3,0
# Riga 1 (inferiore): 0,1, 1,1, 2,1, 3,1
SLOT_ORDER: list[str] = [
    "1,0", "2,0", "3,0", "0,1", "1,1", "2,1", "3,1"
]

_SHIFT_SYMBOLS: set[str] = set("!@#$%^&*()_+{}|:\"<>?~")


def parse_shortcut_to_hotkey(shortcut: str) -> dict:
    """Converte una stringa di scorciatoia (es. 'Ctrl+Shift+Alt+Q' o 'Ctrl+Alt+%') nel formato Hotkey di Stream Deck."""
    if shortcut.endswith("++"):
        key_char = "+"
        prefix = shortcut[:-2]
        mods = [p.strip() for p in prefix.split("+") if p.strip()]
    else:
        parts = [p.strip() for p in shortcut.split("+")]
        key_char = parts[-1]
        mods = parts[:-1]

    has_ctrl = "Ctrl" in mods
    has_alt = "Alt" in mods
    has_shift = "Shift" in mods
    has_cmd = "Cmd" in mods or "Win" in mods

    # Calcolo bitmask modificatori (1=Shift, 2=Ctrl, 4=Alt, 8=Cmd)
    mod_mask = (1 if has_shift else 0) | (2 if has_ctrl else 0) | (4 if has_alt else 0) | (8 if has_cmd else 0)

    # Se non specificato diversamente per i simboli di Studio One SdR, Modifiers = 7 (Ctrl+Shift+Alt)
    if "Ctrl" in mods and "Alt" in mods and not has_shift and key_char in _SHIFT_SYMBOLS:
        # I simboli speciali usati nelle macro Studio One operano con Shift attivo a livello fisico
        has_shift = True
        mod_mask |= 1

    lookup_char = key_char.upper() if len(key_char) == 1 else key_char
    if lookup_char in _CHAR_CODE_MAP:
        native, qt, vkey = _CHAR_CODE_MAP[lookup_char]
    else:
        # Fallback codice ASCII se non trovato
        code = ord(lookup_char[0]) if lookup_char else 65
        native, qt, vkey = code, code, code

    slot1 = {
        "KeyCmd": has_cmd,
        "KeyCtrl": has_ctrl,
        "KeyModifiers": mod_mask,
        "KeyOption": has_alt,
        "KeyShift": has_shift,
        "NativeCode": native,
        "QTKeyCode": qt,
        "VKeyCode": vkey,
    }

    # 3 slot placeholder vuoti come da specifiche Elgato
    empty_slot = {
        "KeyCmd": False,
        "KeyCtrl": False,
        "KeyModifiers": 0,
        "KeyOption": False,
        "KeyShift": False,
        "NativeCode": 146,
        "QTKeyCode": 33554431,
        "VKeyCode": -1,
    }

    return {
        "Coalesce": True,
        "Hotkeys": [slot1, dict(empty_slot), dict(empty_slot), dict(empty_slot)],
    }


def find_first_free_slot(actions: dict) -> str | None:
    """Restituisce la prima posizione libera (es. '1,0') secondo l'ordine standard dei tasti."""
    for pos in SLOT_ORDER:
        if pos not in actions:
            return pos
    return None


def add_hotkey_to_page(
    page_uuid: str,
    shortcut: str,
    title: str,
    position: str | None = None,
    icon_source_path: Path | None = None,
    profiles_root: Path = STUDIO_ONE_PROFILE / "Profiles",
) -> tuple[Path, str]:
    """Aggiunge in modo sicuro un tasto Hotkey nella pagina Stream Deck specificata.

    Restituisce: (backup_path, slot_utilizzato)
    """
    manifest_path = profiles_root / page_uuid.upper() / "manifest.json"
    if not manifest_path.exists():
        # Prova minuscolo se non trovato
        manifest_path = profiles_root / page_uuid.lower() / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json non trovato per la pagina SD '{page_uuid}'")

    raw_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Cerca il controller Keypad
    keypad = None
    for ctrl in raw_data.get("Controllers", []):
        if ctrl.get("Type") == "Keypad":
            keypad = ctrl
            break

    if keypad is None:
        raise DeckWriterError(f"Nessun controller Keypad trovato in {manifest_path.name}")

    actions = keypad.setdefault("Actions", {})

    target_pos = position or find_first_free_slot(actions)
    if not target_pos:
        raise DeckWriterError(f"La pagina Stream Deck '{page_uuid}' è al completo (nessun slot libero).")

    if target_pos in actions:
        raise DeckWriterError(f"Lo slot '{target_pos}' nella pagina SD è già occupato.")

    if target_pos == "0,0":
        raise DeckWriterError("Lo slot '0,0' è riservato al pulsante Back e non può essere sovrascritto.")

    # Generazione icona opzionale da snapshot
    icon_rel_path: str | None = None
    created_icon_file: Path | None = None
    if icon_source_path and Path(icon_source_path).exists():
        images_dir = manifest_path.parent / "Images"
        try:
            icon_rel_path, created_icon_file = create_deck_icon(Path(icon_source_path), images_dir)
        except Exception:
            icon_rel_path = None
            created_icon_file = None

    # Backup del manifest prima di qualsiasi modifica
    backup_path = backup(manifest_path)

    # Costruzione dell'azione Hotkey
    hotkey_settings = parse_shortcut_to_hotkey(shortcut)
    action_id = str(uuid.uuid4()).lower()

    state_obj: dict = {"Title": title}
    if icon_rel_path:
        state_obj["Image"] = icon_rel_path

    new_action = {
        "ActionID": action_id,
        "LinkedTitle": True,
        "Name": "Hotkey",
        "Plugin": {
            "Name": "Activate a Key Command",
            "UUID": "com.elgato.streamdeck.system.hotkey",
            "Version": "1.0",
        },
        "Resources": None,
        "Settings": hotkey_settings,
        "State": 0,
        "States": [
            state_obj
        ],
        "UUID": "com.elgato.streamdeck.system.hotkey",
    }

    actions[target_pos] = new_action

    # Scrittura atomica
    temp_path = manifest_path.parent / f".{manifest_path.name}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, manifest_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if created_icon_file and created_icon_file.exists():
            try:
                created_icon_file.unlink(missing_ok=True)
            except Exception:
                pass
        raise DeckWriterError(f"Errore durante la scrittura di manifest.json: {exc}") from exc

    return backup_path, target_pos


def find_hotkey_in_profile(
    shortcut: str,
    title_match: str = "",
    profiles_root: Path = STUDIO_ONE_PROFILE / "Profiles",
) -> tuple[str, str] | None:
    """Cerca in tutte le pagine SD del profilo se esiste un'azione Hotkey associata.

    Restituisce (page_uuid, pos) se trovata, altrimenti None.
    """
    for page_dir in profiles_root.iterdir():
        if not page_dir.is_dir():
            continue
        manifest_path = page_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            d = json.loads(manifest_path.read_text(encoding="utf-8"))
            for ctrl in d.get("Controllers", []):
                if ctrl.get("Type") == "Keypad":
                    for pos, act in (ctrl.get("Actions") or {}).items():
                        if act.get("Plugin", {}).get("UUID") == "com.elgato.streamdeck.system.hotkey":
                            # Verifica per titolo o per scorciatoia se titolo fornito
                            title = act.get("States", [{}])[0].get("Title", "").replace("\n", " ").strip().lower()
                            if title_match and title_match.lower() in title:
                                return page_dir.name, pos
                            # Oppure verifica per scorciatoia
                            hk1 = (act.get("Settings") or {}).get("Hotkeys", [{}])[0]
                            # Se native code e modifiers corrispondono a shortcut
                            expected_hk = parse_shortcut_to_hotkey(shortcut)["Hotkeys"][0]
                            if (hk1.get("NativeCode") == expected_hk.get("NativeCode") and
                                hk1.get("KeyModifiers") == expected_hk.get("KeyModifiers")):
                                return page_dir.name, pos
        except Exception:
            pass
    return None


def remove_hotkey_from_page(
    page_uuid: str,
    position: str,
    profiles_root: Path = STUDIO_ONE_PROFILE / "Profiles",
) -> Path:
    """Rimuove l'azione allo slot specificato dal manifest della pagina SD (con backup).

    Restituisce il Path del backup creato.
    """
    manifest_path = profiles_root / page_uuid.upper() / "manifest.json"
    if not manifest_path.exists():
        manifest_path = profiles_root / page_uuid.lower() / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest.json non trovato per la pagina SD '{page_uuid}'")

    raw_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    keypad = None
    for ctrl in raw_data.get("Controllers", []):
        if ctrl.get("Type") == "Keypad":
            keypad = ctrl
            break

    if keypad is None:
        raise DeckWriterError(f"Nessun controller Keypad trovato in {manifest_path.name}")

    actions = keypad.get("Actions", {})
    if position not in actions:
        raise DeckWriterError(f"Nessuna azione trovata nello slot '{position}' della pagina '{page_uuid}'.")

    # Controlla se c'era un'immagine associata all'azione
    action_data = actions[position]
    image_rel = None
    states = action_data.get("States", [])
    if states and isinstance(states, list):
        image_rel = states[0].get("Image")

    # Backup preventivo
    backup_path = backup(manifest_path)

    # Rimuovi l'azione liberando lo slot
    del actions[position]

    # Scrittura atomica
    temp_path = manifest_path.parent / f".{manifest_path.name}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, manifest_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise DeckWriterError(f"Errore durante la rimozione dello slot in manifest.json: {exc}") from exc

    # Se la scrittura del manifest ha avuto successo e c'era un'immagine, cancellala
    if image_rel:
        is_shared = any(
            act.get("States", [{}])[0].get("Image") == image_rel
            for act in actions.values()
            if isinstance(act, dict)
        )
        if not is_shared:
            image_file = manifest_path.parent / image_rel
            if image_file.exists():
                try:
                    image_file.unlink(missing_ok=True)
                except Exception:
                    pass

    return backup_path


