"""Finestra Macro Editor (Toplevel aperta dal pulsante ⚙ della Libreria)."""
import customtkinter as ctk

from src.core.win32_utils import get_hwnd, save_window_state, restore_window_position
from src.parsers import macro_scanner
from src.parsers import plugins_catalog
from src.gui.panel_current import PanelCurrent
from src.gui.panel_add import PanelAdd
from src.gui.widgets import tooltip

_YELLOW = "#c8a838"


class MacroEditorWindow(ctk.CTkToplevel):
    """Wrapper Toplevel per il macro editor (ex finestra principale)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"Macro Editor — VSTDeckManager")
        self.resizable(False, False)
        self.geometry("1280x700")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        catalog = plugins_catalog.by_guid()
        macros  = macro_scanner.load()

        self.grid_columnconfigure(0, weight=0, minsize=500)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self._panel_current = PanelCurrent(self, macros, catalog)
        self._panel_current.grid(
            row=0, column=0, sticky="nsew", padx=(12, 5), pady=(12, 5)
        )
        self._panel_add = PanelAdd(self, catalog, macros)
        self._panel_add.grid(
            row=0, column=1, sticky="nsew", padx=(5, 12), pady=(12, 5)
        )

        # Status bar
        n_effect = sum(1 for m in macros if m.macro_type == "effect")
        n_instr  = sum(1 for m in macros if m.macro_type == "instrument")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 8))
        bar.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            bar,
            text=(
                f"Catalog: {len(catalog)} plugins  |  "
                f"Active macros: {len(macros)}  "
                f"({n_effect} effects · {n_instr} instruments)"
            ),
            font=ctk.CTkFont(size=11),
            text_color=_YELLOW,
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        _btn_kw = dict(width=32, height=26, corner_radius=6,
                       fg_color="#1e1e2e", hover_color="#2e2e4e",
                       font=ctk.CTkFont(size=14))

        self._about_win = None
        btn_about = ctk.CTkButton(bar, text="ℹ", **_btn_kw, command=self._open_about)
        btn_about.grid(row=0, column=1, padx=(8, 0))
        tooltip(btn_about, "About")

        self.update()
        restore_window_position(get_hwnd(self), "macro_editor_state")

        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    def reload_data(self):
        """Ricarica le macro e aggiorna PanelCurrent e la barra di stato."""
        macros = macro_scanner.load()
        catalog = plugins_catalog.by_guid()
        self._panel_current.reload(macros)
        self._panel_add.reload_macros(macros)

        n_effect = sum(1 for m in macros if m.macro_type == "effect")
        n_instr  = sum(1 for m in macros if m.macro_type == "instrument")
        self._status_label.configure(
            text=(
                f"Catalog: {len(catalog)} plugins  |  "
                f"Active macros: {len(macros)}  "
                f"({n_effect} effects · {n_instr} instruments)"
            )
        )

    def _open_about(self):
        if self._about_win is not None and self._about_win.winfo_exists():
            self._about_win.lift()
            self._about_win.focus_force()
            return
        from src.gui.about_dialog import AboutDialog
        self._about_win = AboutDialog(self)

    def _on_close(self):
        self.update_idletasks()
        save_window_state(get_hwnd(self), "macro_editor_state")
        self.destroy()
