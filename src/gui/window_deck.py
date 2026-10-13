"""Finestra mappa Stream Deck — visualizza griglia navigabile 4x2 con icone e thumbnail plugin."""
from __future__ import annotations

from pathlib import Path
import customtkinter as ctk
from PIL import Image

from src.core.win32_utils import get_hwnd, save_window_state, restore_window_position
from src.parsers.deck_profile import SDPage, SDSlot, load_profile
from src.parsers import macro_scanner, plugins_catalog
from src.models import Plugin, Macro
from src.gui.snapshots_loader import find_plugin_snapshot
from src.gui.panel_current import _load_shortcuts
from src.writers.macro_writer import delete_macro_file
from src.writers.keyscheme_writer import remove_macro_shortcut
from src.writers.deck_writer import parse_shortcut_to_hotkey, remove_hotkey_from_page
from src.gui.widgets import tooltip, center_over_parent

_YELLOW = "#c8a838"

_COLS = 4
_ROWS = 2
_GAP  = 12
_CARD_H = 208
_IMG_MAX_W = 180
_IMG_MAX_H = 110
_DEFAULT_GEO = "980x640"

# Colori per tipo slot
_C: dict[str, dict] = {
    "folder": {"bg": "#121d30", "border": "#254a7c", "fg": "#7cb7f7", "icon": "📁"},
    "hotkey": {"bg": "#141a22", "border": "#283b44", "fg": "#e2e8f0", "icon": "⌨"},
    "midi":   {"bg": "#1e1028", "border": "#7a2aaa", "fg": "#bb6aff", "icon": "🎛"},
    "back":   {"bg": "#181822", "border": "#36364a", "fg": "#888899", "icon": "◀"},
    "empty":  {"bg": "#111116", "border": "#1c1c24", "fg": "#2a2a32", "icon": ""},
    "other":  {"bg": "#181612", "border": "#554220", "fg": "#aa8840", "icon": "•"},
}


def _bind_recursive(widget, event: str, callback):
    widget.bind(event, callback)
    for child in widget.winfo_children():
        _bind_recursive(child, event, callback)


class DeckMapWindow(ctk.CTkToplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Stream Deck Map")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._main_pages:   list[SDPage] = []
        self._all_pages:    dict[str, SDPage] = {}
        self._history:      list[str] = []
        self._profile_name: str = ""
        self._profile_uuid: str = ""

        # Dati e cache per matching plugin
        self._catalog:        dict[str, Plugin] = {}
        self._macros:         list[Macro] = []
        self._raw_shortcuts:  dict[str, str] = {}
        self._macro_by_hk:    dict[tuple[int, int], Macro] = {}
        self._macro_by_title: dict[str, Macro] = {}
        self._img_cache:      dict[Path, ctk.CTkImage] = {}

        # Drag & drop targets per slot vuoti
        self._empty_slots: dict[object, tuple[str, ctk.CTkFrame, ctk.CTkLabel]] = {}
        self._active_hover_slot: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(6, 12))
        self._content.grid_columnconfigure(0, weight=1)

        self._load_data()
        self.geometry(_DEFAULT_GEO)
        self.update()
        restore_window_position(get_hwnd(self), "deck_window_state")
        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))

    # ------------------------------------------------------------------ header

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="#12121e", corner_radius=0, height=44)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        self._back_btn = ctk.CTkButton(
            hdr, text="◀  Back", width=88, height=30,
            fg_color="#23233a", hover_color="#33336a",
            font=ctk.CTkFont(size=12),
            command=self._go_back,
        )
        self._back_btn.grid(row=0, column=0, padx=(10, 6), pady=7)

        self._title_lbl = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_YELLOW, anchor="w",
        )
        self._title_lbl.grid(row=0, column=1, sticky="w", padx=4)

        ctk.CTkButton(
            hdr, text="↻", width=34, height=30,
            fg_color="#23233a", hover_color="#33336a",
            font=ctk.CTkFont(size=14),
            command=self._load_data,
        ).grid(row=0, column=2, padx=(0, 10), pady=7)

    # ------------------------------------------------------------------ data

    def _load_data(self):
        # Carica catalogo, macro e shortcut per matching istantaneo dei plugin
        try:
            self._catalog = plugins_catalog.by_guid()
            self._macros  = macro_scanner.load()
            _, self._raw_shortcuts = _load_shortcuts()

            self._macro_by_hk = {}
            self._macro_by_title = {}
            for m in self._macros:
                sc = self._raw_shortcuts.get(m.title)
                if sc:
                    try:
                        hk = parse_shortcut_to_hotkey(sc).get("Hotkeys", [{}])[0]
                        nc, km = hk.get("NativeCode"), hk.get("KeyModifiers")
                        if nc is not None and km is not None:
                            self._macro_by_hk[(nc, km)] = m
                    except Exception:
                        pass
                clean_title = m.title.removeprefix("SdR_").lower().replace(" ", "").replace("_", "")
                self._macro_by_title[clean_title] = m
        except Exception:
            pass

        try:
            self._main_pages, self._all_pages, self._profile_name, self._profile_uuid = load_profile()
        except Exception as e:
            self._show_error(f"Error reading SD profile:\n{e}")
            return
        if not self._main_pages:
            self._show_error("No page with buttons found in the SD profile.")
            return

        self._history = [self._main_pages[0].uuid]
        self._render()

    def _current_page(self) -> SDPage | None:
        return self._all_pages.get(self._history[-1]) if self._history else None

    def _go_back(self):
        if len(self._history) > 1:
            self._history.pop()
            self._render()

    def _navigate_to(self, uuid: str):
        self._history.append(uuid.lower())
        self._render()

    def _set_main_page(self, uuid: str):
        self._history = [uuid.lower()]
        self._render()

    def _count_folder_plugins(self, child_uuid: str | None) -> int:
        """Conta quanti plugin (slot hotkey) sono configurati nella cartella specificata."""
        if not child_uuid:
            return 0
        child_page = self._all_pages.get(child_uuid.lower())
        if not child_page:
            return 0
        total = 0
        for s in child_page.keypad.values():
            if s.action_type == "hotkey":
                total += 1
            elif s.action_type == "folder" and s.child_uuid:
                total += self._count_folder_plugins(s.child_uuid)
        return total

    # ------------------------------------------------------------------ plugin resolution & image

    def _resolve_plugin_for_slot(self, slot: SDSlot) -> tuple[Plugin | None, Macro | None, str, Path | None, str | None]:
        """Risolve (plugin, macro, display_title, image_path, shortcut_str) per lo slot specificato."""
        macro: Macro | None = None
        plugin: Plugin | None = None
        shortcut_str: str | None = None

        # 1. Matching via combinazione tasti hotkey
        if slot.raw_action:
            act_settings = slot.raw_action.get("Settings") or {}
            hotkeys = act_settings.get("Hotkeys") or []
            if hotkeys:
                hk0 = hotkeys[0]
                nc, km = hk0.get("NativeCode"), hk0.get("KeyModifiers")
                if nc is not None and km is not None:
                    macro = self._macro_by_hk.get((nc, km))

        # 2. Matching via titolo
        raw_title = slot.title.replace("\n", " ").strip()
        if not macro and raw_title:
            clean_k = raw_title.lower().replace(" ", "").replace("_", "")
            macro = self._macro_by_title.get(clean_k)
            if not macro:
                for k, m in self._macro_by_title.items():
                    if clean_k and (clean_k in k or k in clean_k):
                        macro = m
                        break

        if macro:
            shortcut_str = self._raw_shortcuts.get(macro.title)
            if macro.guid:
                plugin = self._catalog.get(macro.guid)

        # 3. Nome da mostrare come titolo
        if plugin:
            display_title = plugin.name
        elif macro:
            display_title = macro.preset_name or macro.title.removeprefix("SdR_")
        else:
            display_title = raw_title or slot.name or ""

        # 4. Immagine: snapshot di Studio One se disponibile, altrimenti icona SD
        image_path: Path | None = None
        if macro and macro.guid:
            image_path = find_plugin_snapshot(macro.guid)
        if not image_path and slot.image_path and slot.image_path.exists():
            image_path = slot.image_path

        return plugin, macro, display_title, image_path, shortcut_str

    def _get_card_image(self, path: Path | None) -> ctk.CTkImage | None:
        """Carica, ritaglia eventuale trasparenza, ridimensiona e memorizza in cache l'immagine."""
        if not path or not path.exists():
            return None
        if path in self._img_cache:
            return self._img_cache[path]
        try:
            with Image.open(path) as img:
                img_rgba = img.convert("RGBA")
                bbox = img_rgba.getbbox()
                if bbox:
                    img_rgba = img_rgba.crop(bbox)
                img_rgba.thumbnail((_IMG_MAX_W, _IMG_MAX_H), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(img_rgba, size=img_rgba.size)
                self._img_cache[path] = ctk_img
                return ctk_img
        except Exception:
            return None

    # ------------------------------------------------------------------ render

    def _render(self):
        for w in self._content.winfo_children():
            w.destroy()

        page = self._current_page()
        if not page:
            return

        is_main = len(self._history) == 1
        self._back_btn.configure(state="disabled" if is_main else "normal")
        if is_main:
            short_uuid = self._profile_uuid[:8].upper() + "…"
            title = f"{self._profile_name}  —  {short_uuid}"
        else:
            page_hk = sum(1 for s in page.keypad.values() if s.action_type == "hotkey")
            title = f"▸  {page.name or self._history[-1][:8].upper()}   ({page_hk}/7 plugin)"
        self._title_lbl.configure(text=title)

        r = 0

        # Tab pagine principali (se > 1)
        if is_main and len(self._main_pages) > 1:
            tab_row = ctk.CTkFrame(self._content, fg_color="transparent")
            tab_row.grid(row=r, column=0, sticky="w", pady=(0, 6))
            for i, mp in enumerate(self._main_pages):
                active = mp.uuid == self._history[0]
                ctk.CTkButton(
                    tab_row,
                    text=f"Page {i + 1}",
                    width=90, height=26,
                    fg_color="#1f4a8a" if active else "#23233a",
                    hover_color="#2a5aaa",
                    font=ctk.CTkFont(size=11),
                    command=lambda u=mp.uuid: self._set_main_page(u),
                ).pack(side="left", padx=(0, 4))
            r += 1

        # Griglia keypad 4x2
        self._render_keypad(page, r)
        r += 1

        # Riga encoder (se presente)
        if page.encoders:
            self._render_encoders(page, r)

    def _render_encoders(self, page: SDPage, row: int) -> int:
        enc = ctk.CTkFrame(self._content, fg_color="#0e0a16", corner_radius=10, height=72)
        enc.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        enc.grid_propagate(False)
        enc.grid_columnconfigure(list(range(_COLS)), weight=1, uniform="enc")

        ctk.CTkLabel(
            enc, text="  ENCODER",
            font=ctk.CTkFont(size=9), text_color="#553a77", anchor="w",
        ).grid(row=0, column=0, columnspan=_COLS, sticky="w", padx=8, pady=(4, 0))

        for c in range(_COLS):
            slot = page.encoders.get(f"{c},0")
            clr  = _C.get(slot.action_type if slot else "empty", _C["empty"])
            label = (slot.title or slot.name or "—") if slot else ""

            f = ctk.CTkFrame(enc, fg_color=clr["bg"], corner_radius=6)
            f.grid(row=1, column=c, padx=(8 if c == 0 else 4, 8 if c == _COLS - 1 else 4),
                   pady=(2, 8), sticky="nsew")

            ctk.CTkLabel(
                f, text="◎", font=ctk.CTkFont(size=18), text_color=clr["border"],
            ).pack(pady=(3, 0))
            ctk.CTkLabel(
                f, text=label, font=ctk.CTkFont(size=9), text_color=clr["fg"],
                wraplength=180,
            ).pack(pady=(0, 4))

        return row + 1

    def _render_keypad(self, page: SDPage, row: int):
        self._empty_slots.clear()
        self._active_hover_slot = None

        grid = ctk.CTkFrame(self._content, fg_color="transparent")
        grid.grid(row=row, column=0, sticky="nsew", pady=(0, 6))
        grid.grid_columnconfigure(list(range(_COLS)), weight=1, uniform="kp")
        grid.grid_rowconfigure(list(range(_ROWS)), weight=1, uniform="kp")

        for r in range(_ROWS):
            for c in range(_COLS):
                slot = page.keypad.get(f"{c},{r}")
                self._render_slot(grid, slot, c, r)

    def _render_slot(self, parent, slot: SDSlot | None, col: int, row: int):
        atype = slot.action_type if slot else "empty"
        clr   = _C.get(atype, _C["empty"])

        f = ctk.CTkFrame(
            parent,
            fg_color=clr["bg"],
            border_color=clr["border"],
            border_width=1,
            corner_radius=12,
            height=_CARD_H,
        )
        f.grid(
            row=row, column=col,
            padx=_GAP // 2, pady=_GAP // 2,
            sticky="nsew",
        )
        f.grid_propagate(False)

        # 1. Hotkey con plugin / immagine collegata
        if slot and slot.action_type == "hotkey":
            plugin, macro, display_title, img_path, sc_str = self._resolve_plugin_for_slot(slot)
            ctk_img = self._get_card_image(img_path) if img_path else None

            # Pulsante '-' in basso a sinistra per togliere l'assegnazione al volo
            btn_del = ctk.CTkButton(
                f, text="-", width=22, height=20,
                corner_radius=4,
                fg_color="#2b1818", hover_color="#882222",
                text_color="#ff7777",
                font=ctk.CTkFont(size=14, weight="bold"),
                command=lambda s=slot, pn=display_title, m=macro, sc=sc_str: self._confirm_delete(s, pn, m, sc),
            )
            btn_del.place(x=8, rely=1.0, y=-8, anchor="sw")
            tooltip(btn_del, f"Delete assignment for {display_title}")

            if ctk_img:
                # Titolo plugin sopra
                lbl_title = ctk.CTkLabel(
                    f,
                    text=display_title,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=clr["fg"],
                    wraplength=200,
                    anchor="center",
                )
                lbl_title.pack(side="top", fill="x", padx=8, pady=(10, 4))

                # Immagine plugin sotto
                lbl_img = ctk.CTkLabel(f, text="", image=ctk_img)
                lbl_img.pack(side="top", expand=True, padx=8, pady=(0, 10))

                # Tooltip dettagliato
                tip_parts = [display_title]
                if macro:
                    tip_parts.append(f"Macro: {macro.title}")
                if sc_str:
                    tip_parts.append(f"Shortcut: {sc_str}")
                tip_text = "\n".join(tip_parts)
                tooltip(f, tip_text)
                tooltip(lbl_title, tip_text)
                tooltip(lbl_img, tip_text)

                def on_enter(e, w=f, bc="#3e6050", bg="#19221d"):
                    w.configure(border_color=bc, fg_color=bg)

                def on_leave(e, w=f, bg=clr["bg"], bc=clr["border"]):
                    w.configure(border_color=bc, fg_color=bg)

                f.bind("<Enter>", on_enter)
                f.bind("<Leave>", on_leave)
                lbl_title.bind("<Enter>", on_enter)
                lbl_title.bind("<Leave>", on_leave)
                lbl_img.bind("<Enter>", on_enter)
                lbl_img.bind("<Leave>", on_leave)
                return

            # Fallback hotkey senza immagine (es. TODO)
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                inner, text="⌨",
                font=ctk.CTkFont(size=26), text_color=clr["border"],
            ).pack()
            ctk.CTkLabel(
                inner, text=display_title or slot.title,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=clr["fg"],
                wraplength=180,
            ).pack(pady=(4, 0))
            return

        # 2. Cartella con icona grande, titolo e conteggio plugin
        if slot and slot.action_type == "folder":
            n_plugins = self._count_folder_plugins(slot.child_uuid)
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                inner, text="📁",
                font=ctk.CTkFont(size=34), text_color=clr["fg"],
            ).pack()
            ctk.CTkLabel(
                inner, text=slot.title or slot.name or "Folder",
                font=ctk.CTkFont(size=14, weight="bold"), text_color=clr["fg"],
                wraplength=180,
            ).pack(pady=(6, 2))

            plural = "" if n_plugins == 1 else "s"
            count_text = f"{n_plugins} connected plugin{plural}" if n_plugins > 0 else "0 connected plugins"
            badge_fg = "#14243b" if n_plugins > 0 else "#141720"
            badge_border = "#24436c" if n_plugins > 0 else "#1e2230"
            count_color = "#f0a040" if n_plugins >= 7 else ("#7bb0f0" if n_plugins > 0 else "#556578")

            badge = ctk.CTkFrame(
                inner,
                fg_color=badge_fg,
                border_color=badge_border,
                border_width=1,
                corner_radius=10,
                height=22,
            )
            badge.pack(pady=(4, 0))
            badge_lbl = ctk.CTkLabel(
                badge,
                text=f"{count_text}  ({n_plugins}/7)",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=count_color,
                fg_color="transparent",
            )
            badge_lbl.pack(padx=8, pady=2)

            folder_tip = (
                f"Folder: {slot.title or slot.name or 'Folder'}\n"
                f"{count_text} (of 7 available slots)\n"
                f"Click to open folder"
            )
            tooltip(f, folder_tip)
            tooltip(inner, folder_tip)
            tooltip(badge, folder_tip)
            tooltip(badge_lbl, folder_tip)

            if slot.child_uuid:
                uuid = slot.child_uuid

                def on_click(e, u=uuid):
                    self._navigate_to(u)

                def on_enter(e, w=f):
                    w.configure(fg_color="#1a2842", border_color="#3b72c4")

                def on_leave(e, w=f, bg=clr["bg"], bc=clr["border"]):
                    w.configure(fg_color=bg, border_color=bc)

                _bind_recursive(f, "<Button-1>", on_click)
                _bind_recursive(f, "<Enter>", on_enter)
                _bind_recursive(f, "<Leave>", on_leave)
                f.configure(cursor="hand2")
                for w in f.winfo_children():
                    w.configure(cursor="hand2")
            return

        # 3. Tasto Back (Parent Folder)
        if slot and slot.action_type == "back":
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                inner, text="◀",
                font=ctk.CTkFont(size=30), text_color=clr["fg"],
            ).pack()
            ctk.CTkLabel(
                inner, text="Back",
                font=ctk.CTkFont(size=12), text_color=clr["fg"],
            ).pack(pady=(4, 0))

            def on_back_click(e):
                self._go_back()

            def on_enter(e, w=f):
                w.configure(fg_color="#242436", border_color="#5a5a78")

            def on_leave(e, w=f, bg=clr["bg"], bc=clr["border"]):
                w.configure(fg_color=bg, border_color=bc)

            _bind_recursive(f, "<Button-1>", on_back_click)
            _bind_recursive(f, "<Enter>", on_enter)
            _bind_recursive(f, "<Leave>", on_leave)
            f.configure(cursor="hand2")
            for w in f.winfo_children():
                w.configure(cursor="hand2")
            return

        # 4. Slot vuoto
        if not slot or slot.action_type == "empty":
            pos = f"{col},{row}"
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.place(relx=0.5, rely=0.5, anchor="center")
            lbl = ctk.CTkLabel(
                inner, text="empty",
                font=ctk.CTkFont(size=10), text_color="#262632",
            )
            lbl.pack()
            if pos != "0,0":
                self._empty_slots[f] = (pos, f, lbl)
                self._empty_slots[inner] = (pos, f, lbl)
                self._empty_slots[lbl] = (pos, f, lbl)
            return

        # 5. Altri tipi (MIDI / other)
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        icon = clr["icon"]
        if icon:
            ctk.CTkLabel(
                inner, text=icon,
                font=ctk.CTkFont(size=26), text_color=clr["border"],
            ).pack()
        title = (slot.title or slot.name or "") if slot else ""
        if title:
            ctk.CTkLabel(
                inner, text=title,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=clr["fg"],
                wraplength=180,
            ).pack(pady=(4, 0))

    # ------------------------------------------------------------------ delete assignment

    def _confirm_delete(self, slot: SDSlot, plugin_name: str, macro: Macro | None, shortcut: str | None):
        page_uuid = self._history[-1]
        pos = slot.pos
        macro_text = f"{macro.title}.studioonemacro" if macro else "None (only Stream Deck button)"
        sc_text = shortcut or "None"

        msg = (
            f"Are you sure you want to delete this assignment?\n\n"
            f"• Plugin / Name:  {plugin_name}\n"
            f"• Stream Deck:    Page {page_uuid[:8].upper()}…, Slot {pos}\n"
            f"• Macro File:     {macro_text}\n"
            f"• Shortcut:       {sc_text}\n\n"
            f"Actions performed:\n"
            f"  1. Remove button from Stream Deck profile (slot freed)\n"
            f"  2. Delete associated .studioonemacro file (if present, backed up)\n"
            f"  3. Remove shortcut from user.keyscheme (if present, backed up)\n\n"
            f"Do you want to proceed?"
        )

        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirm Delete Assignment")
        center_over_parent(dlg, self, 500, 350)
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
            self._execute_delete(page_uuid, pos, macro, plugin_name)

        ctk.CTkButton(
            btn_row, text="Confirm Delete", width=130,
            fg_color="#882222", hover_color="#aa3333",
            command=_do_delete,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color="#3a3a4a", hover_color="#4a4a5a",
            command=dlg.destroy,
        ).pack(side="left", padx=8)

    def _execute_delete(self, page_uuid: str, pos: str, macro: Macro | None, plugin_name: str):
        try:
            reports = []

            # 1. Rimuovi pulsante da Stream Deck (cancella anche l'icona generata se presente)
            sd_backup = remove_hotkey_from_page(page_uuid, pos)
            reports.append(f"• Stream Deck button in slot {pos} removed (backed up as {sd_backup.name})")

            # 2. Rimuovi macro e shortcut se presenti
            if macro:
                m_backup = delete_macro_file(macro.title)
                if m_backup:
                    reports.append(f"• Macro file deleted (backed up as {m_backup.name})")

                ks_backup = remove_macro_shortcut(macro.title)
                if ks_backup:
                    reports.append(f"• Shortcut removed from keyscheme (backed up as {ks_backup.name})")

            # Notifica aggiornamento finestra Macro Editor se aperta
            if hasattr(self.master, "_macro_win") and self.master._macro_win and self.master._macro_win.winfo_exists():
                try:
                    self.master._macro_win.reload_data()
                except Exception:
                    pass

            # Ricarica la vista della mappa Stream Deck
            self._load_data()

            res_msg = (
                f"✅ ASSIGNMENT DELETED SUCCESSFULLY!\n\n"
                + "\n".join(reports) + "\n\n"
                f"All changes were backed up in backups/.\n"
                f"Restart Fender Studio Pro and Stream Deck to reflect the deletion."
            )
            self._show_msg_dialog("Success", res_msg, color="#44cc44")

        except Exception as exc:
            self._show_msg_dialog("Delete Failed", f"An error occurred while deleting:\n\n{exc}", color="#cc4444")

    # ------------------------------------------------------------------ drag & drop target

    def _find_empty_slot(self, x_root: int, y_root: int) -> tuple[str, ctk.CTkFrame, ctk.CTkLabel] | None:
        try:
            w = self.winfo_containing(x_root, y_root)
        except Exception:
            return None
        while w is not None:
            if w in self._empty_slots:
                return self._empty_slots[w]
            w = getattr(w, "master", None)
        return None

    def on_drag_motion(self, x_root: int, y_root: int, plugin: Plugin):
        # Auto-lift window to foreground if mouse enters Stream Deck Map
        try:
            w = self.winfo_containing(x_root, y_root)
        except Exception:
            w = None

        if w is not None:
            top_w = getattr(w, "winfo_toplevel", lambda: None)()
            if top_w == self:
                if not getattr(self, "_drag_lifted", False):
                    self._drag_lifted = True
                    self.lift()
        else:
            self._drag_lifted = False

        slot_info = self._find_empty_slot(x_root, y_root)
        if slot_info:
            pos, f, lbl = slot_info
            if self._active_hover_slot != pos:
                self.on_drag_cancel()
                self._active_hover_slot = pos
                if f.winfo_exists():
                    f.configure(border_color="#3ea86b", border_width=2, fg_color="#122c1b")
                if lbl.winfo_exists():
                    lbl.configure(
                        text="✚  Drop here",
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color="#6acc80",
                    )
        else:
            if self._active_hover_slot is not None:
                self.on_drag_cancel()

    def on_drag_cancel(self):
        self._drag_lifted = False
        if self._active_hover_slot is not None:
            for pos, f, lbl in set(self._empty_slots.values()):
                if pos == self._active_hover_slot:
                    if f.winfo_exists():
                        f.configure(border_color=_C["empty"]["border"], border_width=1, fg_color=_C["empty"]["bg"])
                    if lbl.winfo_exists():
                        lbl.configure(text="empty", font=ctk.CTkFont(size=10), text_color="#262632")
            self._active_hover_slot = None

    def on_drag_drop(self, x_root: int, y_root: int, plugin: Plugin):
        self._drag_lifted = False
        slot_info = self._find_empty_slot(x_root, y_root)
        self.on_drag_cancel()
        if slot_info:
            pos, _, _ = slot_info
            self._prompt_map_plugin(plugin, pos)

    def _prompt_map_plugin(self, plugin: Plugin, pos: str):
        page = self._current_page()
        if not page:
            return

        from src.gui.panel_add import get_free_shortcuts, _auto_macro_title, _auto_sd_title
        from src.gui.snapshots_loader import get_snapshot_map, get_snapshot_hires_map

        page_uuid = page.uuid
        page_name = page.name or self._history[-1][:8].upper()

        macro_title = _auto_macro_title(plugin.name)
        sd_title = _auto_sd_title(plugin.name)

        free_shortcuts = get_free_shortcuts()
        default_sc = free_shortcuts[0] if free_shortcuts else "Ctrl+Alt+!"

        snap_hires = get_snapshot_hires_map()
        snap_map = get_snapshot_map()
        snap_path = snap_hires.get(plugin.guid.upper()) or snap_map.get(plugin.guid.upper())

        dlg = ctk.CTkToplevel(self)
        dlg.title("Map Plugin to Stream Deck")
        center_over_parent(dlg, self, 520, 510)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()
        dlg.focus_force()

        # Intestazione
        ctk.CTkLabel(
            dlg,
            text="🎛  Map Plugin to Stream Deck",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#6acc80",
        ).pack(pady=(14, 8))

        # Scheda Plugin Preview
        preview_box = ctk.CTkFrame(dlg, fg_color="#151a24", border_color="#2b3b4f", border_width=1, corner_radius=8)
        preview_box.pack(fill="x", padx=20, pady=(0, 10))

        # Mini thumbnail o icona
        img_ctk = None
        if snap_path and snap_path.exists():
            try:
                pil_im = Image.open(snap_path).convert("RGB")
                pil_im = pil_im.resize((100, 56), Image.LANCZOS)
                img_ctk = ctk.CTkImage(pil_im, size=(100, 56))
            except Exception:
                pass

        row_content = ctk.CTkFrame(preview_box, fg_color="transparent")
        row_content.pack(fill="x", padx=10, pady=8)

        if img_ctk:
            img_l = ctk.CTkLabel(row_content, text="", image=img_ctk)
            img_l.image = img_ctk
            img_l.pack(side="left", padx=(0, 12))
        else:
            ctk.CTkLabel(row_content, text="🎛", font=ctk.CTkFont(size=28), text_color="#3e75b8").pack(side="left", padx=(4, 12))

        txt_info = ctk.CTkFrame(row_content, fg_color="transparent")
        txt_info.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            txt_info,
            text=plugin.name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff",
            anchor="w",
        ).pack(fill="x")

        vnd_txt = f"{plugin.vendor} · {plugin.category}" if plugin.vendor else plugin.category
        ctk.CTkLabel(
            txt_info,
            text=vnd_txt,
            font=ctk.CTkFont(size=11),
            text_color="#8899aa",
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Badge destinazione
        dest_lbl = ctk.CTkLabel(
            txt_info,
            text=f"Target:  📁 {page_name}   ·   Slot {pos}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#6acc80",
            anchor="w",
        )
        dest_lbl.pack(fill="x", pady=(4, 0))

        # Form parametri
        form = ctk.CTkFrame(dlg, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20)

        # 1. Macro Title
        ctk.CTkLabel(form, text="Macro Title (.studioonemacro)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#c0c0d0").pack(anchor="w", pady=(4, 2))
        ent_macro = ctk.CTkEntry(form, height=30)
        ent_macro.pack(fill="x")
        ent_macro.insert(0, macro_title)

        # 2. Shortcut
        ctk.CTkLabel(form, text="Keyboard Shortcut (free)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#c0c0d0").pack(anchor="w", pady=(8, 2))
        combo_sc = ctk.CTkComboBox(form, values=free_shortcuts or [default_sc], height=30)
        combo_sc.pack(fill="x")
        combo_sc.set(default_sc)

        # 3. Stream Deck button text
        ctk.CTkLabel(form, text="Button Title (Stream Deck display)", font=ctk.CTkFont(size=11, weight="bold"), text_color="#c0c0d0").pack(anchor="w", pady=(8, 2))
        ent_sd = ctk.CTkEntry(form, height=30)
        ent_sd.pack(fill="x")
        ent_sd.insert(0, sd_title.replace("\n", " "))

        def _do_confirm():
            m_val = ent_macro.get().strip()
            sc_val = combo_sc.get().strip()
            sd_val = ent_sd.get().strip() or plugin.name
            if not m_val:
                ent_macro.focus_set()
                return
            if not sc_val:
                combo_sc.focus_set()
                return

            dlg.destroy()
            self._execute_map_pipeline(plugin, m_val, sc_val, sd_val, page_uuid, pos, snap_path)

        # Bottoni
        btn_bar = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_bar.pack(fill="x", padx=20, pady=(12, 16))

        ctk.CTkButton(
            btn_bar,
            text="Confirm & Map",
            fg_color="#226437",
            hover_color="#2e8549",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=160,
            height=34,
            command=_do_confirm,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_bar,
            text="Cancel",
            fg_color="#3a3a4a",
            hover_color="#4a4a5a",
            width=100,
            height=34,
            command=dlg.destroy,
        ).pack(side="left")

    def _execute_map_pipeline(
        self,
        plugin: Plugin,
        macro_title: str,
        shortcut: str,
        sd_title: str,
        page_uuid: str,
        pos: str,
        snapshot_path: Path | None,
    ):
        from src.writers.macro_writer import write_macro_file
        from src.writers.keyscheme_writer import add_macro_shortcut
        from src.writers.deck_writer import add_hotkey_to_page

        created_macro_path: Path | None = None
        try:
            m_type = "instrument" if plugin.category == "Instrument" else "effect"

            # 1. Scrivi file macro
            created_macro_path = write_macro_file(
                title=macro_title,
                description=f"insert {plugin.name}",
                guid=plugin.guid,
                macro_type=m_type,
                preset_name=plugin.name,
                open_editor=False,
            )

            # 2. Inserisci shortcut in keyscheme (con backup)
            ks_backup = add_macro_shortcut(
                macro_title=macro_title,
                shortcut=shortcut,
            )

            # 3. Aggiungi hotkey su Stream Deck (con backup ed eventuale icona)
            sd_backup, assigned_slot = add_hotkey_to_page(
                page_uuid=page_uuid,
                shortcut=shortcut,
                title=sd_title,
                position=pos,
                icon_source_path=snapshot_path,
            )

            # Ricarica vista SD
            self._load_data()

            # Ricarica vista Library principale
            if hasattr(self.master, "_panel_lib") and self.master._panel_lib:
                plib = self.master._panel_lib
                plib._load_mapped_data()
                plib._rebuild_sidebar_cats()
                plib._refresh()

            # Ricarica Macro Editor se aperto
            if hasattr(self.master, "_macro_win") and self.master._macro_win and self.master._macro_win.winfo_exists():
                try:
                    self.master._macro_win.reload_data()
                except Exception:
                    pass

            icon_msg = f"\n• Icon:       {snapshot_path.name}" if snapshot_path else ""
            res_msg = (
                f"✅ PLUGIN MAPPED SUCCESSFULLY!\n\n"
                f"• Plugin:     {plugin.name}\n"
                f"• Position:   Slot {assigned_slot} in {self._current_page().name or page_uuid[:8].upper()}{icon_msg}\n"
                f"• Macro:      {created_macro_path.name}\n"
                f"• Shortcut:   {shortcut}\n\n"
                f"Backups created in backups/:\n"
                f"  - {ks_backup.name}\n"
                f"  - {sd_backup.name}\n\n"
                f"Restart Fender Studio Pro and Stream Deck to reflect the changes."
            )
            self._show_msg_dialog("Success", res_msg, color="#44cc44")

        except Exception as exc:
            # ROLLBACK: Se la macro era stata scritta ma keyscheme o SD hanno fallito, rimuovila
            if created_macro_path and created_macro_path.exists():
                try:
                    created_macro_path.unlink()
                except Exception:
                    pass

            self._show_msg_dialog(
                "Mapping Failed",
                f"An error occurred while mapping:\n\n{exc}\n\nRollback completed: no incomplete files were left.",
                color="#cc4444",
            )

    def _show_msg_dialog(self, title: str, msg: str, color: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        center_over_parent(dlg, self, 480, 280)
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

    def _on_close(self):
        self.update_idletasks()
        save_window_state(get_hwnd(self), "deck_window_state")
        self.destroy()

    # ------------------------------------------------------------------ error

    def _show_error(self, msg: str):
        for w in self._content.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self._content, text=f"⚠  {msg}",
            text_color="#cc4444", font=ctk.CTkFont(size=12),
        ).pack(pady=40)
