"""Dialogo Opzioni — modifica config.json (esclusi version e window_state)."""
from __future__ import annotations

import json
import tkinter as tk
import customtkinter as ctk
from pathlib import Path

from src.core.config import _CONFIG_FILE   # path al file
from src.gui.widgets import center_over_parent

_YELLOW = "#c8a838"

# Chiavi da non mostrare/modificare
_SKIP_APP_KEYS = {"window_state", "macro_editor_state", "deck_window_state"}

# Definizione campi: (sezione_json, chiave, label, is_path)
_FIELDS = [
    # FSP
    ("fsp", "config_root",           "FSP config root",        True),
    ("fsp", "macros_dir",            "Macros folder",          True),
    ("fsp", "plugins_catalog",       "Plugin catalog",         True),
    ("fsp", "plugin_presentation",   "Plugin presentation",    True),
    ("fsp", "keyscheme",             "Key scheme",             True),
    ("fsp", "snapshots_dir",         "Snapshots folder",       True),
    ("fsp", "macro_group",           "Macro group",            False),
    ("fsp", "macro_prefix",          "Macro prefix",           False),
    # Stream Deck
    ("streamdeck", "profiles_root",            "Stream Deck profiles",      True),
    ("streamdeck", "studio_one_profile_uuid",  "Studio One profile UUID",   False),
    # App
    ("app", "backup_dir", "Backup folder", False),
]

_SECTIONS = {
    "fsp":        "Studio One / FSP",
    "streamdeck": "Stream Deck",
    "app":        "App",
}


class SettingsDialog(ctk.CTkToplevel):

    def __init__(self, parent, welcome: bool = False, on_saved: callable = None):
        super().__init__(parent)
        self.title("Settings — VSTDeckManager")
        self.resizable(False, False)
        center_over_parent(self, parent, 860, 600)
        self.grab_set()

        self._welcome = welcome
        self._on_saved = on_saved
        self._entries: dict[tuple, ctk.CTkEntry] = {}   # (section, key) → entry
        self._status_labels: dict[tuple, ctk.CTkLabel] = {}  # (section, key) → label
        self._cfg = self._load_cfg()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build()

        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    # ---------------------------------------------------------------- build

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(1, weight=1)

        f_title  = ctk.CTkFont(size=13, weight="bold")
        f_label  = ctk.CTkFont(size=11)
        f_small  = ctk.CTkFont(size=10)
        f_status = ctk.CTkFont(size=10, weight="bold")

        r = 0

        # Welcome banner se primo avvio o setup incompleto
        if self._welcome:
            banner = ctk.CTkFrame(scroll, fg_color="#1e1e14", border_color=_YELLOW, border_width=1, corner_radius=8)
            banner.grid(row=r, column=0, columnspan=4, sticky="ew", padx=16, pady=(12, 8))
            ctk.CTkLabel(
                banner,
                text="👋 Welcome to VSTDeckManager!\nPlease configure your Fender Studio Pro / Studio One paths and Stream Deck Profile UUID below.",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=_YELLOW,
                justify="left",
            ).pack(padx=14, pady=10, anchor="w")
            r += 1

        current_section = None

        for section, key, label, is_path in _FIELDS:
            # Intestazione di sezione
            if section != current_section:
                current_section = section
                ctk.CTkLabel(
                    scroll,
                    text=_SECTIONS.get(section, section).upper(),
                    font=f_title, text_color=_YELLOW, anchor="w",
                ).grid(row=r, column=0, columnspan=4, sticky="w",
                       padx=16, pady=(16 if r > 0 else 10, 4))
                r += 1

                ctk.CTkFrame(scroll, height=1, fg_color="#2a2a3a").grid(
                    row=r, column=0, columnspan=4, sticky="ew", padx=16, pady=(0, 8)
                )
                r += 1

            # Label + Entry + Browse + Status
            ctk.CTkLabel(
                scroll, text=label, anchor="w",
                font=f_label, text_color="#9a9aaa", width=160,
            ).grid(row=r, column=0, sticky="w", padx=(16, 8), pady=3)

            value = self._cfg.get(section, {}).get(key, "")
            entry = ctk.CTkEntry(scroll, font=f_label, height=28)
            entry.insert(0, str(value))
            entry.grid(row=r, column=1, sticky="ew", padx=(0, 4), pady=3)
            self._entries[(section, key)] = entry

            if is_path:
                ctk.CTkButton(
                    scroll, text="…", width=30, height=28,
                    fg_color="#1e1e2e", hover_color="#2e2e4e",
                    font=ctk.CTkFont(size=13),
                    command=lambda e=entry, k=key, s=section: self._browse(e, s, k),
                ).grid(row=r, column=2, padx=(0, 6), pady=3)
            else:
                ctk.CTkLabel(scroll, text="", width=30).grid(row=r, column=2, padx=(0, 6))

            # Status indicator label
            status_lbl = ctk.CTkLabel(scroll, text="—", font=f_status, width=76, anchor="w")
            status_lbl.grid(row=r, column=3, padx=(0, 16), pady=3, sticky="w")
            self._status_labels[(section, key)] = status_lbl

            # Check status immediato e su digitazione
            entry.bind("<KeyRelease>", lambda evt, s=section, k=key, ip=is_path: self._update_status(s, k, ip))
            self._update_status(section, key, is_path)

            r += 1

        # Bottom bar
        bot = ctk.CTkFrame(self, fg_color="#0d0d16", corner_radius=0, height=54)
        bot.grid(row=1, column=0, sticky="ew")
        bot.grid_columnconfigure(0, weight=1)
        bot.grid_propagate(False)

        ctk.CTkLabel(
            bot,
            text="⚠  Some changes require an app restart to take full effect.",
            font=ctk.CTkFont(size=11), text_color="#888855", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16)

        ctk.CTkButton(
            bot, text="Cancel", width=90, height=32,
            fg_color="#2a2a3a", hover_color="#3a3a4a",
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 6), pady=10)

        ctk.CTkButton(
            bot, text="Save", width=90, height=32,
            fg_color="#1f5a1f", hover_color="#2a7a2a",
            command=self._save,
        ).grid(row=0, column=2, padx=(0, 16), pady=10)

    # ---------------------------------------------------------------- validation & status

    def _update_status(self, section: str, key: str, is_path: bool):
        lbl = self._status_labels.get((section, key))
        if not lbl:
            return
        entry = self._entries.get((section, key))
        if not entry:
            return
        val = entry.get().strip()

        if not val:
            lbl.configure(text="—", text_color="#666677")
            return

        if is_path:
            p = Path(val)
            is_file_target = key in ("plugins_catalog", "plugin_presentation", "keyscheme")
            if is_file_target:
                valid = p.is_file()
            else:
                valid = p.is_dir()

            if valid:
                lbl.configure(text="✓ Found", text_color="#55cc55")
            else:
                lbl.configure(text="✗ Missing", text_color="#ee5555")
        elif key == "studio_one_profile_uuid":
            prof_root_entry = self._entries.get(("streamdeck", "profiles_root"))
            prof_root_str = prof_root_entry.get().strip() if prof_root_entry else ""
            if prof_root_str:
                sd_path = Path(prof_root_str) / f"{val}.sdProfile"
                if sd_path.is_dir() and (sd_path / "manifest.json").exists():
                    lbl.configure(text="✓ Found", text_color="#55cc55")
                else:
                    lbl.configure(text="✗ Missing", text_color="#ee5555")
            else:
                lbl.configure(text="—", text_color="#666677")
        else:
            lbl.configure(text="", text_color="#666677")

    # ---------------------------------------------------------------- browse

    def _browse(self, entry: ctk.CTkEntry, section: str, key: str):
        from tkinter import filedialog
        current = entry.get().strip()
        init_dir = str(Path(current).parent) if current else "/"

        # File o directory?
        if key in ("plugins_catalog", "plugin_presentation", "keyscheme"):
            path = filedialog.askopenfilename(
                initialdir=init_dir,
                title="Select file",
                parent=self,
            )
        else:
            path = filedialog.askdirectory(
                initialdir=init_dir,
                title="Select folder",
                parent=self,
            )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path.replace("/", "\\"))
            self._update_status(section, key, True)
            if key == "profiles_root":
                self._update_status("streamdeck", "studio_one_profile_uuid", False)

    # ---------------------------------------------------------------- save

    def _save(self):
        cfg = self._load_cfg()   # rileggi fresco per non perdere window_state etc.

        changed = False
        for (section, key), entry in self._entries.items():
            new_val = entry.get().strip()
            old_val = str(cfg.get(section, {}).get(key, ""))
            if new_val != old_val:
                cfg.setdefault(section, {})[key] = new_val
                changed = True

        if not changed:
            self.destroy()
            return

        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            from src.core.config import reload_config
            reload_config()

            if self._on_saved:
                self._on_saved()

            self._show_ok()
        except Exception as e:
            self._show_error(str(e))

    def _show_ok(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Saved")
        dlg.geometry("360x120")
        dlg.resizable(False, False)
        dlg.grab_set()
        ctk.CTkLabel(
            dlg,
            text="✓  Settings saved.\nRestart the app to apply all changes.",
            font=ctk.CTkFont(size=12), text_color="#88cc88",
        ).pack(pady=(20, 10))
        ctk.CTkButton(dlg, text="OK", width=80,
                      command=lambda: (dlg.destroy(), self.destroy())).pack()

    def _show_error(self, msg: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Error")
        dlg.geometry("400x140")
        dlg.resizable(False, False)
        dlg.grab_set()
        ctk.CTkLabel(
            dlg, text=f"✗  Save error:\n{msg}",
            font=ctk.CTkFont(size=11), text_color="#cc4444",
        ).pack(pady=(20, 10))
        ctk.CTkButton(dlg, text="Close", width=80, command=dlg.destroy).pack()

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _load_cfg() -> dict:
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
