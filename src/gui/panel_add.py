"""Pannello destro: ricerca plugin e form per aggiungere una nuova assegnazione."""
from __future__ import annotations

import re
import tkinter as tk
import customtkinter as ctk

import json

from src.models import Plugin, Macro
from src.parsers import plugins_catalog
from src.parsers import plugin_presentation
from src.parsers.deck_profile import load_profile, get_categories
from src.core.config import CACHE_DIR, MACRO_PREFIX
from src.gui.widgets import tooltip as _tooltip, center_over_parent
from src.gui.snapshots_loader import find_plugin_snapshot
from src.writers.macro_writer import write_macro_file
from src.writers.keyscheme_writer import add_macro_shortcut
from src.writers.deck_writer import add_hotkey_to_page

_HIDE_FILE = CACHE_DIR / "hidden.json"

_CAT_SKIP = {
    "AudioEdit", "Engine", "EventEdit", "FileBrowser", "MusicEdit",
    "MusicPartEdit", "Project", "ProjectEdit", "Show", "ShowEdit", "TrackEdit", "VST3",
}


def _plugin_cat(p: Plugin, pres_map: dict[str, str]) -> str:
    """Category for a plugin: from PluginPresentation first, then derived from sub_category."""
    key = p.guid.upper().strip("{}")
    cat = pres_map.get(key, "")
    if cat:
        return cat
    s = p.sub_category
    for prefix in ("VST3/", "(Native)/"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.split("/")[0].strip()
    return "zzzz" if (not s or s in _CAT_SKIP) else s


def _load_hidden() -> set[str]:
    try:
        data = json.loads(_HIDE_FILE.read_text(encoding="utf-8"))
        return set(data.get("hidden", []))
    except Exception:
        return set()

from src.core.config import KEYSCHEME

_YELLOW = "#c8a838"

# Tasti e simboli supportati da Stream Deck e sicuri per macro di Studio One (escluso '+' per evitare ambiguità)
_CANDIDATE_SYMBOLS = [
    "%", "^", "*", "(", ")", "_",
    ";", "=", ",", "-", ".", "/", "`",
    "[", "]", "\\", "'",
    "!", "@", "#", "$",
    "{", "}", "|", ":", '"', "<", ">", "?"
]
_CANDIDATE_LETTERS = [chr(c) for c in range(65, 91)]   # A-Z
_CANDIDATE_DIGITS  = [str(d) for d in range(10)]        # 0-9
_CANDIDATE_FKEYS   = [f"F{i}" for i in range(1, 13)]    # F1-F12


def get_free_shortcuts(keyscheme_path=KEYSCHEME) -> list[str]:
    """Legge user.keyscheme dal vivo e restituisce solo combinazioni realmente non assegnate."""
    try:
        content = keyscheme_path.read_text(encoding="utf-8")
        used = set(re.findall(r'<Key\s+name="([^"]+)"', content))
    except Exception:
        used = set()

    # Priorità: simboli sicuri, combinazioni a 4 tasti (Ctrl+Shift+Alt) con lettere/numeri, poi combinazioni a 3 tasti
    candidates = (
        [f"Ctrl+Alt+{s}" for s in _CANDIDATE_SYMBOLS] +
        [f"Ctrl+Shift+Alt+{s}" for s in _CANDIDATE_SYMBOLS] +
        [f"Ctrl+Shift+Alt+{k}" for k in _CANDIDATE_LETTERS] +
        [f"Ctrl+Alt+{k}" for k in _CANDIDATE_LETTERS] +
        [f"Ctrl+Shift+Alt+{d}" for d in _CANDIDATE_DIGITS] +
        [f"Ctrl+Alt+{d}" for d in _CANDIDATE_DIGITS] +
        [f"Ctrl+Shift+Alt+{f}" for f in _CANDIDATE_FKEYS] +
        [f"Ctrl+Alt+{f}" for f in _CANDIDATE_FKEYS]
    )
    free = [c for c in candidates if c not in used]
    return free



# Colonne risultati: (chiave attr, label, larghezza px)
_COLS = [
    ("name",         "Plugin",   285),
    ("vendor",       "Vendor",   225),
    ("sub_category", "Category", 60),
]
_BADGE_W = 22
_MAX_RESULTS = 200   # cap display; affina la ricerca per vedere altri


def _auto_macro_title(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]", "", name)
    return f"{MACRO_PREFIX}{clean[:18]}"


def _auto_sd_title(name: str) -> str:
    parts = name.split(" ", 1)
    return "\n".join(parts) if len(parts) > 1 else name


def _bind_combo_click(combo: ctk.CTkComboBox) -> ctk.CTkComboBox:
    """Apre il dropdown anche cliccando sul campo testo, non solo sulla freccia."""
    combo._entry.bind("<Button-1>", lambda e: combo._open_dropdown_menu())
    return combo


def _plugin_key(p: Plugin, col: str) -> str:
    return getattr(p, col, "").lower()


class PanelAdd(ctk.CTkFrame):

    def __init__(self, parent, catalog: dict[str, Plugin], macros: list[Macro]):
        super().__init__(parent, corner_radius=10)
        self._all_plugins    = list(catalog.values())
        self._existing_guids = {m.guid for m in macros if m.guid}
        self._pres_map = plugin_presentation.load()
        self._hidden   = _load_hidden()

        # Categorie disponibili (esclude zzzz e plugin nascosti)
        _cats = sorted({
            _plugin_cat(p, self._pres_map)
            for p in self._all_plugins
            if _plugin_cat(p, self._pres_map) != "zzzz"
            and p.guid.upper() not in self._hidden
        })
        self._all_cats = _cats


        # Categorie SD lette dinamicamente dal profilo Stream Deck
        try:
            _main, _all, _, _ = load_profile()
            self._categories = get_categories(_main, _all)
        except Exception:
            self._categories = []
        self._sd_slots     = {c["name"]: (c["used"], c["total"]) for c in self._categories}
        self._sd_uuids     = {c["name"]: c["uuid"] for c in self._categories}
        self._cat_names    = [c["name"] for c in self._categories]
        self._selected_plugin: Plugin | None = None
        self._result_rows: list[ctk.CTkFrame] = []
        self._filtered: list[Plugin] = []


        self._sort_col = "name"
        self._sort_asc = True
        self._hdr_labels: dict[str, ctk.CTkLabel] = {}

        self._f_title  = ctk.CTkFont(size=13, weight="bold")
        self._f_label  = ctk.CTkFont(size=12)
        self._f_sub    = ctk.CTkFont(size=11)
        self._f_result = ctk.CTkFont(size=12)
        self._f_small  = ctk.CTkFont(size=11)
        self._f_hdr    = ctk.CTkFont(size=11, weight="bold")

        self._search_var   = ctk.StringVar()
        self._type_var     = ctk.StringVar(value="All")
        self._vendor_var   = ctk.StringVar(value="All")
        self._cat_var      = ctk.StringVar(value="All")
        self._macro_var    = ctk.StringVar()
        self._free_shortcuts = get_free_shortcuts()
        self._shortcut_var = ctk.StringVar(value=self._free_shortcuts[0] if self._free_shortcuts else "")
        self._sdcat_var    = ctk.StringVar()
        self._sdtitle_var  = ctk.StringVar()


        # Guard: preview labels non esistono finché _build_form non le crea
        self._prev_macro: ctk.CTkLabel | None = None
        self._prev_key:   ctk.CTkLabel | None = None
        self._prev_sd:    ctk.CTkLabel | None = None

        # _search_var: solo su Return o click bottone (non a ogni carattere)
        self._type_var.trace_add("write",   self._apply_filter)
        self._vendor_var.trace_add("write", self._apply_filter)
        self._cat_var.trace_add("write",    self._apply_filter)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)   # lista espande

        self._build_title()
        self._build_search()
        self._build_results_header()
        self._build_results_list()
        self._build_form()
        self._build_action()
        # lista inizia vuota — almeno 1 filtro richiesto

    # ------------------------------------------------------------------ build

    def _cat_label(self, cat: str) -> str:
        used, total = self._sd_slots.get(cat, (0, 7))
        tag = " ⛔" if used >= total else f" ({used}/{total})"
        return f"{cat}{tag}"

    def _build_title(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="ADD PLUGIN",
            font=self._f_title, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._refresh_btn = ctk.CTkButton(
            frame, text="↻ Refresh catalog",
            font=self._f_small, height=26, width=140,
            fg_color="#2a3a2a", hover_color="#3a5a3a",
            command=self._on_refresh,
        )
        self._refresh_btn.grid(row=0, column=1, sticky="e")

    def _build_search(self):
        # Riga 1: filtri Produttore + Tipo
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        filter_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            filter_frame, text="Vendor:", font=self._f_sub,
            text_color="#888888", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 4))

        vendors = ["All"] + sorted({p.vendor for p in self._all_plugins if p.vendor})
        _bind_combo_click(ctk.CTkComboBox(
            filter_frame, variable=self._vendor_var,
            values=vendors,
            height=30, font=self._f_sub, state="readonly",
        )).grid(row=0, column=1, sticky="ew", padx=(0, 8))

        _bind_combo_click(ctk.CTkComboBox(
            filter_frame, variable=self._type_var,
            values=["All", "Effect", "Instrument", "Native"],
            width=118, height=30, font=self._f_sub,
            state="readonly",
        )).grid(row=0, column=2)

        ctk.CTkLabel(
            filter_frame, text="Category:", font=self._f_sub,
            text_color="#888888", anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(3, 0))

        _bind_combo_click(ctk.CTkComboBox(
            filter_frame, variable=self._cat_var,
            values=["All"] + self._all_cats,
            height=30, font=self._f_sub, state="readonly",
        )).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(3, 0))

        # Riga 2: campo ricerca + bottone
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 2))
        search_frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            search_frame, textvariable=self._search_var,
            placeholder_text="Search by name...  (Enter or →)",
            height=30, font=self._f_sub,
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        entry.bind("<Return>", lambda e: self._apply_filter())

        btn_search = ctk.CTkButton(
            search_frame, text="→", width=32, height=30,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._apply_filter,
        )
        btn_search.grid(row=0, column=1)
        _tooltip(btn_search, "Search  (or press Enter)")

    def _build_results_header(self):
        """Header fisso con larghezze identiche alle righe risultati."""
        hdr = ctk.CTkFrame(self, fg_color="#1a1a2e", corner_radius=6, height=26)
        hdr.grid(row=3, column=0, sticky="ew", padx=14, pady=(2, 1))
        hdr.pack_propagate(False)

        for key, label, w in _COLS:
            lbl = ctk.CTkLabel(
                hdr, text=label, width=w,
                font=self._f_hdr, text_color="#7a8aaa",
                anchor="w", cursor="hand2",
            )
            lbl.pack(side="left", padx=(8 if key == "name" else 0, 0))
            self._hdr_labels[key] = lbl
            lbl.bind("<Button-1>", lambda e, k=key: self._set_sort(k))

        # label conteggio risultati a destra
        self._count_lbl = ctk.CTkLabel(
            hdr, text="", font=self._f_small, text_color="#505050", anchor="e",
        )
        self._count_lbl.pack(side="right", padx=(0, 8))

        self._refresh_header_labels()

    def _build_results_list(self):
        self._results_scroll = ctk.CTkScrollableFrame(self, corner_radius=6)
        self._results_scroll.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 0))
        self._results_scroll.grid_columnconfigure(0, weight=1)

    def _build_form(self):
        sep = ctk.CTkFrame(self, height=1, fg_color="#333333")
        sep.grid(row=5, column=0, sticky="ew", padx=14, pady=(8, 8))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=6, column=0, sticky="ew", padx=14)
        form.grid_columnconfigure(1, weight=1)

        # Macro title
        ctk.CTkLabel(form, text="Macro:", width=92,
                     font=self._f_label, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=3)
        ctk.CTkEntry(
            form, textvariable=self._macro_var,
            placeholder_text=f"{MACRO_PREFIX}NomePlugin",
            height=30, font=self._f_sub,
        ).grid(row=0, column=1, sticky="ew", pady=3)

        # Shortcut
        ctk.CTkLabel(form, text="Shortcut:", width=92,
                     font=self._f_label, anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=3)

        sc_frame = ctk.CTkFrame(form, fg_color="transparent")
        sc_frame.grid(row=1, column=1, sticky="ew", pady=3)
        sc_frame.grid_columnconfigure(0, weight=1)
        self._shortcut_combo = _bind_combo_click(ctk.CTkComboBox(
            sc_frame, variable=self._shortcut_var,
            values=self._free_shortcuts,
            height=30, font=self._f_sub, state="readonly",
        ))
        self._shortcut_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkLabel(
            sc_frame, text="auto", width=36,
            font=self._f_small, text_color="#1f6aa5",
        ).grid(row=0, column=1)

        # SD Categoria
        ctk.CTkLabel(form, text="SD Category:", width=92,
                     font=self._f_label, anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=3)

        sd_frame = ctk.CTkFrame(form, fg_color="transparent")
        sd_frame.grid(row=2, column=1, sticky="ew", pady=3)
        sd_frame.grid_columnconfigure(0, weight=1)
        self._sdcat_combo = _bind_combo_click(ctk.CTkComboBox(
            sd_frame, variable=self._sdcat_var,
            values=[self._cat_label(c) for c in self._cat_names],
            height=30, font=self._f_sub, state="readonly",
            command=self._on_cat_changed,
        ))
        self._sdcat_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._sdcat_var.set(self._cat_label(self._cat_names[0]) if self._cat_names else "")

        self._sdcat_warn = ctk.CTkLabel(
            sd_frame, text="", width=60,
            font=self._f_small, text_color="#FFA500",
        )
        self._sdcat_warn.grid(row=0, column=1)

        # Titolo SD
        ctk.CTkLabel(form, text="SD Title:", width=92,
                     font=self._f_label, anchor="w",
        ).grid(row=3, column=0, sticky="nw", pady=(5, 3))
        ctk.CTkEntry(
            form, textvariable=self._sdtitle_var,
            placeholder_text='es. Pro-Q\\n4',
            height=30, font=self._f_sub,
        ).grid(row=3, column=1, sticky="ew", pady=(5, 3))

        ctk.CTkLabel(
            form,
            text='Use \\n for line break on button  (e.g. "AirEQ\\nPremium")',
            font=self._f_small, text_color=_YELLOW, anchor="w",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))

        # Preview
        prev = ctk.CTkFrame(form, fg_color="#1a1a1a", corner_radius=6)
        prev.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        prev.grid_columnconfigure(0, weight=1)

        self._prev_macro = self._make_prev_line(prev, 0)
        self._prev_key   = self._make_prev_line(prev, 1)
        self._prev_sd    = self._make_prev_line(prev, 2)

        # Aggiorna preview live
        for var in (self._macro_var, self._shortcut_var, self._sdcat_var, self._sdtitle_var):
            var.trace_add("write", lambda *_: self._update_preview())

        # Ora che i widget esistono, aggiorna cat warn e preview
        self._on_cat_changed(self._sdcat_var.get())

    def _make_prev_line(self, parent, row: int) -> ctk.CTkLabel:
        lbl = ctk.CTkLabel(
            parent, text="", font=self._f_small,
            text_color="#606060", anchor="w",
        )
        lbl.grid(row=row, column=0, sticky="w", padx=10, pady=1)
        return lbl

    def _build_action(self):
        sep = ctk.CTkFrame(self, height=1, fg_color="#333333")
        sep.grid(row=7, column=0, sticky="ew", padx=14, pady=(6, 8))

        self._btn_create = ctk.CTkButton(
            self, text="MAKE FILES",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=42, corner_radius=8,
            command=self._on_create,
        )
        self._btn_create.grid(row=8, column=0, sticky="ew", padx=14, pady=(0, 14))

    # -------------------------------------------------------------- sort

    def _set_sort(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._refresh_header_labels()
        self._apply_filter()   # ri-ordina e ri-renderizza

    def _refresh_header_labels(self):
        for key, label, _ in _COLS:
            lbl = self._hdr_labels.get(key)
            if lbl is None:
                continue
            if key == self._sort_col:
                arrow = " ↑" if self._sort_asc else " ↓"
                lbl.configure(text=label + arrow, text_color="#dce4ee")
            else:
                lbl.configure(text=label, text_color="#7a8aaa")

    # ---------------------------------------------------------- filter / render

    def _apply_filter(self, *args):
        q      = self._search_var.get().strip().lower()
        typ    = self._type_var.get()
        vendor = self._vendor_var.get()
        cat    = self._cat_var.get()

        # Almeno un filtro attivo
        if typ == "All" and vendor == "All" and cat == "All" and not q:
            self._render_results([])
            self._count_lbl.configure(text="", text_color="#505050")
            return

        filtered: list[Plugin] = []
        for p in self._all_plugins:
            if _plugin_cat(p, self._pres_map) == "zzzz":
                continue
            if p.guid.upper() in self._hidden:
                continue
            if cat != "All" and _plugin_cat(p, self._pres_map) != cat:
                continue
            if typ == "Effect" and p.category != "AudioEffect":
                continue
            if typ == "Instrument" and "Synth" not in p.category and "Instrument" not in p.category:
                continue
            if typ == "Native" and not p.sub_category.startswith("(Native)"):
                continue
            if vendor != "All" and p.vendor != vendor:
                continue
            if q and q not in p.name.lower() \
                  and q not in p.sub_category.lower() \
                  and q not in p.vendor.lower():
                continue
            filtered.append(p)

        # Sort: non-configurati prima, ordinati; configurati in fondo
        key_fn = lambda p: _plugin_key(p, self._sort_col)
        not_conf = sorted([p for p in filtered if p.guid not in self._existing_guids],
                          key=key_fn, reverse=not self._sort_asc)
        conf     = sorted([p for p in filtered if p.guid in self._existing_guids],
                          key=key_fn, reverse=not self._sort_asc)
        self._filtered = not_conf + conf

        self._render_results(self._filtered)

        n = len(self._filtered)
        self._count_lbl.configure(
            text=f"{n} plugins" if n else "",
            text_color="#505050",
        )

    def _render_results(self, plugins: list[Plugin]):
        for r in self._result_rows:
            r.destroy()
        self._result_rows.clear()
        self._results_scroll._parent_canvas.yview_moveto(0)

        for i, plugin in enumerate(plugins):
            already    = plugin.guid in self._existing_guids
            bg         = "#2a2a35" if i % 2 == 0 else "#222230"
            name_color = "#666666" if already else "#e0e8ff"
            vnd_color  = "#4a4a5a" if already else "#9a8a7a"
            sub_color  = "#4a4a5a" if already else "#6a8aaa"

            row = ctk.CTkFrame(
                self._results_scroll, fg_color=bg,
                corner_radius=3, height=30,
            )
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.grid_propagate(False)
            self._result_rows.append(row)

            ctk.CTkLabel(
                row, text=plugin.name, width=_COLS[0][2],
                font=self._f_result, text_color=name_color, anchor="w",
            ).pack(side="left", padx=(8, 0))

            ctk.CTkLabel(
                row, text=plugin.vendor or "—", width=_COLS[1][2],
                font=self._f_small, text_color=vnd_color, anchor="w",
            ).pack(side="left")

            sub_cat = (plugin.sub_category or "—").replace("VST3/", "").replace("(Native)/", "")
            ctk.CTkLabel(
                row, text=sub_cat, width=_COLS[2][2],
                font=self._f_small, text_color=sub_color, anchor="w",
            ).pack(side="left")

            if already:
                ctk.CTkLabel(
                    row, text="✓", width=_BADGE_W,
                    font=self._f_small, text_color="#336633",
                ).pack(side="left")

            _p = plugin
            row.bind("<Button-1>", lambda e, p=_p: self._on_plugin_selected(p))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, p=_p: self._on_plugin_selected(p))

    # ----------------------------------------------------------- event handlers

    def _on_plugin_selected(self, plugin: Plugin):
        self._selected_plugin = plugin
        self._macro_var.set(_auto_macro_title(plugin.name))
        self._sdtitle_var.set(_auto_sd_title(plugin.name))
        if self._free_shortcuts:
            self._shortcut_var.set(self._free_shortcuts[0])

        suggested = self._suggest_category(plugin.sub_category)
        if suggested:
            self._sdcat_var.set(self._cat_label(suggested))
            self._on_cat_changed(self._cat_label(suggested))
        self._update_preview()

    def _suggest_category(self, sub_cat: str) -> str | None:
        """Returns the best matching SD category name from self._cat_names, or None."""
        sc = sub_cat.lower()
        # (keyword in sub_cat) → list of search terms to look for in SD category names
        _MAP = [
            ("eq",         ["eq"]),
            ("reverb",     ["reverb"]),
            ("dynamics",   ["dynamics", "compress"]),
            ("compressor", ["compress", "dynamics"]),
            ("limiter",    ["limit"]),
            ("filter",     ["filter"]),
            ("delay",      ["delay"]),
            ("spatial",    ["spatial"]),
            ("distort",    ["distort"]),
            ("modulation", ["modulation"]),
            ("synth",      ["synth", "instrument", "strument"]),
            ("instrument", ["synth", "instrument", "strument"]),
        ]
        for key, search_terms in _MAP:
            if key in sc:
                candidates = []
                for term in search_terms:
                    for cat_name in self._cat_names:
                        if term in cat_name.lower() and cat_name not in candidates:
                            candidates.append(cat_name)
                if candidates:
                    # Prefer the category with most free slots
                    return max(candidates,
                               key=lambda c: self._sd_slots.get(c, (0, 7))[1]
                                             - self._sd_slots.get(c, (0, 7))[0])
        return None

    def _on_cat_changed(self, value: str):
        cat_name = value.split(" (")[0].split(" ⛔")[0]
        used, total = self._sd_slots.get(cat_name, (0, 7))
        if used >= total:
            self._sdcat_warn.configure(text="⛔ FULL", text_color="#FF4444")
        elif used >= total - 1:
            self._sdcat_warn.configure(text=f"⚠ {used}/{total}", text_color="#FFA500")
        else:
            self._sdcat_warn.configure(text=f"{used}/{total}", text_color="#6a8a6a")
        self._update_preview()

    def _on_refresh(self):
        self._refresh_btn.configure(text="⏳ Loading...", state="disabled")
        self.update()
        try:
            new_plugins  = plugins_catalog.load(force_refresh=True)
            self._all_plugins = new_plugins
            self._pres_map = plugin_presentation.load(force_refresh=True)
            self._hidden = _load_hidden()
            _cats = sorted({
                _plugin_cat(p, self._pres_map)
                for p in self._all_plugins
                if _plugin_cat(p, self._pres_map) != "zzzz"
                and p.guid.upper() not in self._hidden
            })
            self._all_cats = _cats
            if hasattr(self, "_cat_combo"):
                self._cat_combo.configure(values=["All"] + self._all_cats)
            info = plugins_catalog.cache_info()
            self._refresh_btn.configure(
                text=f"↻ Updated ({info.get('count','?')} plugins)",
                state="normal",
            )
        except Exception as e:

            self._refresh_btn.configure(text="✗ Error", state="normal")
        self._apply_filter()
        # Ripristina testo dopo 3s
        self.after(3000, lambda: self._refresh_btn.configure(text="↻ Refresh catalog"))

    def _update_preview(self):
        if self._prev_macro is None:
            return
        macro  = self._macro_var.get() or f"{MACRO_PREFIX}..."
        key    = self._shortcut_var.get() or "—"
        sd_raw = self._sdcat_var.get() or "—"
        cat    = sd_raw.split(" (")[0].split(" ⛔")[0]
        title  = self._sdtitle_var.get().replace("\n", "\\n") or "—"

        snap = find_plugin_snapshot(self._selected_plugin.guid) if (self._selected_plugin and self._selected_plugin.guid) else None
        icon_str = " + Icon" if snap else ""

        self._prev_macro.configure(
            text=f"  → Create  {macro}.studioonemacro", text_color="#4a7a4a")
        self._prev_key.configure(
            text=f"  → Shortcut  {key}  in user.keyscheme", text_color="#4a6a8a")
        self._prev_sd.configure(
            text=f"  → Button  [{title}]{icon_str}  in {cat}/manifest.json", text_color="#8a6a3a")

    def _on_create(self):
        errors = self._validate()
        if errors:
            self._show_dialog("Error", "\n".join(errors), color="#cc4444")
            return

        cat_name = self._sdcat_var.get().split(" (")[0].split(" ⛔")[0]
        plugin   = self._selected_plugin
        macro_title = self._macro_var.get().strip()
        shortcut = self._shortcut_var.get().strip()
        sd_title = self._sdtitle_var.get().strip()
        page_uuid = self._sd_uuids.get(cat_name)

        if not page_uuid:
            self._show_dialog("Error", f"Could not find Stream Deck page UUID for '{cat_name}'.", color="#cc4444")
            return

        snapshot_path = find_plugin_snapshot(plugin.guid) if (plugin and plugin.guid) else None
        icon_desc = f"Yes ({snapshot_path.name})" if snapshot_path else "None (text only)"

        msg = (
            f"Plugin:   {plugin.name}\n"
            f"Vendor:   {plugin.vendor or '—'}\n"
            f"GUID:     {plugin.guid}\n"
            f"Icon:     {icon_desc}\n\n"
            f"Files to write:\n"
            f"  1. Macro file:  {macro_title}.studioonemacro\n"
            f"  2. Shortcut:    {shortcut}  -> user.keyscheme\n"
            f"  3. Stream Deck: Button [{sd_title.replace(chr(10), ' ')}] in {cat_name}\n\n"
            f"Automatic backups with timestamp will be created before any changes.\n"
            f"Do you want to proceed?"
        )

        self._show_confirm_dialog(
            title="Confirm Creation",
            msg=msg,
            on_confirm=lambda: self._execute_creation(plugin, macro_title, shortcut, sd_title, page_uuid, cat_name, snapshot_path),
        )

    def _execute_creation(
        self,
        plugin: Plugin,
        macro_title: str,
        shortcut: str,
        sd_title: str,
        page_uuid: str,
        cat_name: str,
        snapshot_path: Path | None = None,
    ):
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
                icon_source_path=snapshot_path,
            )

            icon_msg = f"\n  - Plugin icon applied: {snapshot_path.name}" if snapshot_path else ""
            success_msg = (
                f"✅ ALL FILES CREATED SUCCESSFULLY!\n\n"
                f"• Macro created:\n  {created_macro_path.name}\n\n"
                f"• Shortcut assigned:\n  {shortcut} in user.keyscheme\n\n"
                f"• Stream Deck button added:\n  Slot {assigned_slot} in category '{cat_name}'{icon_msg}\n\n"
                f"Backups created in backups/:\n"
                f"  - {ks_backup.name}\n"
                f"  - {sd_backup.name}\n\n"
                f"Note: Restart Fender Studio Pro and Stream Deck to reload the new configuration."
            )
            self._show_dialog("Success", success_msg, color="#44cc44")

            # Ricarica profilo SD interno
            self._refresh_sd_profile()

            # Notifica il parent MacroEditorWindow per ricaricare PanelCurrent
            if hasattr(self.master, "reload_data"):
                self.master.reload_data()

        except Exception as exc:
            # ROLLBACK: Se la macro era stata scritta ma keyscheme o SD hanno fallito, rimuovila
            if created_macro_path and created_macro_path.exists():
                try:
                    created_macro_path.unlink()
                except Exception:
                    pass

            self._show_dialog(
                "Creation Failed",
                f"An error occurred during writing:\n\n{exc}\n\nRollback completed: no incomplete files were left.",
                color="#cc4444"
            )



    def _refresh_sd_profile(self):
        try:
            _main, _all, _, _ = load_profile()
            self._categories = get_categories(_main, _all)
            self._sd_slots  = {c["name"]: (c["used"], c["total"]) for c in self._categories}
            self._sd_uuids  = {c["name"]: c["uuid"] for c in self._categories}
            if hasattr(self, "_sdcat_combo"):
                self._sdcat_combo.configure(values=[self._cat_label(c["name"]) for c in self._categories])
        except Exception:
            pass

    def reload_macros(self, macros: list[Macro]):
        self._existing_titles = {m.title for m in macros}
        self._free_shortcuts = get_free_shortcuts()
        if hasattr(self, "_shortcut_combo"):
            self._shortcut_combo.configure(values=self._free_shortcuts)
        if self._free_shortcuts and (not self._shortcut_var.get() or self._shortcut_var.get() not in self._free_shortcuts):
            self._shortcut_var.set(self._free_shortcuts[0])



    def _validate(self) -> list[str]:
        errors = []
        if not self._selected_plugin:
            errors.append("Select a plugin from the results.")
        macro = self._macro_var.get().strip()
        if not macro:
            errors.append("Macro title cannot be empty.")
        elif not macro.startswith(MACRO_PREFIX):
            errors.append(f"Macro title must start with '{MACRO_PREFIX}'.")
        if not self._shortcut_var.get():
            errors.append("Select a shortcut.")
        cat_raw = self._sdcat_var.get()
        if not cat_raw:
            errors.append("Select a Stream Deck category.")
        else:
            cat_name = cat_raw.split(" (")[0].split(" ⛔")[0]
            used, total = self._sd_slots.get(cat_name, (0, 7))
            if used >= total:
                errors.append(f"Category '{cat_name}' is full ({used}/{total}).")
        if not self._sdtitle_var.get().strip():
            errors.append("SD title cannot be empty.")
        return errors

    def _show_dialog(self, title: str, msg: str, color: str = "#1f6aa5"):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        center_over_parent(dlg, self.winfo_toplevel(), 480, 300)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        ctk.CTkLabel(
            dlg, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color,
        ).pack(pady=(14, 6))

        tb = ctk.CTkTextbox(dlg, font=ctk.CTkFont(size=12), wrap="word")
        tb.pack(fill="both", expand=True, padx=16)
        tb.insert("1.0", msg)
        tb.configure(state="disabled")

        ctk.CTkButton(dlg, text="Close", width=100, command=dlg.destroy).pack(pady=(8, 12))

    def _show_confirm_dialog(self, title: str, msg: str, on_confirm):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        center_over_parent(dlg, self.winfo_toplevel(), 500, 340)
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.lift()

        ctk.CTkLabel(
            dlg, text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#c8a838",
        ).pack(pady=(14, 6))

        tb = ctk.CTkTextbox(dlg, font=ctk.CTkFont(size=12), wrap="word")
        tb.pack(fill="both", expand=True, padx=16)
        tb.insert("1.0", msg)
        tb.configure(state="disabled")

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=(10, 14))

        def _do_confirm():
            dlg.destroy()
            on_confirm()

        ctk.CTkButton(
            btn_row, text="Confirm and Create", width=140,
            fg_color="#2a6a2a", hover_color="#3a8a3a",
            command=_do_confirm
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="Cancel", width=100,
            fg_color="#3a3a4a", hover_color="#4a4a5a",
            command=dlg.destroy
        ).pack(side="left", padx=8)

