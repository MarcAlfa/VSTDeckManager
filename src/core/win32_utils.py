"""Utilità Win32 per gestione finestre multi-monitor (save/restore posizione)."""
import json
import ctypes
import ctypes.wintypes
from pathlib import Path
from src.core.config import _CONFIG_FILE

# ------------------------------------------------------------------ structs

class _RECT(ctypes.Structure):
    _fields_ = [("left",  ctypes.c_long), ("top",    ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize",    ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork",    _RECT),          ("dwFlags",   ctypes.c_ulong)]

_MonitorEnumProc = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
    ctypes.POINTER(_RECT), ctypes.c_double,
)

_GA_ROOT                  = 2
_SWP_NOSIZE               = 0x0001
_SWP_NOZORDER             = 0x0004
_MONITOR_DEFAULTTONEAREST = 2

# ------------------------------------------------------------------ helpers

def get_monitors() -> list[dict]:
    monitors: list[dict] = []

    def _cb(hmon, hdc, lprect, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        monitors.append({
            "left": r.left, "top": r.top,
            "right": r.right, "bottom": r.bottom,
            "width": r.right - r.left, "height": r.bottom - r.top,
            "primary": bool(mi.dwFlags & 1),
        })
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(_cb), 0)
    return monitors


def get_hwnd(widget) -> int:
    """HWND Win32 della finestra root (bypassa child handles di tkinter)."""
    hwnd = widget.winfo_id()
    root = ctypes.windll.user32.GetAncestor(hwnd, _GA_ROOT)
    return root or hwnd

# ------------------------------------------------------------------ save / restore

def save_window_state(hwnd: int, config_key: str) -> None:
    """
    Salva monitor + posizione relativa sotto app[config_key] in config.json.
    Usa MonitorFromWindow + GetWindowRect (coordinate fisiche Win32).
    """
    try:
        hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))

        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))

        ml, mt = mi.rcMonitor.left, mi.rcMonitor.top
        state = {
            "monitor": {
                "left":    ml,
                "top":     mt,
                "width":   mi.rcMonitor.right - ml,
                "height":  mi.rcMonitor.bottom - mt,
                "primary": bool(mi.dwFlags & 1),
            },
            "rel_x": rect.left - ml,
            "rel_y": rect.top  - mt,
            "w":     rect.right  - rect.left,
            "h":     rect.bottom - rect.top,
        }

        with open(_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("app", {})[config_key] = state
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception:
        pass


def restore_window_position(hwnd: int, config_key: str) -> None:
    """
    Ripristina la finestra sul monitor corretto usando SetWindowPos.
    Legge da app[config_key] in config.json.
    """
    try:
        with open(_CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        ws = data.get("app", {}).get(config_key)
        if not ws:
            return

        saved_mon = ws["monitor"]
        monitors  = get_monitors()

        target = next(
            (m for m in monitors
             if m["left"]  == saved_mon["left"]  and
                m["top"]   == saved_mon["top"]   and
                m["width"] == saved_mon["width"] and
                m["height"]== saved_mon["height"]),
            next((m for m in monitors if m["primary"]), monitors[0]),
        )

        abs_x = target["left"] + ws["rel_x"]
        abs_y = target["top"]  + ws["rel_y"]
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, abs_x, abs_y, 0, 0,
            _SWP_NOSIZE | _SWP_NOZORDER,
        )

    except Exception:
        pass
