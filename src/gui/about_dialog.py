"""Finestra About — VSTDeckManager."""
import customtkinter as ctk
from src.core.config import VERSION, YEAR
from src.gui.widgets import center_over_parent

_YELLOW = "#c8a838"
_VERSION = VERSION
_YEAR = YEAR


class AboutDialog(ctk.CTkToplevel):

    def __init__(self, parent):
        super().__init__(parent)
        self.title("About — VSTDeckManager")
        self.resizable(False, False)
        center_over_parent(self, parent, 380, 300)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)

        # Logo / titolo
        ctk.CTkLabel(
            self,
            text="🎛  VSTDeckManager",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=_YELLOW,
        ).grid(row=0, column=0, pady=(32, 4))

        ctk.CTkLabel(
            self,
            text=f"version  {_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        ).grid(row=1, column=0, pady=(0, 20))

        ctk.CTkFrame(self, height=1, fg_color="#2a2a3a").grid(
            row=2, column=0, sticky="ew", padx=40, pady=(0, 20)
        )

        ctk.CTkLabel(
            self,
            text="VST plugin management, macros and Stream Deck \nfor Fender Studio Pro",
            font=ctk.CTkFont(size=12),
            text_color="#aaaaaa",
            justify="center",
        ).grid(row=3, column=0, pady=(0, 6))

        ctk.CTkLabel(
            self,
            text=f"© {_YEAR} Marcalfa • MIT License",
            font=ctk.CTkFont(size=11),
            text_color="#666677",
        ).grid(row=4, column=0, pady=(0, 24))

        ctk.CTkButton(
            self,
            text="Close",
            width=100, height=32,
            fg_color="#2a2a3a", hover_color="#3a3a4a",
            command=self.destroy,
        ).grid(row=5, column=0, pady=(0, 24))

        self.attributes("-topmost", True)
        self.after(200, lambda: self.attributes("-topmost", False))
