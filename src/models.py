"""Dataclass condivisi tra parser, writer e GUI."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Plugin:
    """Plugin dal catalogo Plugins-en.settings."""
    guid: str          # classID con graffe, es. "{B1907A66-...}"
    name: str          # nome leggibile, es. "AirEQ Premium"
    category: str      # "AudioEffect" o "Instrument"
    sub_category: str  # es. "(Native)/EQ", "Reverb", "Dynamics/Compressor"
    vendor: str = ""   # produttore, es. "FabFilter", "Waves"


@dataclass
class Macro:
    """Macro SdR da file .studioonemacro."""
    title: str                    # es. "SdR_AirEQP"
    guid: str                     # classID con graffe (es. "{B1907A66-...}"), vuoto per strumenti
    description: str              # testo libero
    open_editor: bool             # True = apre GUI plugin dopo inserimento
    file_path: str                # path assoluto del file .studioonemacro
    macro_type: str = "effect"    # "effect" = Add Insert + cid | "instrument" = Load Track Preset
    preset_name: str = ""         # usato solo per macro_type="instrument" (es. "Kontakt8")


@dataclass
class Assignment:
    """Unione di Macro + shortcut + posizione SD (stato completo di un plugin)."""
    macro: Macro
    plugin: Optional[Plugin]     # None se il GUID non e' nel catalogo
    shortcut: Optional[str]      # es. "Ctrl+Shift+Alt+Q", None se non assegnato
    sd_category: Optional[str]   # es. "EQ", None se non in SD
    sd_position: Optional[str]   # es. "1,0", None se non in SD
    sd_title: Optional[str]      # titolo sul tasto SD, es. "AirEQ\nPremium"
