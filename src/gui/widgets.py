"""Widget/helper GUI condivisi tra le finestre."""
import tkinter as tk


def tooltip(widget, text: str):
    """Mostra un piccolo popup sopra il widget al passaggio del mouse."""
    tip: list = [None]

    def show(e):
        if tip[0]:
            return
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tk.Label(
            tw, text=text,
            bg="#23233a", fg="#cccccc",
            font=("Segoe UI", 10),
            padx=10, pady=4,
            relief="flat", bd=0,
        ).pack()
        tw.update_idletasks()
        x = widget.winfo_rootx() + widget.winfo_width() // 2 - tw.winfo_width() // 2
        y = widget.winfo_rooty() - tw.winfo_height() - 6
        tw.geometry(f"+{x}+{y}")
        tip[0] = tw

    def hide(e):
        if tip[0]:
            tip[0].destroy()
            tip[0] = None

    widget.bind("<Enter>", show, add="+")
    widget.bind("<Leave>", hide, add="+")


def center_over_parent(dialog, parent, width: int, height: int):
    """Posiziona una finestra toplevel centrata rispetto al parent sullo stesso monitor."""
    try:
        parent.update_idletasks()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        x = px + max(0, (pw - width) // 2)
        y = py + max(0, (ph - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        dialog.geometry(f"{width}x{height}")
