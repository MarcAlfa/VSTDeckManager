"""Writer sicuro per aggiungere scorciatoie in user.keyscheme di Fender Studio Pro / Studio One.

Caratteristiche e tutele:
- Encoding UTF-8 CON BOM (identico al file originale di FSP)
- Terminatori di riga CRLF (\r\n) e indentazione a tabulazione (\t)
- Codifica del nome comando: 'Macro ' + base64(titolo_macro)
- Sicurezza:
    1. Backup automatico con timestamp prima di qualsiasi modifica
    2. Verifica che la shortcut o il comando non siano già presenti in conflitto
    3. Scrittura atomica via file temporaneo
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from src.core.config import KEYSCHEME
from src.core.backup import backup


class KeyschemeWriterError(Exception):
    """Errore durante la modifica di user.keyscheme."""
    pass


def encode_macro_command_name(macro_title: str) -> str:
    """Restituisce il nome comando come salvato in keyscheme: 'Macro ' + base64(titolo)."""
    b64 = base64.b64encode(macro_title.encode("utf-8")).decode("ascii")
    return f"Macro {b64}"


def decode_macro_command_name(command_name: str) -> str | None:
    """Decodifica un nome comando 'Macro BASE64' nel titolo originale."""
    if not command_name.startswith("Macro "):
        return None
    raw_b64 = command_name[6:].strip()
    try:
        return base64.b64decode(raw_b64).decode("utf-8")
    except Exception:
        return None


def add_macro_shortcut(
    macro_title: str,
    shortcut: str,
    keyscheme_path: Path = KEYSCHEME,
    allow_overwrite_shortcut: bool = False,
) -> Path:
    """Aggiunge in modo sicuro la scorciatoia per la macro specificata nel file user.keyscheme.

    1. Esegue il backup di keyscheme_path in backups/.
    2. Controlla che il comando macro o lo shortcut non siano già occupati.
    3. Inserisce il blocco XML mantenendo formattazione, tabulazioni e CRLF.
    4. Salva in modo atomico.
    """
    if not keyscheme_path.exists():
        raise FileNotFoundError(f"File keyscheme non trovato: {keyscheme_path}")

    if not macro_title:
        raise KeyschemeWriterError("Titolo macro non specificato.")
    if not shortcut:
        raise KeyschemeWriterError("Scorciatoia non specificata.")

    # Legge il contenuto raw mantenendo encoding
    raw_bytes = keyscheme_path.read_bytes()
    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
    text = raw_bytes[3:].decode("utf-8") if has_bom else raw_bytes.decode("utf-8")

    cmd_name = encode_macro_command_name(macro_title)

    # 1. Controllo se il comando esiste già
    cmd_pattern = re.compile(rf'<Command\s+category="Macros"\s+name="{re.escape(cmd_name)}"', re.IGNORECASE)
    if cmd_pattern.search(text):
        raise KeyschemeWriterError(f"La macro '{macro_title}' ha già un comando definito in {keyscheme_path.name}.")

    # 2. Controllo se la scorciatoia è già assegnata a un altro comando
    key_pattern = re.compile(rf'<Key\s+name="{re.escape(shortcut)}"\s*/>', re.IGNORECASE)
    if key_pattern.search(text) and not allow_overwrite_shortcut:
        raise KeyschemeWriterError(
            f"La scorciatoia '{shortcut}' è già utilizzata in {keyscheme_path.name}. Operazione annullata per sicurezza."
        )

    # Backup obbligatorio prima di toccare qualsiasi cosa
    backup_path = backup(keyscheme_path)

    # 3. Costruzione del blocco XML da inserire
    cmd_name_esc = escape(cmd_name)
    shortcut_esc = escape(shortcut)
    new_block = (
        f"\t<Command category=\"Macros\" name=\"{cmd_name_esc}\">\r\n"
        f"\t\t<Key name=\"{shortcut_esc}\"/>\r\n"
        f"\t</Command>\r\n"
    )

    # 4. Inserimento: cerchiamo l'ultimo blocco di categoria "Macros" per mantenerli raggruppati,
    # altrimenti prima della chiusura </Commands>
    last_macro_pos = -1
    for m in re.finditer(r'<Command\s+category="Macros"[^>]*>(?:.*?</Command>|/>)', text, re.DOTALL):
        last_macro_pos = m.end()

    if last_macro_pos != -1:
        # Inserisci subito dopo l'ultima macro trovata
        # Trova la fine della riga dopo last_macro_pos
        crlf_pos = text.find("\r\n", last_macro_pos)
        if crlf_pos != -1:
            insert_idx = crlf_pos + 2
        else:
            insert_idx = last_macro_pos
        updated_text = text[:insert_idx] + new_block + text[insert_idx:]
    else:
        # Fallback: inserisci subito prima di </Commands>
        close_tag = "</Commands>"
        close_idx = text.rfind(close_tag)
        if close_idx == -1:
            raise KeyschemeWriterError("Tag di chiusura </Commands> non trovato nel file keyscheme.")
        updated_text = text[:close_idx] + new_block + text[close_idx:]

    # 5. Scrittura atomica su file temporaneo
    temp_path = keyscheme_path.parent / f".{keyscheme_path.name}.tmp"
    try:
        bom = b"\xef\xbb\xbf" if has_bom else b""
        with open(temp_path, "wb") as f:
            f.write(bom)
            f.write(updated_text.encode("utf-8"))

        os.replace(temp_path, keyscheme_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise KeyschemeWriterError(f"Errore durante il salvataggio atomico di keyscheme: {exc}") from exc

    return backup_path


def remove_macro_shortcut(
    macro_title: str,
    keyscheme_path: Path = KEYSCHEME,
) -> Path | None:
    """Rimuove in sicurezza la definizione del comando Macro da user.keyscheme, facendo prima il backup.

    Restituisce il Path del backup creato se il comando era presente ed e' stato rimosso, altrimenti None.
    """
    if not keyscheme_path.exists():
        raise FileNotFoundError(f"File keyscheme non trovato: {keyscheme_path}")

    if not macro_title:
        raise KeyschemeWriterError("Titolo macro non specificato per la rimozione.")

    raw_bytes = keyscheme_path.read_bytes()
    has_bom = raw_bytes.startswith(b"\xef\xbb\xbf")
    text = raw_bytes[3:].decode("utf-8") if has_bom else raw_bytes.decode("utf-8")

    cmd_name = encode_macro_command_name(macro_title)

    # Cerca il blocco intero: <Command category="Macros" name="Macro BASE64"> ... </Command>\r\n (oppure inline />)
    pattern = re.compile(
        rf'\t*<Command\s+category="Macros"\s+name="{re.escape(cmd_name)}"[^>]*>.*?</Command>\r?\n?'
        rf'|\t*<Command\s+category="Macros"\s+name="{re.escape(cmd_name)}"[^>]*/>\r?\n?',
        re.DOTALL | re.IGNORECASE
    )

    if not pattern.search(text):
        return None

    # Backup prima della modifica
    backup_path = backup(keyscheme_path)

    updated_text = pattern.sub("", text)

    # Scrittura atomica
    temp_path = keyscheme_path.parent / f".{keyscheme_path.name}.tmp"
    try:
        bom = b"\xef\xbb\xbf" if has_bom else b""
        with open(temp_path, "wb") as f:
            f.write(bom)
            f.write(updated_text.encode("utf-8"))

        os.replace(temp_path, keyscheme_path)
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise KeyschemeWriterError(f"Errore durante la rimozione da keyscheme: {exc}") from exc

    return backup_path

