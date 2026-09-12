"""
Frame Lyx — ui.settings_dialog

Application settings: FFmpeg path (auto-detect, browse, live validation)
and UI theme.  Persisted through QSettings so they survive restarts.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from core.project_manager import app_settings
from core.video_renderer import detect_ffmpeg


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings \u2014 Frame Lyx")
        self.setMinimumWidth(560)
        self._settings = app_settings()

        root = QVBoxLayout(self)
        root.setSpacing(12)

        root.addWidget(QLabel("FFMPEG"))
        row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit(
            self._settings.value("ffmpeg_path", "") or detect_ffmpeg() or "")
        self.ffmpeg_edit.setPlaceholderText("Automatically detected path")
        browse = QPushButton("Browse\u2026")
        detect = QPushButton("Automatically Detect FFmpeg")
        row.addWidget(self.ffmpeg_edit, 1)
        row.addWidget(detect)
        row.addWidget(browse)
        root.addLayout(row)

        self.ffmpeg_status = QLabel()
        root.addWidget(self.ffmpeg_status)
        self.ffmpeg_edit.textChanged.connect(self._check_ffmpeg)
        detect.clicked.connect(self._auto_detect)
        browse.clicked.connect(self._browse)
        self._check_ffmpeg()

        root.addWidget(QLabel("APPEARANCE"))
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Theme", "Light Theme"])
        self.theme_combo.setCurrentIndex(
            0 if self._settings.value("theme", "dark") == "dark" else 1)
        theme_row.addWidget(self.theme_combo, 1)
        root.addLayout(theme_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _check_ffmpeg(self):
        path = self.ffmpeg_edit.text().strip()
        if not path:
            self.ffmpeg_status.setText("")
            return
        if os.path.isfile(path):
            self.ffmpeg_status.setText(
                "\u2713 FFmpeg found.")
            self.ffmpeg_status.setStyleSheet("color: #2fd48f;")
        else:
            self.ffmpeg_status.setText(
                "\u2717 File not found \u2014 rendering will fail until fixed.")
            self.ffmpeg_status.setStyleSheet("color: #f0566a;")

    def _auto_detect(self):
        path = detect_ffmpeg()
        if path:
            self.ffmpeg_edit.setText(path)
        else:
            self.ffmpeg_status.setText(
                "\u2717 FFmpeg was not found. Please install FFmpeg and "
                "configure it in Settings.")
            self.ffmpeg_status.setStyleSheet("color: #f0566a;")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FFmpeg Executable",
            os.path.dirname(self.ffmpeg_edit.text()) or os.path.expanduser("~"))
        if path:
            self.ffmpeg_edit.setText(path)

    def accept(self):
        self._settings.setValue("ffmpeg_path", self.ffmpeg_edit.text().strip())
        self._settings.setValue(
            "theme", "dark" if self.theme_combo.currentIndex() == 0 else "light")
        super().accept()

    @staticmethod
    def ffmpeg_path() -> str:
        settings = app_settings()
        return settings.value("ffmpeg_path", "") or detect_ffmpeg() or ""

    @staticmethod
    def current_theme() -> str:
        return app_settings().value("theme", "dark")
