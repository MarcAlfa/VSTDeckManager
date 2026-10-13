"""Backup automatico prima di ogni scrittura."""
import shutil
from datetime import datetime
from pathlib import Path

from src.core.config import BACKUP_DIR


def backup(file_path: Path) -> Path:
    """Copia file_path in BACKUP_DIR con timestamp. Restituisce il path del backup."""
    if not file_path.exists():
        raise FileNotFoundError(f"File da backuppare non trovato: {file_path}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{file_path.stem}_{ts}{file_path.suffix}"
    shutil.copy2(file_path, dest)
    return dest
