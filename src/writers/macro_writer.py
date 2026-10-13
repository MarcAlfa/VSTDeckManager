"""Writer per file .studioonemacro di Fender Studio Pro / Studio One.

Specifiche tecniche obbligatorie verificate dai file originali:
- Encoding UTF-8 CON BOM (byte EF BB BF all'inizio del file)
- Terminatori di riga CRLF (\r\n)
- Indentazione con tabulazione (\t)
- Struttura:
    * FX: Add Insert to Selected Channels (con cid=GUID, mode=1, preset=default, openEditor=0/1)
          + Show Channel Editor (State=1)
    * Instrument: Load Track Preset (con Name=preset_name)
          + Show Instrument Editor (State=1)
          + Monitor (State=1)
"""
from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape

from src.core.config import MACROS_DIR, MACRO_GROUP, MACRO_PREFIX
from src.core.backup import backup


class MacroWriterError(Exception):
    """Errore durante la generazione o scrittura del file macro."""
    pass


def build_macro_xml(
    title: str,
    description: str = "",
    guid: str = "",
    macro_type: str = "effect",
    preset_name: str = "",
    open_editor: bool = False,
    group: str = MACRO_GROUP,
) -> str:
    """Genera la stringa XML completa pronta per essere scritta, con tabulazioni e CRLF."""
    title_esc = escape(title)
    group_esc = escape(group)
    desc_esc = escape(description)

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Macro title="{title_esc}" group="{group_esc}" description="{desc_esc}">',
    ]

    if macro_type == "effect":
        if not guid:
            raise MacroWriterError("GUID obbligatorio per macro di tipo effect.")
        guid_esc = escape(guid)
        open_val = "1" if open_editor else "0"
        lines.extend([
            '\t<CommandElement category="Track" name="Add Insert to Selected Channels">',
            '\t\t<CommandArgument name="mode" value="1"/>',
            f'\t\t<CommandArgument name="cid" value="{guid_esc}"/>',
            '\t\t<CommandArgument name="preset" value="default"/>',
            f'\t\t<CommandArgument name="openEditor" value="{open_val}"/>',
            '\t</CommandElement>',
            '\t<CommandElement category="Console" name="Show Channel Editor">',
            '\t\t<CommandArgument name="State" value="1"/>',
            '\t</CommandElement>',
        ])
    elif macro_type == "instrument":
        name = preset_name or title.removeprefix(MACRO_PREFIX)
        name_esc = escape(name)
        lines.extend([
            '\t<CommandElement category="Track" name="Load Track Preset">',
            f'\t\t<CommandArgument name="Name" value="{name_esc}"/>',
            '\t</CommandElement>',
            '\t<CommandElement category="Console" name="Show Instrument Editor">',
            '\t\t<CommandArgument name="State" value="1"/>',
            '\t</CommandElement>',
            '\t<CommandElement category="Track" name="Monitor">',
            '\t\t<CommandArgument name="State" value="1"/>',
            '\t</CommandElement>',
        ])
    else:
        raise MacroWriterError(f"Tipo macro non supportato: '{macro_type}'. Usa 'effect' o 'instrument'.")

    lines.append('</Macro>\r\n')
    return "\r\n".join(lines[:-1]) + "\r\n" + lines[-1]


def write_macro_file(
    title: str,
    description: str = "",
    guid: str = "",
    macro_type: str = "effect",
    preset_name: str = "",
    open_editor: bool = False,
    group: str = MACRO_GROUP,
    macros_dir: Path = MACROS_DIR,
    overwrite: bool = False,
) -> Path:
    """Scrive in modo sicuro il file .studioonemacro su disco.

    Garantisce:
    1. Nome file valido con estensione .studioonemacro
    2. Se overwrite=False e il file esiste, blocca l'operazione
    3. Se overwrite=True e il file esiste, esegue preventivamente il backup con timestamp
    4. Scrittura atomica via file temporaneo con UTF-8 BOM esplicito
    """
    if not title:
        raise MacroWriterError("Il titolo della macro non può essere vuoto.")

    if not macros_dir or not macros_dir.exists():
        raise MacroWriterError(f"The configured Macros directory does not exist: {macros_dir}")

    filename = f"{title}.studioonemacro"
    target_path = macros_dir / filename

    if target_path.exists():
        if not overwrite:
            raise FileExistsError(
                f"Il file macro '{filename}' esiste già in {macros_dir}. Operazione bloccata per sicurezza."
            )
        # Se sovrascrive esplicitamente, fa prima il backup
        backup(target_path)

    xml_content = build_macro_xml(
        title=title,
        description=description,
        guid=guid,
        macro_type=macro_type,
        preset_name=preset_name,
        open_editor=open_editor,
        group=group,
    )

    macros_dir.mkdir(parents=True, exist_ok=True)
    temp_path = macros_dir / f".{filename}.tmp"

    try:
        # EF BB BF = UTF-8 BOM
        bom = b"\xef\xbb\xbf"
        encoded_content = xml_content.encode("utf-8")
        with open(temp_path, "wb") as f:
            f.write(bom)
            f.write(encoded_content)

        # Rimpiazzo atomico del file target
        os.replace(temp_path, target_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise MacroWriterError(f"Impossibile scrivere il file macro: {exc}") from exc

    return target_path


def delete_macro_file(
    title: str,
    macros_dir: Path = MACROS_DIR,
) -> Path | None:
    """Elimina in sicurezza il file .studioonemacro facendone prima il backup in backups/.

    Restituisce il Path del backup creato se il file esisteva ed e' stato rimosso, altrimenti None.
    """
    if not title:
        raise MacroWriterError("Titolo macro non specificato per l'eliminazione.")

    filename = f"{title}.studioonemacro"
    target_path = macros_dir / filename

    if not target_path.exists():
        return None

    # Backup di sicurezza prima di cancellare
    backup_path = backup(target_path)
    target_path.unlink()
    return backup_path

