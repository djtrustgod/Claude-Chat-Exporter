"""Entry point for the Claude Chat Exporter desktop app."""

from __future__ import annotations

import sys

import customtkinter as ctk

from src.gui.main_window import MainWindow


def main() -> int:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = MainWindow()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
