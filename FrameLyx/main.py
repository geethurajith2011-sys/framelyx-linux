#!/usr/bin/env python3
"""
Frame Lyx — application entry point.

Join Image Frames · Create Videos.
Run with:  python main.py
"""

import os
import sys

# Make package imports work when launching from any directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from core.project_manager import app_settings
from ui import theme
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Frame Lyx")
    app.setOrganizationName("FrameLyx")
    app.setDesktopFileName("FrameLyx")

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "icons", "framelyx.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Professional typography with graceful fallbacks per platform.
    for family in ("Segoe UI", "Ubuntu", "Cantarell", "Inter", "DejaVu Sans"):
        font = QFont(family, 10)
        if font.exactMatch() or family == "DejaVu Sans":
            app.setFont(font)
            break

    theme.apply_theme(app, app_settings().value("theme", "dark"))

    window = MainWindow()

    # Crash recovery: offer to restore an autosaved (unsaved) project.
    autosave = window.autosave
    if autosave.has_recovery():
        from PySide6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            None, "Crash Recovery",
            "An autosaved project from a previous session was found.\n\n"
            "Restore it?")
        if answer == QMessageBox.Yes:
            project = autosave.load_recovery()
            if project:
                window._set_project(project)
                window.show_welcome(False)
        autosave.clear()

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
