# 🎛 VSTDeckManager

A Windows desktop tool for **Fender Studio Pro / Studio One** that combines a full VST plugin library browser
with macro and Stream Deck management.

The library reads your plugins, organises them by **your own FSP categories** (not generic VST3 sub-types),
shows plugin images from **your own Snapshots folder**, and lets you manage favourites, hidden plugins and notes.
A separate editor automates the full pipeline for adding a plugin to your workflow:
one click creates the macro, assigns the keyboard shortcut, and places the button on the **Stream Deck** — all at once.

---

## ✅ Main Features

### VST Library (main window)
- **Plugin catalog browser** — all installed VST3/Native plugins in a card grid with image thumbnails
- **FSP user categories** — categories come from `PluginPresentation.settings` (`sortPath` field), which reflects
  the custom categorisation the user has set inside FSP — not the generic VST3 sub-type strings
- **Plugin images** — loaded from the folder configured in `fsp.snapshots_dir` (e.g. `D:\StudioOne\Snapshots\`);
  each vendor sub-folder contains a `snapshots.json` that maps plugin GUID → image file; three resolutions are
  supported (`.png` thumbnail, `@2x.png` medium, `.original.png` full-res for the detail view)
- **Favourites / Hidden / Notes** — per-plugin, stored in `cache/` by GUID; survive app restarts
- **Detail view** — click any card to expand it: full-res image, metadata, favourite/hide buttons, freetext notes
- **Sidebar with collapsible groups** — Effects and Instruments, each listing the user's real FSP categories in
  alphabetical order; Favourites and Hidden have their own dedicated views
- **Settings dialog** — edit all config.json paths directly from the UI (🛠 button)

### Macro Editor (secondary window, ⚙ button)
- **Macro scanner** — reads all existing macros whose name starts with `macro_prefix` (e.g. `SdR_`), both
  *effect* macros (`Add Insert` + plugin GUID) and *instrument* macros (`Load Track Preset`),
  with live shortcut lookup from `user.keyscheme`
- **Fully dynamic** — categories, slot counts, and page structure are read live from the SD profile; nothing is hardcoded
- **Smart category suggestion** — auto-suggests the right SD category based on the plugin sub-type
- **MAKE FILES pipeline** — one-click end-to-end automation with preview, validation, and automatic timestamped backups before writing macro, keyscheme, and Stream Deck button files

### Stream Deck Map (popup window, 🎛 button on main window)
- **Interactive Drag & Drop** — drag any plugin card directly from the VST Library onto an empty slot in the Stream Deck Map to instantly create the FSP macro, bind a keyboard shortcut, and generate the tailored button icon in one step.
- **Navigable visual map** — live visual map of your SD profile (4×2 grid per page, folder navigation, encoder row)
- **Square cards & plugin thumbnails** — proportional square cards displaying the plugin title and crisp snapshot image below it, with interactive folder/back navigation and detailed tooltips
- **Folder plugin counts & capacity** — folder cards dynamically display connected plugin count and capacity pills (e.g. `4 plugin collegati (4/7)` or `7/7` capacity warning), with deep recursive counting and internal header indicators
- **Quick unmap (`-` button)** — quick delete button in the bottom-left of each mapped plugin card with confirmation dialog; safely frees the SD slot, removes the shortcut in `user.keyscheme`, and deletes the `.studioonemacro` file (with automatic backups)


### General
- **Multi-monitor aware** — all three windows (Library, Macro Editor, Stream Deck Map) remember their position per monitor across sessions
- Dark UI with yellow accent, non-resizable, compact layout

---

## 🧱 Tech Stack

| Layer             | Technology                    |
|-------------------|-------------------------------|
| Language          | Python 3.13                   |
| UI                | CustomTkinter                 |
| Image handling    | Pillow                        |
| Win32 integration | ctypes (multi-monitor, HWND)  |
| Config            | JSON                          |

---

## 📂 Project Structure

```
VSTDeckManager/
│
├── vstdeckman.py              # entry point
├── config.json                # paths, profile UUID, window states (edit to match your setup)
├── requirements.txt           # dependencies
│
├── src/
│   ├── models.py              # dataclasses: Plugin, Macro, Assignment
│   ├── core/
│   │   ├── config.py          # loads config.json once at import, exposes paths + MACRO_PREFIX/MACRO_GROUP
│   │   ├── backup.py          # auto-backup with timestamp (ready, used by the upcoming writers)
│   │   └── win32_utils.py     # multi-monitor save/restore (Win32 API)
│   ├── parsers/                    # read-only
│   │   ├── plugins_catalog.py      # reads Plugins-en.settings (with JSON cache)
│   │   ├── plugin_presentation.py  # reads PluginPresentation.settings → {GUID: sortPath}
│   │   ├── macro_scanner.py        # reads {macro_prefix}*.studioonemacro files (effect + instrument)
│   │   └── deck_profile.py         # reads SD manifest.json files (no cache)
│   ├── writers/
│   │   ├── macro_writer.py         # writes .studioonemacro (XML + UTF-8 BOM + CRLF + tabs)
│   │   ├── keyscheme_writer.py     # injects macro shortcut into user.keyscheme (base64)
│   │   └── deck_writer.py          # adds hotkey action into SD manifest.json (hardware codes)
│   └── gui/
│       ├── app.py                  # main window (Library)
│       ├── macro_editor.py         # Macro Editor window (Toplevel, ⚙ button)
│       ├── panel_library.py        # VST library: card grid, sidebar, detail view
│       ├── snapshots_loader.py     # maps GUID → image path from fsp.snapshots_dir
│       ├── panel_current.py        # macro editor — left panel: existing macros list
│       ├── panel_add.py            # macro editor — right panel: plugin search + add form
│       ├── window_deck.py          # Stream Deck Map popup (🎛 button)
│       ├── settings_dialog.py      # Settings dialog (edits config.json from UI)
│       ├── about_dialog.py         # About dialog
│       └── widgets.py              # shared GUI helpers (tooltip)
│
├── backups/                   # auto-generated backups
└── cache/                     # plugin catalog cache + favorites/hidden/notes JSON
```

---

## 🔧 Setup (Development)

```powershell
# Create virtual environment
python -m venv .venv

# Activate it (PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run
python vstdeckman.py
```

---

## ⚙️ Configuration

Edit `config.json` to match your system before running:

```json
{
  "fsp": {
    "config_root":         "C:\\Users\\YOU\\AppData\\Roaming\\Fender\\Studio Pro 8",
    "macros_dir":          "C:\\Users\\YOU\\Documents\\Studio One\\Macros",
    "plugins_catalog":     "C:\\Users\\YOU\\AppData\\Roaming\\Fender\\Studio Pro 8\\x64\\Plugins-en.settings",
    "plugin_presentation": "C:\\Users\\YOU\\AppData\\Roaming\\Fender\\Studio Pro 8\\PluginPresentation.settings",
    "keyscheme":           "C:\\Users\\YOU\\AppData\\Roaming\\Fender\\Studio Pro 8\\user.keyscheme",
    "snapshots_dir":       "D:\\StudioOne\\Snapshots",
    "macro_group":         "YourPrefix",
    "macro_prefix":        "YourPrefix_"
  },
  "streamdeck": {
    "profiles_root":           "C:\\Users\\YOU\\AppData\\Roaming\\Elgato\\StreamDeck\\ProfilesV3",
    "studio_one_profile_uuid": "YOUR-PROFILE-UUID-HERE"
  }
}
```

> **`plugin_presentation`** — `PluginPresentation.settings` is the FSP file that stores the user's own plugin
> category assignments (the ones you see in the FSP browser when you drag plugins into custom folders).
> The app reads the `sortPath` attribute of each `<PlugInInfo>` element to derive the category shown in the sidebar.
> This means the Library sidebar mirrors exactly your personal FSP organisation — not generic VST3 sub-types.

> **`snapshots_dir`** — FSP saves plugin screenshots in this folder, organised as
> `{snapshots_dir}\{VendorName}\{PluginName}.png` (and `@2x` / `.original` variants).
> Each vendor sub-folder also contains a `snapshots.json` that maps plugin GUID → image filename.
> The app reads this structure to display thumbnails in the card grid and full-res images in the detail view.
> Only third-party plugins get snapshots; native FSP/PreSonus plugins do not have images available.

> **`macro_group` / `macro_prefix`** — the app only reads and manages macros that start with this prefix.
> You can use any prefix you like (e.g. `"MyFX_"`), as long as it's consistent.
> Without a prefix the scanner would pick up every single macro in your library.

> **Profile UUID** — the folder name inside `ProfilesV3\` that matches your Studio One Stream Deck profile.
> You can find it by opening `%APPDATA%\Elgato\StreamDeck\ProfilesV3\` and looking for the folder
> whose `manifest.json` contains `"Name": "Studio One"` (or whatever you named your profile).

> **Stream Deck folder names** — each category folder on the main page of your SD profile must have a **unique name**.
> If you need multiple folders for the same type (e.g. two Synth pages), append a suffix: `Synth A`, `Synth B`, etc.
> Duplicate names will cause the app to read the wrong slot counts.

---

## 💾 Runtime Data

| Path | Description |
|---|---|
| `config.json` | Paths, profile UUID, window states (auto-updated on close) |
| `cache/plugins_catalog.json` | Plugin catalog cache — rebuilt on demand with ↻ Refresh |
| `cache/favorites.json` | Favourite plugin GUIDs |
| `cache/hidden.json` | Hidden plugin GUIDs |
| `cache/notes.json` | Per-plugin freetext notes (keyed by GUID) |
| `backups/` | Timestamped backups before any write operation |

---

## 🗺️ Roadmap

### 🔜 Next
- **`[Mapped]` filter & badge in VST Library**: visual red accent/border on cards for plugins that already have an active FSP macro + SD button assignment, plus dedicated `🎛 Mapped` sidebar section.
- **Direct Map & Unmap actions**:
  - `[+ Map to Stream Deck]` button on cards / detail view, launching Macro Editor with the plugin pre-selected and free shortcut ready.
  - `[✕ Unmap]` one-click safe deletion directly from plugin detail view.
- **Controller location info**: display Stream Deck category, physical slot (`Slot X,Y`), and shortcut inside plugin detail view and card tooltip.
- **Export filters**: export only Mapped plugins, only Favorites, or the currently active view.
- Create new SD sub-pages directly from the app (currently done by hand in the Stream Deck app).
- Detect whether FSP / Stream Deck are running and warn to restart them after writing.
- **Support for other Stream Deck hardware (15-key Standard, 32-key XL, Mini)**: the app is currently tailored and tested exclusively on the 8-key Stream Deck Plus (4×2 grid); study manifest structures and slot layouts to support and verify different hardware models.



---

## 📌 Status

> **v0.9.2** — Pre-release public readiness: MIT license alignment, About dialog updates, streamlined configuration templates, and comprehensive hardware compatibility documentation for Stream Deck models.

> **v0.9.1** — Interactive Drag & Drop from VST Library directly onto Stream Deck Map empty slots (with live hover highlight, auto-lift, and one-click mapping pipeline), full English UI localization, multi-monitor dialog centering, expanded 154-candidate shortcut pool, and symbol hotkey parsing fixes (`++`).

> **v0.8** — Live folder plugin counts & capacity in Stream Deck Map, tooltips on library card actions (favorite/hide/restore), new 🛠 settings icon, and mapped plugin detection.

> **v0.79** — `[Mapped]` badge on VST library cards, dedicated `🎛 Mapped` sidebar section, and Stream Deck assignment info in detail view.

> **v0.78** — Stream Deck Map moved to main window, redesigned with square cards & plugin snapshot thumbnails, and quick unmap (`-`) button.

> **v0.77** — automatic Stream Deck snapshot icons & end-to-end assignment management.

The full pipeline for macro creation, keyboard shortcut assignment, and Stream Deck hotkey button integration
is operative via **MAKE FILES**. Plugin snapshot images from Studio One (`Snapshots/`) are automatically converted,
resized, and centered onto 288×288 transparent RGBA canvases and registered directly in the Stream Deck profile (`Images/`).
Stream Deck buttons are filled according to natural reading order (row by row: `1,0` → `2,0` → `3,0` → `0,1` → `1,1` → `2,1` → `3,1`),
with full Shift modifier resolution for symbol shortcuts.
Existing assignments can be deleted with a single click (🗑️ / ✕) directly from the Macro Editor, safely removing the
`.studioonemacro` file, freeing the keyboard shortcut in `user.keyscheme`, and clearing the Stream Deck button and its
associated icon image, all safeguarded by automatic timestamped backups.


## 🎮 Hardware Compatibility

- **Developed and Tested on**: **Elgato Stream Deck +** (4×2 keypad layout with 8 LCD keys + 4 rotary encoders / touch strip).
- **Other Stream Deck Models (Standard 15-key, XL 32-key, Mini 6-key, Neo)**:
  - **Not officially tested yet.**
  - Currently, the UI and writer logic are tuned to a 4×2 grid (8 keys). If loaded with a profile from a device with no knobs, the encoder strip is automatically omitted without issues. On models with more than 8 keys (15 or 32 keys), only the first 4×2 slot area is currently rendered and populated.
  - **Contributions & Feedback**: Testers, issues, and PRs from users with other Stream Deck models are very welcome!

---

## 📜 License

This project is licensed under the [MIT License](LICENSE) - see the [LICENSE](LICENSE) file for details.

---

## 🧑‍💻 Author
**marcalfa**
📆 Started: January 2026
🌍 Location: Earth

