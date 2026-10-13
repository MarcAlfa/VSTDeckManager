"""Scansiona la cartella macro e legge tutte le macro {MACRO_PREFIX}*.studioonemacro."""
from pathlib import Path
from xml.etree import ElementTree as ET

from src.core.config import MACROS_DIR, MACRO_PREFIX
from src.models import Macro


def load(macros_dir: Path = MACROS_DIR) -> list[Macro]:
    """
    Legge tutti i file {MACRO_PREFIX}*.studioonemacro nella cartella macro
    (prefisso da config.json -> fsp.macro_prefix, default "SdR_").
    I file hanno BOM UTF-8: ET.parse lo gestisce automaticamente.
    Restituisce lista di Macro ordinata per title.
    """
    macros: list[Macro] = []
    if not macros_dir or not macros_dir.exists():
        return macros

    for path in sorted(macros_dir.glob(f"{MACRO_PREFIX}*.studioonemacro")):
        macro = _parse_file(path)
        if macro:
            macros.append(macro)

    return macros


def _parse_file(path: Path) -> Macro | None:
    """
    Parsa un singolo file .studioonemacro. Restituisce None se non valido.

    Due strutture supportate:
      - effect:     CommandElement "Add Insert to Selected Channels" con cid -> guid
      - instrument: CommandElement "Load Track Preset" con Name -> preset_name
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()

        title = root.get("title", "").strip()
        description = root.get("description", "").strip()

        if not title:
            return None

        # Cerca il comando principale per determinare il tipo
        command_names = [el.get("name", "") for el in root.iter("CommandElement")]

        if "Add Insert to Selected Channels" in command_names:
            # Macro effect: cerca cid e openEditor
            guid = ""
            open_editor = False
            for arg in root.iter("CommandArgument"):
                if arg.get("name") == "cid":
                    guid = arg.get("value", "").strip()
                if arg.get("name") == "openEditor":
                    open_editor = arg.get("value", "0") == "1"
            if not guid:
                return None
            return Macro(
                title=title,
                guid=guid,
                description=description,
                open_editor=open_editor,
                file_path=str(path),
                macro_type="effect",
            )

        elif "Load Track Preset" in command_names:
            # Macro instrument: cerca Name del preset
            preset_name = ""
            for arg in root.iter("CommandArgument"):
                if arg.get("name") == "Name":
                    preset_name = arg.get("value", "").strip()
                    break
            return Macro(
                title=title,
                guid="",
                description=description,
                open_editor=False,
                file_path=str(path),
                macro_type="instrument",
                preset_name=preset_name,
            )

        return None  # struttura sconosciuta

    except ET.ParseError:
        return None


def by_guid(macros_dir: Path = MACROS_DIR) -> dict[str, Macro]:
    """Restituisce le macro come dict {guid: Macro} per lookup rapido.

    Le macro instrument (guid vuoto, usano preset_name) sono escluse:
    altrimenti collasserebbero tutte sulla stessa chiave "".
    """
    return {m.guid: m for m in load(macros_dir) if m.guid}


def by_title(macros_dir: Path = MACROS_DIR) -> dict[str, Macro]:
    """Restituisce le macro come dict {title: Macro} per lookup rapido."""
    return {m.title: m for m in load(macros_dir)}
