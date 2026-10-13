"""Pannello sinistro: lista macro esistenti con shortcut dal keyscheme."""
import re
import base64
import customtkinter as ctk

from src.models import Macro, Plugin
from src.core.config import KEYSCHEME, MACRO_PREFIX
from src.writers.macro_writer import delete_macro_file
from src.writers.keyscheme_writer import remove_macro_shortcut
from src.writers.deck_writer import find_hotkey_in_profile, remove_hotkey_from_page
from src.gui.widgets import tooltip as _tooltip

_YELLOW  = "#c8a838"
_COL_W   = {"plugin": 150, "macro": 88, "shortcut": 80, "del": 30}
_BG_FX_EVEN  = "#252c38"
_BG_FX_ODD   = "#1e242e"
_BG_INS_EVEN = "#1d2820"
_BG_INS_ODD  = "#192219"
_COL_FX      = "#ccd8f0"
_COL_INS     = "#88cc88"


def _bind_combo_click(combo: ctk.CTkComboBox) -> ctk.CTkComboBox:
    combo._entry.bind("<Button-1>", lambda e: combo._open_dropdown_menu())
    return combo


def _load_shortcuts() -> tuple[dict[str, str], dict[str, str]]:
    """Legge user.keyscheme e restituisce ({macro_title: shortcut abbreviato}, {macro_title: shortcut originale})."""
    try:
        content = KEYSCHEME.read_text(encoding="utf-8")
        pattern = r'<Command category="Macros" name="Macro ([^"]+)">\s*<Key name="([^"]+)"/>'
        abbrev_res: dict[str, str] = {}
        raw_res: dict[str, str] = {}
        for b64, key in re.findall(pattern, content):
            try:
                title = base64.b64decode(b64).decode()
                abbrev_res[title] = _abbrev(key)
                raw_res[title] = key
            except Exception:
                pass
        return abbrev_res, raw_res
    except Exception:
        return {}, {}



def _abbrev(key: str) -> str:
    """'Ctrl+Shift+Alt+Q' -> 'C+S+A+Q'   'Ctrl+Alt+}' -> 'C+A+}'"""
    return (key
            .replace("Ctrl",  "C")
            .replace("Shift", "S")
            .replace("Alt",   "A"))


class PanelCurrent(ctk.CTkFrame):

    def __init__(self, parent, macros: list[Macro], catalog: dict[str, Plugin]):
        super().__init__(parent, corner_radius=10)
        self._all_macros = macros
        self._catalog    = catalog
        self._shortcuts, self._raw_shortcuts = _load_shortcuts()
        self._rows: list[ctk.CTkFrame] = []

        self._f_title  = ctk.CTkFont(size=13, weight="bold")
        self._f_header = ctk.CTkFont(size=11, weight="bold")
        self._f_row    = ctk.CTkFont(size=12)
        self._f_sub    = ctk.CTkFont(size=11)

        self._filter_var = ctk.StringVar()
        self._filter_var.trace_add("write", self._apply_filter)
        self._type_var = ctk.StringVar(value="All")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_title()
        self._build_filters()
        self._build_header()
        self._build_list()
        self._render_list(self._all_macros)

    # ------------------------------------------------------------------ build

    def _build_title(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        self._title_label = ctk.CTkLabel(
            frame,
            text=f"EXISTING MACROS  ({len(self._all_macros)})",
            font=self._f_title, anchor="w",
        )
        self._title_label.pack(side="left")

    def _build_filters(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            frame, textvariable=self._filter_var,
            placeholder_text="Filter by name...",
            height=30, font=self._f_sub,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        _bind_combo_click(ctk.CTkComboBox(
            frame, variable=self._type_var,
            values=["All", "Effect", "Instrument"],
            width=108, height=30, font=self._f_sub,
            command=self._apply_filter,
            state="readonly",
        )).grid(row=0, column=1)

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=6, height=26)
        hdr.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 3))
        hdr.pack_propagate(False)

        headers = [
            ("plugin", _COL_W["plugin"], "Plugin"),
            ("macro", _COL_W["macro"], "Macro"),
            ("shortcut", _COL_W["shortcut"], "Shortcut"),
            ("del", _COL_W["del"], ""),
        ]

        for key, w, label in headers:
            ctk.CTkLabel(
                hdr,
                text=label,
                width=w,
                font=self._f_header,
                text_color="#7a8aaa",
                anchor="w" if key != "del" else "center",
            ).pack(side="left", padx=(8 if key == "plugin" else 0, 0))

    def _build_list(self):
        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=6)
        self._scroll.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 12))
        self._scroll.grid_columnconfigure(0, weight=1)

    # ----------------------------------------------------------------- filter

    def _apply_filter(self, *args):
        q   = self._filter_var.get().strip().lower()
        typ = self._type_var.get()

        result = self._all_macros
        if typ == "Effect":
            result = [m for m in result if m.macro_type == "effect"]
        elif typ == "Instrument":
            result = [m for m in result if m.macro_type == "instrument"]

        if q:
            def _match(m: Macro) -> bool:
                if q in m.title.lower():
                    return True
                p = self._catalog.get(m.guid)
                return p is not None and q in p.name.lower()
            result = [m for m in result if _match(m)]

        self._render_list(result)

    # ----------------------------------------------------------------- render

    def _render_list(self, macros: list[Macro]):
        for r in self._rows:
            r.destroy()
        self._rows.clear()

        for i, macro in enumerate(macros):
            plugin      = self._catalog.get(macro.guid)
            plugin_name = plugin.name if plugin else macro.title.removeprefix(MACRO_PREFIX)
            macro_short = macro.title.removeprefix(MACRO_PREFIX)
            shortcut    = self._shortcuts.get(macro.title, "—")

            is_instr   = macro.macro_type == "instrument"
            bg         = (_BG_INS_EVEN if is_instr else _BG_FX_EVEN) if i % 2 == 0 \
                         else (_BG_INS_ODD if is_instr else _BG_FX_ODD)
            name_color = _COL_INS if is_instr else _COL_FX

            row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4, height=26)
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_propagate(False)
            self._rows.append(row)

            ctk.CTkLabel(
                row, text=plugin_name, width=_COL_W["plugin"],
                font=self._f_row, text_color=name_color, anchor="w",
            ).pack(side="left", padx=(8, 0))

            ctk.CTkLabel(
                row, text=macro_short, width=_COL_W["macro"],
                font=self._f_sub, text_color="#7a8aaa", anchor="w",
            ).pack(side="left")

            sc_color = _YELLOW if shortcut != "—" else "#555566"
            ctk.CTkLabel(
                row, text=shortcut, width=_COL_W["shortcut"],
                font=self._f_sub, text_color=sc_color, anchor="w",
            ).pack(side="left")

            # Pulsante cancellazione assegnazione
            btn_del = ctk.CTkButton(
                row, text="✕", width=22, height=20,
                corner_radius=4, fg_color="#3a2020", hover_color="#662222",
                text_color="#ff7777", font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda m=macro, pn=plugin_name: self._confirm_delete(m, pn)
            )
            btn_del.pack(side="right", padx=(0, 6))
            _tooltip(btn_del, f"Delete macro and shortcuts for {plugin_name}")

    def _confirm_delete(self, macro: Macro, plugin_name: str):
        raw_shortcut = self._raw_shortcuts.get(macro.title, "")
        shortcut_display = raw_shortcut or "None"

        # Controlla se la macro ha un tasto Stream Deck
        sd_info = None
        if raw_shortcut:
            sd_info = find_hotkey_in_profile(raw_shortcut, title_match=macro.title.removeprefix(MACRO_PREFIX))

        sd_text = f"Yes (Page: {sd_info[0][:8]}..., Slot: {sd_info[1]})" if sd_info else "No button found (or not mapped)"

        msg = (
            f"Are you sure you want to delete this assignment?\n\n"
            f"• Plugin:        {plugin_name}\n"
            f"• Macro File:    {macro.title}.studioonemacro\n"
            f"• Shortcut:      {shortcut_display} in user.keyscheme\n"
            f"• Stream Deck:   {sd_text}\n\n"
            f"Actions performed:\n"
            f"  1. Delete .studioonemacro file (backed up in backups/)\n"
            f"  2. Remove shortcut from user.keyscheme (backed up)\n"
            f"  3. Remove button from Stream Deck page (if present, backed up)\n\n"
            f"Do you want to proceed?"
        )

        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirm Delete Assignment")
        dlg.geometry("500x350")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        ctk.CTkLabel(
            dlg, text="Delete Assignment",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ff5555",
        ).pack(pady=(14, 6))

        tb = ctk.CTkTextbox(dlg, font=ctk.CTkFont(size=12), wrap="word")
        tb.pack(fill="both", expand=True, padx=16)
        tb.insert("1.0", msg)
        tb.configure(state="disabled")

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=(10, 14))

        def _do_delete():
            dlg.destroy()
            self._execute_delete(macro, raw_shortcut, sd_info)

        ctk.CTkButton(
            btn_row, text="Confirm Delete", width=130,
            fg_color="#882222", hover_color="#aa3333",
            command=_do_delete
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color="#3a3a4a", hover_color="#4a4a5a",
            command=dlg.destroy
        ).pack(side="left", padx=8)

    def _execute_delete(self, macro: Macro, raw_shortcut: str, sd_info: tuple[str, str] | None):
        try:
            reports = []

            # 1. Rimuovi file macro
            m_backup = delete_macro_file(macro.title)
            if m_backup:
                reports.append(f"• Macro file deleted (backed up as {m_backup.name})")

            # 2. Rimuovi da keyscheme
            ks_backup = remove_macro_shortcut(macro.title)
            if ks_backup:
                reports.append(f"• Shortcut removed from keyscheme (backed up as {ks_backup.name})")

            # 3. Rimuovi da Stream Deck se presente
            if sd_info:
                page_uuid, pos = sd_info
                sd_backup = remove_hotkey_from_page(page_uuid, pos)
                reports.append(f"• Stream Deck button in slot {pos} freed (backed up as {sd_backup.name})")

            res_msg = (
                f"✅ ASSIGNMENT DELETED SUCCESSFULLY!\n\n"
                + "\n".join(reports) + "\n\n"
                f"All changes were backed up in backups/.\n"
                f"Restart Fender Studio Pro and Stream Deck to reflect the deletion."
            )

            # Notifica il parent per ricaricare la vista
            if hasattr(self.master, "reload_data"):
                self.master.reload_data()

            self._show_msg_dialog("Success", res_msg, color="#44cc44")

        except Exception as exc:
            self._show_msg_dialog("Delete Failed", f"An error occurred while deleting:\n\n{exc}", color="#cc4444")

    def _show_msg_dialog(self, title: str, msg: str, color: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("480x280")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        ctk.CTkLabel(
            dlg, text=title, font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color,
        ).pack(pady=(14, 6))

        tb = ctk.CTkTextbox(dlg, font=ctk.CTkFont(size=12), wrap="word")
        tb.pack(fill="both", expand=True, padx=16)
        tb.insert("1.0", msg)
        tb.configure(state="disabled")

        ctk.CTkButton(dlg, text="Close", width=100, command=dlg.destroy).pack(pady=(8, 12))

    def reload(self, macros: list[Macro]):
        """Ricarica le macro e riscatta le shortcut live da keyscheme."""
        self._all_macros = macros
        self._shortcuts, self._raw_shortcuts = _load_shortcuts()
        if hasattr(self, "_title_label"):
            self._title_label.configure(text=f"EXISTING MACROS  ({len(self._all_macros)})")
        self._apply_filter()


