"""VSTDeckManager — finestra principale: libreria plugin."""
import customtkinter as ctk

from src.core.config import CFG, VERSION
from src.core.win32_utils import get_hwnd, save_window_state, restore_window_position
from src.parsers import plugins_catalog
from src.gui.panel_library import PanelLibrary
from src.gui.widgets import tooltip as _tooltip

_VERSION     = VERSION
_YELLOW      = "#c8a838"
_DEFAULT_GEO = "1380x880"


class App(ctk.CTk):

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        super().__init__()

        self.title(f"VSTDeckManager  v{_VERSION}")
        self.resizable(False, False)
        self.geometry(_DEFAULT_GEO)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        catalog = plugins_catalog.by_guid()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self._panel_lib = PanelLibrary(self, catalog)
        self._panel_lib.grid(row=0, column=0, sticky="nsew")

        # Status bar
        bar = ctk.CTkFrame(self, fg_color="transparent", height=32)
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(2, 6))
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_propagate(False)

        self._catalog_label = ctk.CTkLabel(
            bar,
            text=f"Catalog: {len(catalog)} plugins",
            font=ctk.CTkFont(size=11),
            text_color=_YELLOW,
            anchor="w",
        )
        self._catalog_label.grid(row=0, column=0, sticky="w")

        _btn_kw = dict(width=32, height=26, corner_radius=6,
                       fg_color="#1e1e2e", hover_color="#2e2e4e",
                       font=ctk.CTkFont(size=14))

        self._deck_win     = None
        self._macro_win    = None
        self._settings_win = None
        self._about_win    = None

        btn_macro = ctk.CTkButton(bar, text="⚙", **_btn_kw, command=self._open_macro_editor)
        btn_macro.grid(row=0, column=1, padx=(8, 2))
        _tooltip(btn_macro, "Macro Editor")

        btn_deck = ctk.CTkButton(bar, text="🎛", **_btn_kw, command=self._open_deck)
        btn_deck.grid(row=0, column=2, padx=2)
        _tooltip(btn_deck, "Stream Deck Map")

        btn_opt = ctk.CTkButton(bar, text="🛠", **_btn_kw, command=self._open_settings)
        btn_opt.grid(row=0, column=3, padx=2)
        _tooltip(btn_opt, "Settings")

        btn_about = ctk.CTkButton(bar, text="ℹ", **_btn_kw, command=self._open_about)
        btn_about.grid(row=0, column=4, padx=(2, 0))
        _tooltip(btn_about, "About")

        self.update()
        restore_window_position(get_hwnd(self), "window_state")

        # Controlla al primo avvio se la configurazione è valida
        self.after(350, self._check_first_run)

    def _check_first_run(self):
        from src.core.config import is_configured
        if not is_configured():
            self._open_settings(welcome=True)

    def _open_about(self):
        if self._about_win is not None and self._about_win.winfo_exists():
            self._about_win.lift()
            self._about_win.focus_force()
            return
        from src.gui.about_dialog import AboutDialog
        self._about_win = AboutDialog(self)

    def _open_settings(self, welcome: bool = False):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        from src.gui.settings_dialog import SettingsDialog
        self._settings_win = SettingsDialog(self, welcome=welcome, on_saved=self._on_settings_saved)

    def _on_settings_saved(self):
        from src.core.config import reload_config, is_configured
        reload_config()
        catalog = plugins_catalog.by_guid(force_refresh=True)
        self._catalog_label.configure(text=f"Catalog: {len(catalog)} plugins")
        if hasattr(self._panel_lib, "_catalog"):
            self._panel_lib._catalog = catalog
            if hasattr(self._panel_lib, "_filter_and_render"):
                self._panel_lib._filter_and_render()

    def _show_path_warning(self, title: str, message: str):
        from src.gui.widgets import center_over_parent
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.resizable(False, False)
        center_over_parent(dlg, self, 480, 180)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="⚠ " + title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#e0a030",
        ).pack(pady=(16, 6))

        ctk.CTkLabel(
            dlg, text=message,
            font=ctk.CTkFont(size=11),
            text_color="#cccccc",
            wraplength=440,
            justify="center",
        ).pack(pady=(0, 16), padx=20)

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=(0, 12))

        ctk.CTkButton(
            btn_row, text="Cancel", width=90, height=30,
            fg_color="#2a2a3a", hover_color="#3a3a4a",
            command=dlg.destroy,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            btn_row, text="Open Settings 🛠", width=130, height=30,
            fg_color="#c8a838", hover_color="#dfbd47", text_color="#111116",
            command=lambda: (dlg.destroy(), self._open_settings()),
        ).pack(side="left", padx=6)

    def _open_macro_editor(self):
        """Apre la finestra editor macro come Toplevel separato."""
        from src.core.config import MACROS_DIR, KEYSCHEME
        if not MACROS_DIR.is_dir():
            self._show_path_warning(
                "Macros Folder Not Found",
                f"The configured Macros folder does not exist:\n{MACROS_DIR}\nPlease set a valid folder in Settings."
            )
            return

        if not KEYSCHEME.is_file():
            self._show_path_warning(
                "Keyscheme File Not Found",
                f"The configured user.keyscheme file does not exist:\n{KEYSCHEME}\nPlease set a valid file in Settings."
            )
            return

        if self._macro_win is not None and self._macro_win.winfo_exists():
            self._macro_win.lift()
            self._macro_win.focus_force()
            return
        from src.gui.macro_editor import MacroEditorWindow
        self._macro_win = MacroEditorWindow(self)

    def _open_deck(self):
        """Apre la finestra mappa Stream Deck come Toplevel separato."""
        from src.core.config import STUDIO_ONE_PROFILE
        if not STUDIO_ONE_PROFILE.is_dir() or not (STUDIO_ONE_PROFILE / "manifest.json").exists():
            self._show_path_warning(
                "Stream Deck Profile Not Found",
                f"The Stream Deck profile was not found at:\n{STUDIO_ONE_PROFILE}\nPlease check your Profiles root and Profile UUID in Settings."
            )
            return

        if self._deck_win is not None and self._deck_win.winfo_exists():
            self._deck_win.lift()
            self._deck_win.focus_force()
            return
        from src.gui.window_deck import DeckMapWindow
        self._deck_win = DeckMapWindow(self)

    def _on_close(self):
        self.update_idletasks()
        save_window_state(get_hwnd(self), "window_state")
        self.destroy()
