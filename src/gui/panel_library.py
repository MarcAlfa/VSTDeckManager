"""Pannello libreria VST: sidebar categorie + grid card con immagini e preferiti."""
from __future__ import annotations

import json
import traceback
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import customtkinter as ctk
from PIL import Image

from src.models import Plugin
from src.gui.snapshots_loader import get_snapshot_map, get_snapshot_hires_map
from src.parsers import plugin_presentation
from src.core.config import CACHE_DIR
from src.gui.widgets import tooltip

_YELLOW = "#c8a838"

# ---- card dimensions -------------------------------------------------------
_CARD_W    = 179
_CARD_H    = 140
_IMG_W     = 167
_IMG_H     = 75
_CARD_COLS = 6
_CARD_GAP  = 6
_BATCH_SZ  = 30      # card per batch (rendering asincrono)
_MAX_CARDS = 300     # cap per "Tutti" e categorie grandi

# ---- sidebar ---------------------------------------------------------------
_SIDEBAR_W = 170

# ---- category groups --------------------------------------------------------
_CAT_INSTRUMENTS = {
    "Bass", "Controller", "Drum-Sampler", "Piano-Organ", "Synth",
}


_FAV_FILE   = CACHE_DIR / "favorites.json"
_HIDE_FILE  = CACHE_DIR / "hidden.json"
_NOTES_FILE = CACHE_DIR / "notes.json"

# ---- detail view image size ------------------------------------------------
_DETAIL_IMG_W = 400
_DETAIL_IMG_H = 225


# ---- internal skip list (VST3 internal engines, not real audio plugins) ----
_SKIP_CATS = {
    "AudioEdit", "Engine", "EventEdit", "FileBrowser",
    "MusicEdit", "MusicPartEdit", "Project", "ProjectEdit",
    "Show", "ShowEdit", "TrackEdit", "VST3",
}


# ---- helpers ----------------------------------------------------------------

def _derive_category_from_sub(sub_category: str) -> str:
    """Fallback: deriva categoria grezza da sub_category VST3."""
    s = sub_category
    for prefix in ("VST3/", "(Native)/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.split("/")[0].strip()
    if not s or s in _SKIP_CATS:
        return "zzzz"
    return s


def _get_category(guid: str, sub_category: str, pres_map: dict[str, str]) -> str:
    """Ritorna la categoria FSP dal mapping PluginPresentation, con fallback.

    guid può essere "{XXXXXXXX-...}" — le graffe vengono rimosse per il lookup.
    """
    key = guid.upper().strip("{}")
    cat = pres_map.get(key, "")
    if cat:
        return cat
    return _derive_category_from_sub(sub_category)


def _load_favorites() -> set[str]:
    try:
        data = json.loads(_FAV_FILE.read_text(encoding="utf-8"))
        return set(data.get("favorites", []))
    except Exception:
        return set()


def _save_favorites(favs: set[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _FAV_FILE.write_text(
        json.dumps({"favorites": sorted(favs)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_hidden() -> set[str]:
    try:
        data = json.loads(_HIDE_FILE.read_text(encoding="utf-8"))
        return set(data.get("hidden", []))
    except Exception:
        return set()


def _save_hidden(hidden: set[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _HIDE_FILE.write_text(
        json.dumps({"hidden": sorted(hidden)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_notes() -> dict[str, str]:
    try:
        return json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_notes(notes: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _NOTES_FILE.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _bind_combo_click(combo: ctk.CTkComboBox) -> ctk.CTkComboBox:
    combo._entry.bind("<Button-1>", lambda e: combo._open_dropdown_menu())
    return combo


# ============================================================================

class PanelLibrary(ctk.CTkFrame):

    def __init__(self, parent, catalog: dict[str, Plugin]):
        super().__init__(parent, corner_radius=0, fg_color="transparent")

        self._all_plugins  = list(catalog.values())
        self._favorites    = _load_favorites()
        self._hidden       = _load_hidden()
        self._notes        = _load_notes()
        self._snap_map      = get_snapshot_map()
        self._snap_hires    = get_snapshot_hires_map()
        self._img_cache:   dict[str, ctk.CTkImage] = {}
        self._placeholder: ctk.CTkImage | None = None

        # Load FSP category mapping (PluginPresentation.settings)
        self._pres_map: dict[str, str] = plugin_presentation.load()

        # Mapped plugin cache (macro + SD assignment)
        self._mapped_info: dict[str, dict] = {}
        self._load_mapped_data()

        # Rendering state
        self._card_widgets:   list[ctk.CTkFrame] = []
        self._pending_images: list[tuple] = []
        self._render_queue:   list[Plugin] = []
        self._render_offset:  int = 0

        self._cat_buttons:  dict[str, ctk.CTkButton] = {}
        self._current_cat:  str | None = None
        self._detail_frame: ctk.CTkFrame | None = None
        self._note_save_id: str | None = None    # after() id per debounce note

        # Build per-category lists
        self._cat_plugins: dict[str, list[Plugin]] = {}
        for p in self._all_plugins:
            cat = _get_category(p.guid, p.sub_category, self._pres_map)
            self._cat_plugins.setdefault(cat, []).append(p)

        # Categorie divise in tre gruppi (mostra solo categorie con plugin visibili)
        all_cats = {
            cat for cat, plist in self._cat_plugins.items()
            if any(p.guid.upper() not in self._hidden for p in plist)
        }
        eff_cats   = all_cats - _CAT_INSTRUMENTS - {"zzzz"}
        instr_cats = all_cats & _CAT_INSTRUMENTS

        self._cat_effects     = sorted(eff_cats)
        self._cat_instruments = sorted(instr_cats)
        self._cat_others      = ["zzzz"] if any(p.guid.upper() not in self._hidden for p in self._cat_plugins.get("zzzz", [])) else []
        # _categories mantiene la lista piatta per compatibilità con _on_refresh
        self._categories = self._cat_effects + self._cat_instruments + self._cat_others


        # Stato espansione gruppi sidebar
        self._group_expanded: dict[str, bool] = {"Effects": True, "Instruments": True, "Others": True}
        self._group_frames:   dict[str, ctk.CTkFrame] = {}
        self._group_hdrs:     dict[str, ctk.CTkButton] = {}

        # Fonts
        self._f_hdr    = ctk.CTkFont(size=11, weight="bold")
        self._f_label  = ctk.CTkFont(size=12)
        self._f_small  = ctk.CTkFont(size=11)
        self._f_card   = ctk.CTkFont(size=11, weight="bold")
        self._f_vendor = ctk.CTkFont(size=10)

        # Filter vars
        self._search_var = ctk.StringVar()
        self._type_var   = ctk.StringVar(value="All")
        self._vendor_var = ctk.StringVar(value="All")

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

        # Trace solo per filtri combo (non su search, che usa Enter/bottone)
        self._type_var.trace_add("write",   lambda *_: self._refresh())
        self._vendor_var.trace_add("write", lambda *_: self._refresh())

        self._drag_data: dict | None = None
        self._drag_avatar: ctk.CTkToplevel | None = None
        self.winfo_toplevel().bind("<Escape>", self._on_drag_cancel, add="+")

        # Nessuna _refresh() qui — lista inizia vuota

    def _load_mapped_data(self):
        """Scansiona macro, scorciatoie e Stream Deck per mappare i plugin configurati."""
        self._mapped_info = {}
        try:
            from src.parsers import macro_scanner
            from src.parsers.deck_profile import load_profile
            from src.gui.panel_current import _load_shortcuts
            from src.writers.deck_writer import parse_shortcut_to_hotkey
            import html

            macros = macro_scanner.load()
            _, raw_shortcuts = _load_shortcuts()
            _, all_pages, _, _ = load_profile()

            sd_hotkeys = []
            for p_uuid, page in all_pages.items():
                for pos, slot in page.keypad.items():
                    if slot.action_type == "hotkey":
                        sd_hotkeys.append((p_uuid, page.name or p_uuid[:8].upper(), pos, slot))

            for m in macros:
                raw_sc = html.unescape(raw_shortcuts.get(m.title, ""))
                sd_found = None
                for p_uuid, p_name, pos, slot in sd_hotkeys:
                    clean_s = slot.title.replace("\n", " ").strip().lower().replace(" ", "").replace("_", "")
                    clean_m = m.title.removeprefix("SdR_").lower().replace(" ", "").replace("_", "")
                    if clean_s == clean_m or clean_s in clean_m or clean_m in clean_s:
                        sd_found = (p_name, pos)
                        break
                    if raw_sc and slot.raw_action:
                        try:
                            hk_exp = parse_shortcut_to_hotkey(raw_sc).get("Hotkeys", [{}])[0]
                            hk_act = (slot.raw_action.get("Settings") or {}).get("Hotkeys", [{}])[0]
                            if (hk_exp.get("NativeCode") == hk_act.get("NativeCode") and
                                hk_exp.get("KeyModifiers") == hk_act.get("KeyModifiers")):
                                sd_found = (p_name, pos)
                                break
                        except Exception:
                            pass

                info = {
                    "macro": m,
                    "shortcut": raw_sc,
                    "sd": sd_found,
                }

                if m.guid:
                    self._mapped_info[m.guid.strip("{}").upper()] = info
                else:
                    clean_mt = m.title.removeprefix("SdR_").lower().replace(" ", "").replace("_", "")
                    for p in self._all_plugins:
                        if p.category == "Instrument":
                            clean_pn = p.name.lower().replace(" ", "").replace("_", "")
                            if clean_pn == clean_mt or clean_mt in clean_pn:
                                self._mapped_info[p.guid.strip("{}").upper()] = info
                                break
        except Exception:
            pass

    def _is_mapped(self, plugin: Plugin) -> bool:
        return plugin.guid.strip("{}").upper() in self._mapped_info

    # ---------------------------------------------------------------- sidebar

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color="#12121e", corner_radius=0, width=_SIDEBAR_W)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)
        sb.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            sb, text="VST LIBRARY",
            font=self._f_hdr, text_color=_YELLOW, anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        scroll = ctk.CTkScrollableFrame(
            sb, fg_color="transparent", corner_radius=0,
            scrollbar_button_color="#1a1a2e",
            scrollbar_button_hover_color="#2a2a3e",
        )
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        r = 0
        visible_all = len([p for p in self._all_plugins if p.guid.upper() not in self._hidden])
        self._cat_buttons["All"] = self._make_cat_btn(
            scroll, r, "All", visible_all, "All"
        )
        r += 1
        fav_count = len([p for p in self._all_plugins if p.guid.upper() in self._favorites and p.guid.upper() not in self._hidden])
        self._cat_buttons["Favorites"] = self._make_cat_btn(
            scroll, r, "★  Favorites", fav_count, "Favorites"
        )
        r += 1
        self._cat_buttons["Hidden"] = self._make_cat_btn(
            scroll, r, "⊗  Hidden", len(self._hidden), "Hidden"
        )
        r += 1
        mapped_count = len([p for p in self._all_plugins if self._is_mapped(p) and p.guid.upper() not in self._hidden])
        self._cat_buttons["Mapped"] = self._make_cat_btn(
            scroll, r, "🎛  Mapped", mapped_count, "Mapped"
        )
        r += 1

        ctk.CTkFrame(scroll, height=1, fg_color="#252535").grid(
            row=r, column=0, sticky="ew", padx=8, pady=5
        )
        r += 1

        for group_name, cats in (("Effects", self._cat_effects),
                                  ("Instruments", self._cat_instruments),
                                  ("Others", self._cat_others)):
            # Header espandibile
            hdr = ctk.CTkButton(
                scroll,
                text=f"▼  {group_name.upper()}",
                anchor="w",
                font=ctk.CTkFont(size=11, weight="bold"),
                height=26, corner_radius=4,
                fg_color="#1e1e30", hover_color="#28284a",
                text_color=_YELLOW,
                command=lambda g=group_name: self._toggle_group(g),
            )
            hdr.grid(row=r, column=0, sticky="ew", padx=6, pady=(6, 1))
            self._group_hdrs[group_name] = hdr
            r += 1

            # Container con i pulsanti categoria
            frame = ctk.CTkFrame(scroll, fg_color="transparent")
            frame.grid(row=r, column=0, sticky="ew")
            frame.grid_columnconfigure(0, weight=1)
            self._group_frames[group_name] = frame
            r += 1

            for i, cat in enumerate(cats):
                n = len([p for p in self._cat_plugins.get(cat, []) if p.guid.upper() not in self._hidden])
                self._cat_buttons[cat] = self._make_cat_btn(frame, i, cat, n, cat,
                                                             indent=True)

    def _toggle_group(self, group_name: str):
        expanded = not self._group_expanded[group_name]
        self._group_expanded[group_name] = expanded
        frame = self._group_frames[group_name]
        hdr   = self._group_hdrs[group_name]
        arrow = "▼" if expanded else "▶"
        hdr.configure(text=f"{arrow}  {group_name.upper()}")
        if expanded:
            frame.grid()
        else:
            frame.grid_remove()

    def _make_cat_btn(self, parent, row, label, count, key, active=False,
                      indent=False) -> ctk.CTkButton:
        text = f"  {label}  ({count})"
        btn = ctk.CTkButton(
            parent, text=text, anchor="w",
            font=self._f_small, height=28, corner_radius=6,
            fg_color="#1f3055" if active else "transparent",
            hover_color="#1a2a40",
            text_color="#dce4ee" if active else "#888888",
            command=lambda k=key: self._select_cat(k),
        )
        lx = 18 if indent else 6
        btn.grid(row=row, column=0, sticky="ew", padx=(lx, 6), pady=1)
        return btn

    def _select_cat(self, cat: str):
        for k, btn in self._cat_buttons.items():
            btn.configure(
                fg_color="#1f3055" if k == cat else "transparent",
                text_color="#dce4ee" if k == cat else "#888888",
            )
        self._current_cat = cat
        self._refresh()

    # ---------------------------------------------------------------- main area

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        self._build_toolbar(main)
        self._build_count_bar(main)
        self._build_grid_area(main)

    def _build_toolbar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        bar.grid_columnconfigure(0, weight=1)

        search_row = ctk.CTkFrame(bar, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            search_row, textvariable=self._search_var,
            placeholder_text="Search by name or vendor...  (Enter)",
            height=32, font=self._f_label,
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        entry.bind("<Return>", lambda e: self._do_search())

        ctk.CTkButton(
            search_row, text="→", width=34, height=32,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._do_search,
        ).grid(row=0, column=1, padx=(0, 6))

        self._refresh_btn = ctk.CTkButton(
            search_row, text="↻ Refresh",
            font=self._f_small, height=32, width=100,
            fg_color="#2a3a2a", hover_color="#3a5a3a",
            command=self._on_refresh,
        )
        self._refresh_btn.grid(row=0, column=2)

        ctk.CTkButton(
            search_row, text="⬆ Export",
            font=self._f_small, height=32, width=100,
            fg_color="#2a2a3a", hover_color="#3a3a5a",
            command=self._export_list,
        ).grid(row=0, column=3, padx=(6, 0))

        filter_row = ctk.CTkFrame(bar, fg_color="transparent")
        filter_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        filter_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            filter_row, text="Vendor:", font=self._f_small,
            text_color="#888888", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 4))

        vendors = ["All"] + sorted({p.vendor for p in self._all_plugins if p.vendor})
        self._vendor_combo = _bind_combo_click(ctk.CTkComboBox(
            filter_row, variable=self._vendor_var,
            values=vendors, height=28, font=self._f_small, state="readonly",
        ))
        self._vendor_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))


        _bind_combo_click(ctk.CTkComboBox(
            filter_row, variable=self._type_var,
            values=["All", "Effect", "Instrument", "Native"],
            width=118, height=28, font=self._f_small, state="readonly",
        )).grid(row=0, column=2)

    def _build_count_bar(self, parent):
        self._count_lbl = ctk.CTkLabel(
            parent, text="",
            font=self._f_small, text_color="#505050", anchor="w",
        )
        self._count_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(2, 2))

    def _build_grid_area(self, parent):
        self._grid_outer = ctk.CTkFrame(parent, fg_color="#0d0d16", corner_radius=6)
        self._grid_outer.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 4))
        self._grid_outer.grid_columnconfigure(0, weight=1)
        self._grid_outer.grid_rowconfigure(0, weight=1)

        # Messaggio iniziale
        self._empty_lbl = ctk.CTkLabel(
            self._grid_outer,
            text="Select a category from the sidebar\nor search for a plugin",
            font=ctk.CTkFont(size=13),
            text_color="#303045",
        )
        self._empty_lbl.grid(row=0, column=0)

        # Scroll frame (inizialmente nascosto)
        self._scroll = ctk.CTkScrollableFrame(
            self._grid_outer, corner_radius=0, fg_color="transparent",
        )
        for c in range(_CARD_COLS):
            self._scroll.grid_columnconfigure(c, weight=0, minsize=_CARD_W)

        self._scroll_visible = False

    def _show_scroll(self):
        if not self._scroll_visible:
            self._empty_lbl.grid_forget()
            self._scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
            self._scroll_visible = True

    def _show_empty(self, msg: str = "Select a category from the sidebar\nor search for a plugin"):
        if self._scroll_visible:
            self._scroll.grid_forget()
            self._scroll_visible = False
        self._empty_lbl.configure(text=msg)
        self._empty_lbl.grid(row=0, column=0)

    # ---------------------------------------------------------------- catalog refresh

    def _rebuild_sidebar_cats(self):
        """Ricalcola le categorie e ricostruisce i pulsanti dinamici della sidebar."""
        all_cats = {
            cat for cat, plist in self._cat_plugins.items()
            if any(p.guid.upper() not in self._hidden for p in plist)
        }
        self._cat_effects     = sorted(all_cats - _CAT_INSTRUMENTS - {"zzzz"})
        self._cat_instruments = sorted(all_cats & _CAT_INSTRUMENTS)
        self._cat_others      = ["zzzz"] if any(p.guid.upper() not in self._hidden for p in self._cat_plugins.get("zzzz", [])) else []
        self._categories = self._cat_effects + self._cat_instruments + self._cat_others

        # Aggiorna count bottoni statici
        visible_all = len([p for p in self._all_plugins if p.guid.upper() not in self._hidden])
        self._cat_buttons["All"].configure(text=f"  All  ({visible_all})")
        fav_count = len([p for p in self._all_plugins if p.guid.upper() in self._favorites and p.guid.upper() not in self._hidden])
        self._cat_buttons["Favorites"].configure(text=f"  ★  Favorites  ({fav_count})")
        self._cat_buttons["Hidden"].configure(text=f"  ⊗  Hidden  ({len(self._hidden)})")
        mapped_count = len([p for p in self._all_plugins if self._is_mapped(p) and p.guid.upper() not in self._hidden])
        if "Mapped" in self._cat_buttons:
            self._cat_buttons["Mapped"].configure(text=f"  🎛  Mapped  ({mapped_count})")

        # Rimuovi riferimenti vecchi bottoni categoria
        for key in [k for k in self._cat_buttons if k not in ("All", "Favorites", "Hidden", "Mapped")]:
            del self._cat_buttons[key]

        # Ricostruisci bottoni nei group frame
        for group_name, cats in (("Effects", self._cat_effects),
                                  ("Instruments", self._cat_instruments),
                                  ("Others", self._cat_others)):
            frame = self._group_frames[group_name]
            for w in frame.winfo_children():
                w.destroy()
            for i, cat in enumerate(cats):
                n = len([p for p in self._cat_plugins.get(cat, []) if p.guid.upper() not in self._hidden])
                self._cat_buttons[cat] = self._make_cat_btn(frame, i, cat, n, cat, indent=True)

        # Se la categoria corrente non esiste più, deseleziona
        if self._current_cat not in self._cat_buttons:
            self._current_cat = None


    def _on_refresh(self):
        self._refresh_btn.configure(text="⏳ Loading...", state="disabled")
        self.update()
        try:
            from src.parsers import plugins_catalog
            # Ricarica dal disco le categorie FSP forzando il refresh della cache
            self._pres_map = plugin_presentation.load(force_refresh=True)
            new_plugins = plugins_catalog.load(force_refresh=True)
            self._all_plugins = new_plugins

            # Ricarica preferiti, nascosti e note dal disco
            self._favorites = _load_favorites()
            self._hidden = _load_hidden()
            self._notes = _load_notes()
            self._load_mapped_data()

            # Ricarica snapshots e svuota la cache delle immagini
            self._snap_map = get_snapshot_map(force_refresh=True)
            self._snap_hires = get_snapshot_hires_map(force_refresh=True)
            self._img_cache.clear()

            # Ricostruisci cat_plugins con il nuovo pres_map
            self._cat_plugins.clear()
            for p in self._all_plugins:
                cat = _get_category(p.guid, p.sub_category, self._pres_map)
                self._cat_plugins.setdefault(cat, []).append(p)

            # Aggiorna dropdown vendor
            vendors = ["All"] + sorted({p.vendor for p in self._all_plugins if p.vendor})
            if hasattr(self, "_vendor_combo"):
                self._vendor_combo.configure(values=vendors)

            # Ricostruisci sidebar con le nuove categorie e contatori
            self._rebuild_sidebar_cats()
            info = plugins_catalog.cache_info()
            self._refresh_btn.configure(
                text=f"↻ {info.get('count', '?')} plugins",
                state="normal",
            )
        except Exception:
            self._refresh_btn.configure(text="✗ Error", state="normal")
            mb.showerror("Refresh error", traceback.format_exc())
        self._refresh()
        self.after(3000, lambda: self._refresh_btn.configure(text="↻ Refresh"))


    # ---------------------------------------------------------------- export

    def _export_list(self):
        path = fd.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
            initialfile="vst_library.txt",
            title="Export VST list",
        )
        if not path:
            return

        lines = []

        def _section(title: str, cats: list[str]):
            first = True
            for cat in cats:
                plugins = [
                    p for p in self._cat_plugins.get(cat, [])
                    if p.guid.upper() not in self._hidden
                ]
                if not plugins:
                    continue
                if first:
                    lines.append(f"{'=' * 60}")
                    lines.append(title)
                    lines.append(f"{'=' * 60}")
                    first = False
                lines.append(f"\n[{cat}]")
                for p in sorted(plugins, key=lambda x: x.name.lower()):
                    tags = []
                    if p.guid.upper() in self._favorites:
                        tags.append("★")
                    if self._is_mapped(p):
                        tags.append("🎛 Mapped")
                    tag_str = f" [{' '.join(tags)}]" if tags else ""
                    vendor = f"  ({p.vendor})" if p.vendor else ""
                    lines.append(f"  {p.name}{vendor}{tag_str}")

        _section("EFFECTS", self._cat_effects)
        _section("INSTRUMENTS", self._cat_instruments)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            mb.showinfo("Export", f"List exported:\n{path}")
        except Exception as e:
            mb.showerror("Export error", str(e))

    # ---------------------------------------------------------------- search trigger

    def _do_search(self):
        """Triggered da Invio / bottone → deseleziona categoria e cerca su tutti."""
        q = self._search_var.get().strip()
        if not q:
            return
        # Deseleziona categoria nella sidebar
        for btn in self._cat_buttons.values():
            btn.configure(fg_color="transparent", text_color="#888888")
        self._current_cat = None
        self._refresh()

    # ---------------------------------------------------------------- filter

    def _get_filtered(self) -> list[Plugin]:
        q      = self._search_var.get().strip().lower()
        typ    = self._type_var.get()
        vendor = self._vendor_var.get()

        if self._current_cat == "All":
            base = self._all_plugins
        elif self._current_cat == "Favorites":
            base = [p for p in self._all_plugins if p.guid.upper() in self._favorites]
        elif self._current_cat == "Hidden":
            base = [p for p in self._all_plugins if p.guid.upper() in self._hidden]
        elif self._current_cat == "Mapped":
            base = [p for p in self._all_plugins if self._is_mapped(p)]
        elif self._current_cat is not None:
            base = self._cat_plugins.get(self._current_cat, [])
        else:
            base = self._all_plugins

        in_hidden_view = (self._current_cat == "Hidden")

        result = []
        for p in base:
            # Escludi i nascosti da tutte le view tranne "Nascosti"
            if not in_hidden_view and p.guid.upper() in self._hidden:
                continue
            if typ == "Effect" and p.category != "AudioEffect":
                continue
            if typ == "Instrument" and "Synth" not in p.category and "Instrument" not in p.category:
                continue
            if typ == "Native" and not p.sub_category.startswith("(Native)"):
                continue
            if vendor != "All" and p.vendor != vendor:
                continue
            if q and q not in p.name.lower() and q not in (p.vendor or "").lower():
                continue
            result.append(p)

        return sorted(result, key=lambda p: p.name.lower())

    # ---------------------------------------------------------------- refresh

    def _refresh(self, *args):
        # Se nessuna categoria e nessuna ricerca → stato vuoto
        q = self._search_var.get().strip()
        if self._current_cat is None and not q:
            self._clear_cards()
            self._show_empty()
            self._count_lbl.configure(text="")
            return

        self._render_queue   = []
        self._render_offset  = 0
        self._pending_images = []
        self._clear_cards()

        plugins = self._get_filtered()
        total   = len(plugins)
        shown   = min(total, _MAX_CARDS)

        if total == 0:
            cat_label = self._current_cat or "search"
            self._show_empty(f"No plugins found in  {cat_label}")
            self._count_lbl.configure(text="0 plugins", text_color="#505050")
            return

        self._show_scroll()

        if shown < total:
            self._count_lbl.configure(
                text=f"showing {shown} of {total}  —  {self._current_cat or 'search'}   (refine to see more)",
                text_color=_YELLOW,
            )
        else:
            self._count_lbl.configure(
                text=f"{total} plugins  —  {self._current_cat or 'search'}",
                text_color="#505050",
            )

        self._scroll._parent_canvas.yview_moveto(0)
        self._render_queue  = plugins[:shown]
        self._render_offset = 0
        self.after(0, self._render_next_batch)

    def _clear_cards(self):
        for w in self._card_widgets:
            w.destroy()
        self._card_widgets.clear()

    # ---------------------------------------------------------------- batch rendering

    def _render_next_batch(self):
        batch = self._render_queue[self._render_offset: self._render_offset + _BATCH_SZ]
        if not batch:
            self.after(10, self._load_next_image)
            return

        for j, plugin in enumerate(batch):
            i = self._render_offset + j
            r, c = divmod(i, _CARD_COLS)
            card = self._make_card(plugin, r, c)
            self._card_widgets.append(card)

        self._render_offset += len(batch)

        if self._render_offset < len(self._render_queue):
            self.after(0, self._render_next_batch)
        else:
            self.after(10, self._load_next_image)

    # ---------------------------------------------------------------- card

    def _make_card(self, plugin: Plugin, row: int, col: int) -> ctk.CTkFrame:
        is_fav = plugin.guid.upper() in self._favorites
        is_mapped = self._is_mapped(plugin)

        card = ctk.CTkFrame(
            self._scroll,
            width=_CARD_W, height=_CARD_H,
            fg_color="#1a1a28",
            border_color=_YELLOW if is_fav else ("#2e5438" if is_mapped else "#2a2a40"),
            border_width=2 if (is_fav or is_mapped) else 1,
            corner_radius=8,
            cursor="hand2",
        )
        card.grid(row=row, column=col, padx=_CARD_GAP, pady=_CARD_GAP, sticky="nw")
        card.grid_propagate(False)

        img_lbl = ctk.CTkLabel(
            card, text="", image=self._get_placeholder(),
            width=_IMG_W, height=_IMG_H, fg_color="transparent",
            cursor="hand2",
        )
        img_lbl.place(x=(_CARD_W - _IMG_W) // 2, y=5)

        name_text = plugin.name if len(plugin.name) <= 21 else plugin.name[:20] + "…"
        name_lbl = ctk.CTkLabel(
            card, text=name_text, anchor="w",
            font=self._f_card, text_color="#dce4ee",
            fg_color="transparent", height=17,
            cursor="hand2",
        )
        name_lbl.place(x=6, y=88)

        vnd = (plugin.vendor or "—")
        if len(vnd) > 18:
            vnd = vnd[:17] + "…"
        vendor_lbl = ctk.CTkLabel(
            card, text=vnd, anchor="w",
            font=self._f_vendor, text_color="#6a6a7a",
            fg_color="transparent", height=16,
            cursor="hand2",
        )
        vendor_lbl.place(x=6, y=_CARD_H - 19)

        # Click e Drag su card
        if not is_mapped:
            def _on_press(e, p=plugin):
                self._drag_data = {
                    "plugin": p,
                    "start_x": e.x_root,
                    "start_y": e.y_root,
                    "dragging": False,
                }

            def _on_motion(e):
                if not getattr(self, "_drag_data", None):
                    return
                dx = abs(e.x_root - self._drag_data["start_x"])
                dy = abs(e.y_root - self._drag_data["start_y"])
                if not self._drag_data["dragging"] and (dx > 6 or dy > 6):
                    self._drag_data["dragging"] = True
                    self._start_drag_avatar(self._drag_data["plugin"], e.x_root, e.y_root)
                if self._drag_data["dragging"]:
                    self._update_drag_avatar(e.x_root, e.y_root)
                    deck_win = getattr(self.master, "_deck_win", None)
                    if deck_win and deck_win.winfo_exists():
                        deck_win.on_drag_motion(e.x_root, e.y_root, self._drag_data["plugin"])

            def _on_release(e, p=plugin):
                if not getattr(self, "_drag_data", None):
                    return
                was_dragging = self._drag_data["dragging"]
                self._stop_drag_avatar()
                deck_win = getattr(self.master, "_deck_win", None)
                if was_dragging:
                    if deck_win and deck_win.winfo_exists():
                        deck_win.on_drag_drop(e.x_root, e.y_root, p)
                else:
                    self._show_detail(p)
                self._drag_data = None

            for w in (card, img_lbl, name_lbl, vendor_lbl):
                w.bind("<ButtonPress-1>", _on_press)
                w.bind("<B1-Motion>", _on_motion)
                w.bind("<ButtonRelease-1>", _on_release)
        else:
            _cb = lambda e, p=plugin: self._show_detail(p)
            for w in (card, img_lbl, name_lbl, vendor_lbl):
                w.bind("<Button-1>", _cb)

        if is_mapped:
            mapped_data = self._mapped_info.get(plugin.guid.strip("{}").upper())
            badge = ctk.CTkFrame(
                card,
                fg_color="#132417",
                border_color="#2f663c",
                border_width=1,
                corner_radius=4,
                height=18,
            )
            badge.place(x=8, y=8)
            badge_lbl = ctk.CTkLabel(
                badge,
                text="🎛 Mapped",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color="#6acc80",
                fg_color="transparent",
            )
            badge_lbl.pack(padx=4, pady=0)

            tip_parts = ["Mapped to Stream Deck"]
            if mapped_data and mapped_data.get("sd"):
                page_name, pos = mapped_data["sd"]
                tip_parts.append(f"Position: {page_name} · Slot {pos}")
            if mapped_data and mapped_data.get("shortcut"):
                tip_parts.append(f"Shortcut: {mapped_data['shortcut']}")
            tip_str = "\n".join(tip_parts)
            tooltip(badge, tip_str)
            tooltip(badge_lbl, tip_str)
            badge.bind("<Button-1>", _cb)
            badge_lbl.bind("<Button-1>", _cb)

        star_btn = ctk.CTkButton(
            card,
            text="★" if is_fav else "☆",
            width=22, height=20, corner_radius=4,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#2a2a3a",
            text_color=_YELLOW if is_fav else "#3a3a5a",
        )
        star_btn.configure(command=lambda p=plugin, b=star_btn: self._toggle_fav(p, b))
        star_btn.place(x=_CARD_W - 27, y=_CARD_H - 22)
        tooltip(star_btn, "Remove from favorites" if is_fav else "Add to favorites")

        # Bottone hide: "⊗" = nascondi, "↩" = ripristina (nella view Nascosti)
        in_hidden_view = (self._current_cat == "Hidden")
        hide_btn = ctk.CTkButton(
            card,
            text="↩" if in_hidden_view else "⊗",
            width=22, height=20, corner_radius=4,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color="#2a2a3a",
            text_color="#555577" if not in_hidden_view else "#8888aa",
        )
        hide_btn.configure(command=lambda p=plugin, b=hide_btn: self._toggle_hide(p, b))
        hide_btn.place(x=_CARD_W - 52, y=_CARD_H - 22)
        tooltip(hide_btn, "Restore / unhide plugin" if in_hidden_view else "Hide plugin")

        self._pending_images.append((img_lbl, plugin.guid.upper()))
        return card

    # ---------------------------------------------------------------- drag & drop avatar

    def _start_drag_avatar(self, plugin: Plugin, x_root: int, y_root: int):
        self._stop_drag_avatar()
        try:
            self._drag_avatar = ctk.CTkToplevel(self)
            self._drag_avatar.overrideredirect(True)
            self._drag_avatar.attributes("-topmost", True)
            try:
                self._drag_avatar.attributes("-alpha", 0.92)
            except Exception:
                pass

            box = ctk.CTkFrame(
                self._drag_avatar,
                fg_color="#182538",
                border_color="#3e885b",
                border_width=2,
                corner_radius=8,
            )
            box.pack(fill="both", expand=True)

            ctk.CTkLabel(
                box,
                text=f"🎛  {plugin.name}",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#ffffff",
            ).pack(padx=14, pady=(7, 2))

            v_txt = f"{plugin.vendor} · Drag to SD Map" if plugin.vendor else "Drag to SD Map"
            ctk.CTkLabel(
                box,
                text=v_txt,
                font=ctk.CTkFont(size=9),
                text_color="#88d5ae",
            ).pack(padx=14, pady=(0, 7))

            self._drag_avatar.geometry(f"+{x_root + 14}+{y_root + 14}")
        except Exception:
            self._drag_avatar = None

    def _update_drag_avatar(self, x_root: int, y_root: int):
        if self._drag_avatar and self._drag_avatar.winfo_exists():
            try:
                self._drag_avatar.geometry(f"+{x_root + 14}+{y_root + 14}")
            except Exception:
                pass

    def _stop_drag_avatar(self):
        if getattr(self, "_drag_avatar", None) and self._drag_avatar.winfo_exists():
            try:
                self._drag_avatar.destroy()
            except Exception:
                pass
        self._drag_avatar = None

    def _on_drag_cancel(self, event=None):
        if getattr(self, "_drag_data", None):
            self._stop_drag_avatar()
            deck_win = getattr(self.master, "_deck_win", None)
            if deck_win and deck_win.winfo_exists():
                deck_win.on_drag_cancel()
            self._drag_data = None

    # ---------------------------------------------------------------- image loading

    def _get_placeholder(self) -> ctk.CTkImage:
        if self._placeholder is None:
            img = Image.new("RGB", (_IMG_W, _IMG_H), "#111122")
            self._placeholder = ctk.CTkImage(img, size=(_IMG_W, _IMG_H))
        return self._placeholder

    def _load_next_image(self):
        if not self._pending_images:
            return
        img_lbl, guid = self._pending_images.pop(0)
        if not img_lbl.winfo_exists():
            self.after(0, self._load_next_image)
            return
        ctk_img = self._get_ctk_image(guid)
        if ctk_img and img_lbl.winfo_exists():
            img_lbl.configure(image=ctk_img)
        self.after(5, self._load_next_image)

    def _get_ctk_image(self, guid_upper: str) -> ctk.CTkImage | None:
        if guid_upper in self._img_cache:
            return self._img_cache[guid_upper]
        path = self._snap_map.get(guid_upper)
        if not path:
            return None
        try:
            pil_img = Image.open(path).convert("RGB")
            w, h = pil_img.size
            target_ratio = _IMG_W / _IMG_H
            current_ratio = w / h
            if current_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left  = (w - new_w) // 2
                pil_img = pil_img.crop((left, 0, left + new_w, h))
            else:
                new_h = int(w / target_ratio)
                top   = (h - new_h) // 2
                pil_img = pil_img.crop((0, top, w, top + new_h))
            pil_img = pil_img.resize((_IMG_W, _IMG_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(pil_img, size=(_IMG_W, _IMG_H))
            self._img_cache[guid_upper] = ctk_img
            return ctk_img
        except Exception:
            return None

    # ---------------------------------------------------------------- favorites

    def _toggle_fav(self, plugin: Plugin, btn: ctk.CTkButton):
        guid = plugin.guid.upper()
        if guid in self._favorites:
            self._favorites.discard(guid)
            is_fav = False
        else:
            self._favorites.add(guid)
            is_fav = True
        _save_favorites(self._favorites)

        if btn.winfo_exists():
            btn.configure(
                text="★" if is_fav else "☆",
                text_color=_YELLOW if is_fav else "#3a3a5a",
            )
            is_mapped = self._is_mapped(plugin)
            b_clr = _YELLOW if is_fav else ("#2e5438" if is_mapped else "#2a2a40")
            btn.master.configure(
                border_color=b_clr,
                border_width=2 if (is_fav or is_mapped) else 1,
            )
            tooltip(btn, "Remove from favorites" if is_fav else "Add to favorites")

        fav_btn = self._cat_buttons.get("Favorites")
        if fav_btn and fav_btn.winfo_exists():
            fav_btn.configure(text=f"  ★  Favorites  ({len(self._favorites)})")

        if self._current_cat == "Favorites":
            self._refresh()

    # ---------------------------------------------------------------- hide

    def _toggle_hide(self, plugin: Plugin, btn: ctk.CTkButton):
        guid = plugin.guid.upper()
        if guid in self._hidden:
            self._hidden.discard(guid)
        else:
            self._hidden.add(guid)
        _save_hidden(self._hidden)

        # Aggiorna sidebar e contatori
        self._rebuild_sidebar_cats()

        # Il plugin scompare/riappare → ricarica la view corrente
        self._refresh()


    # ================================================================ DETAIL VIEW

    def _show_detail(self, plugin: Plugin):
        """Nasconde la grid e mostra la vista dettaglio del plugin."""
        if self._scroll_visible:
            self._scroll.grid_forget()
        else:
            self._empty_lbl.grid_forget()

        if self._detail_frame and self._detail_frame.winfo_exists():
            self._detail_frame.destroy()

        self._detail_frame = ctk.CTkFrame(self._grid_outer, fg_color="transparent")
        self._detail_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._detail_frame.grid_columnconfigure(1, weight=1)
        self._detail_frame.grid_rowconfigure(1, weight=1)

        # ---- back button ------------------------------------------------
        ctk.CTkButton(
            self._detail_frame,
            text="← Back",
            width=110, height=30, corner_radius=6,
            fg_color="#1e1e2e", hover_color="#2e2e4e",
            font=self._f_small,
            command=self._back_to_grid,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # ---- left panel (immagine + info) -------------------------------
        left = ctk.CTkFrame(self._detail_frame, fg_color="transparent", width=420)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        left.grid_propagate(False)

        img_lbl = ctk.CTkLabel(
            left, text="", image=self._get_placeholder(),
            width=_DETAIL_IMG_W, height=_DETAIL_IMG_H,
            fg_color="#111122", corner_radius=8,
        )
        img_lbl.place(x=10, y=0)
        self.after(10, lambda: self._load_detail_image(plugin.guid.upper(), img_lbl))

        ctk.CTkLabel(
            left, text=plugin.name,
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color="#dce4ee", anchor="w",
            wraplength=400, justify="left", fg_color="transparent",
        ).place(x=10, y=_DETAIL_IMG_H + 12)

        ctk.CTkLabel(
            left, text=plugin.vendor or "—",
            font=ctk.CTkFont(size=12), text_color="#7a7a8a",
            anchor="w", fg_color="transparent",
        ).place(x=10, y=_DETAIL_IMG_H + 38)

        ctk.CTkLabel(
            left, text=plugin.sub_category or "—",
            font=ctk.CTkFont(size=11), text_color="#4a5a6a",
            anchor="w", fg_color="transparent",
        ).place(x=10, y=_DETAIL_IMG_H + 56)

        # Bottoni fav + hide + eventuale box Mapped
        is_mapped = self._is_mapped(plugin)
        if is_mapped:
            m_info = self._mapped_info.get(plugin.guid.strip("{}").upper(), {})
            sd_txt = f"{m_info['sd'][0]} · Slot {m_info['sd'][1]}" if m_info.get("sd") else "Mapped"
            sc_txt = m_info.get("shortcut") or "—"

            mapped_box = ctk.CTkFrame(
                left, fg_color="#122418", border_color="#2b5836",
                border_width=1, corner_radius=6, height=30,
            )
            mapped_box.place(x=10, y=_DETAIL_IMG_H + 78, width=348)
            ctk.CTkLabel(
                mapped_box,
                text=f"🎛  SD: {sd_txt}   |   {sc_txt}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#6acc80",
            ).place(relx=0.5, rely=0.5, anchor="center")
            btn_y = _DETAIL_IMG_H + 118
        else:
            btn_y = _DETAIL_IMG_H + 85

        is_fav  = plugin.guid.upper() in self._favorites
        is_hide = plugin.guid.upper() in self._hidden

        self._detail_fav_btn = ctk.CTkButton(
            left,
            text=("★  Favorite" if is_fav else "☆  Add to favorites"),
            width=200, height=32, corner_radius=6,
            fg_color="#2a2a10" if is_fav else "#1e1e2e",
            hover_color="#3a3a20" if is_fav else "#2e2e4e",
            text_color=_YELLOW if is_fav else "#888888",
            font=self._f_small,
        )
        self._detail_fav_btn.configure(command=lambda p=plugin: self._detail_toggle_fav(p))
        self._detail_fav_btn.place(x=10, y=btn_y)

        self._detail_hide_btn = ctk.CTkButton(
            left,
            text=("↩  Unhide" if is_hide else "⊗  Hide"),
            width=140, height=32, corner_radius=6,
            fg_color="#2a1010" if is_hide else "transparent",
            hover_color="#3a2020",
            border_width=0 if is_hide else 1,
            border_color="#333355",
            text_color="#cc6666" if is_hide else "#555577",
            font=self._f_small,
        )
        self._detail_hide_btn.configure(command=lambda p=plugin: self._detail_toggle_hide(p))
        self._detail_hide_btn.place(x=218, y=btn_y)

        # ---- right panel (note) ----------------------------------------
        right = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            right, text="Notes",
            font=self._f_hdr, text_color="#7a8aaa", anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        self._detail_textbox = ctk.CTkTextbox(
            right, font=ctk.CTkFont(size=12), wrap="word",
            fg_color="#111122", border_color="#2a2a40",
            border_width=1, corner_radius=8,
        )
        self._detail_textbox.grid(row=1, column=0, sticky="nsew")

        existing = self._notes.get(plugin.guid.upper(), "")
        if existing:
            self._detail_textbox.insert("1.0", existing)

        self._detail_textbox.bind(
            "<KeyRelease>", lambda e, p=plugin: self._on_note_change(p),
        )

    def _back_to_grid(self):
        if self._detail_frame and self._detail_frame.winfo_exists():
            self._detail_frame.destroy()
            self._detail_frame = None
        if self._scroll_visible:
            self._scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        else:
            self._empty_lbl.grid(row=0, column=0)

    def _load_detail_image(self, guid_upper: str, label: ctk.CTkLabel):
        path = self._snap_hires.get(guid_upper)
        if not path or not label.winfo_exists():
            return
        try:
            pil_img = Image.open(path).convert("RGB")
            w, h = pil_img.size
            ratio = _DETAIL_IMG_W / _DETAIL_IMG_H
            if w / h > ratio:
                nw = int(h * ratio)
                pil_img = pil_img.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
            else:
                nh = int(w / ratio)
                pil_img = pil_img.crop((0, (h - nh) // 2, w, (h + nh) // 2))
            pil_img = pil_img.resize((_DETAIL_IMG_W, _DETAIL_IMG_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(pil_img, size=(_DETAIL_IMG_W, _DETAIL_IMG_H))
            if label.winfo_exists():
                label.configure(image=ctk_img)
        except Exception:
            pass

    def _on_note_change(self, plugin: Plugin):
        if self._note_save_id:
            self.after_cancel(self._note_save_id)
        self._note_save_id = self.after(600, lambda: self._flush_note(plugin))

    def _flush_note(self, plugin: Plugin):
        if not self._detail_textbox or not self._detail_textbox.winfo_exists():
            return
        text = self._detail_textbox.get("1.0", "end-1c").strip()
        guid = plugin.guid.upper()
        if text:
            self._notes[guid] = text
        else:
            self._notes.pop(guid, None)
        _save_notes(self._notes)

    def _detail_toggle_fav(self, plugin: Plugin):
        guid = plugin.guid.upper()
        if guid in self._favorites:
            self._favorites.discard(guid)
            is_fav = False
        else:
            self._favorites.add(guid)
            is_fav = True
        _save_favorites(self._favorites)
        self._detail_fav_btn.configure(
            text=("★  Favorite" if is_fav else "☆  Add to favorites"),
            fg_color="#2a2a10" if is_fav else "#1e1e2e",
            hover_color="#3a3a20" if is_fav else "#2e2e4e",
            text_color=_YELLOW if is_fav else "#888888",
        )
        fav_btn = self._cat_buttons.get("Favorites")
        if fav_btn and fav_btn.winfo_exists():
            fav_btn.configure(text=f"  ★  Favorites  ({len(self._favorites)})")

    def _detail_toggle_hide(self, plugin: Plugin):
        guid = plugin.guid.upper()
        if guid in self._hidden:
            self._hidden.discard(guid)
            is_hide = False
        else:
            self._hidden.add(guid)
            is_hide = True
        _save_hidden(self._hidden)
        self._detail_hide_btn.configure(
            text=("↩  Unhide" if is_hide else "⊗  Hide"),
            fg_color="#2a1010" if is_hide else "transparent",
            border_width=0 if is_hide else 1,
            text_color="#cc6666" if is_hide else "#555577",
        )
        self._rebuild_sidebar_cats()

