"""
Frame Lyx — ui.export_panel

Professional export panel: live output summary, output location/filename,
aspect-ratio handling, estimated file size, render history and the big
CREATE VIDEO button.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPushButton, QVBoxLayout, QWidget)

from core.project_manager import Project
from core.video_renderer import (CODEC_LABELS, FIT_LABELS, QUALITY_LABELS,
                                 RESOLUTION_LABELS, RESOLUTION_PRESETS,
                                 estimate_output_size)


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} GB"


class ExportPanel(QWidget):
    """Export settings + summary + the CREATE VIDEO button."""

    settingsChanged = Signal()
    renderRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ---- summary card ---------------------------------------------
        summary_frame_layout = QVBoxLayout()
        summary_frame_layout.setContentsMargins(16, 12, 16, 12)
        title = QLabel("EXPORT SUMMARY")
        title.setProperty("cls", "panelTitle")
        summary_frame_layout.addWidget(title)
        self.summary = QLabel("No project loaded.")
        self.summary.setProperty("cls", "muted")
        self.summary.setTextFormat(Qt.RichText)
        summary_frame_layout.addWidget(self.summary)

        from PySide6.QtWidgets import QFrame
        card = QFrame()
        card.setProperty("cls", "panel")
        card.setLayout(summary_frame_layout)
        root.addWidget(card)

        # ---- output settings --------------------------------------------
        form_card_l = QFormLayout()
        form_card_l.setLabelAlignment(Qt.AlignRight)
        form_card_l.setSpacing(8)

        self.codec_combo = QComboBox()
        self.codec_combo.addItems(list(CODEC_LABELS.values()))

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(list(QUALITY_LABELS.values()))

        self.res_combo = QComboBox()
        self.res_combo.addItems(list(RESOLUTION_LABELS.values()))

        self.custom_w = QLineEdit()
        self.custom_w.setPlaceholderText("1920")
        self.custom_w.setMaximumWidth(90)
        self.custom_h = QLineEdit()
        self.custom_h.setPlaceholderText("1080")
        self.custom_h.setMaximumWidth(90)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom_w)
        custom_row.addWidget(QLabel("\u00d7"))
        custom_row.addWidget(self.custom_h)
        custom_row.addStretch(1)
        self.custom_widget = QWidget()
        self.custom_widget.setLayout(custom_row)

        self.fit_combo = QComboBox()
        self.fit_combo.addItems(list(FIT_LABELS.values()))

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Untitled_Project.mp4")

        choose_btn = QPushButton("Choose Output Folder\u2026")
        self.folder_label = QLabel("(same folder as frames)")
        self.folder_label.setProperty("cls", "muted")

        self.open_after = QCheckBox("Open output folder after rendering")
        self.open_after.setChecked(True)

        form_card_l.addRow("Video Format:", QLabel("MP4"))
        form_card_l.addRow("Codec:", self.codec_combo)
        form_card_l.addRow("Quality:", self.quality_combo)
        form_card_l.addRow("Resolution:", self.res_combo)
        form_card_l.addRow("", self.custom_widget)
        form_card_l.addRow("Aspect Ratio:", self.fit_combo)
        form_card_l.addRow("Filename:", self.filename_edit)
        folder_row = QHBoxLayout()
        folder_row.addWidget(choose_btn)
        folder_row.addWidget(self.folder_label, 1)
        form_card_l.addRow("Location:", folder_row)
        form_card_l.addRow("", self.open_after)

        card2 = QFrame()
        card2.setProperty("cls", "panel")
        inner = QVBoxLayout(card2)
        inner.setContentsMargins(16, 12, 16, 12)
        t2 = QLabel("OUTPUT SETTINGS")
        t2.setProperty("cls", "panelTitle")
        inner.addWidget(t2)
        inner.addLayout(form_card_l)
        root.addWidget(card2)

        # ---- render history ----------------------------------------------
        hist_title = QLabel("RENDER HISTORY")
        hist_title.setProperty("cls", "panelTitle")
        root.addWidget(hist_title)
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(110)
        root.addWidget(self.history_list)

        # ---- CREATE VIDEO ---------------------------------------------------
        self.forge_btn = QPushButton("\u25b6  CREATE VIDEO")
        self.forge_btn.setProperty("cls", "primary")
        self.forge_btn.setMinimumHeight(58)
        self.forge_btn.setCursor(Qt.PointingHandCursor)
        font = self.forge_btn.font()
        font.setPointSize(16)
        font.setBold(True)
        self.forge_btn.setFont(font)
        root.addWidget(self.forge_btn)
        root.addStretch(1)

        # wiring
        choose_btn.clicked.connect(self._choose_folder)
        self.forge_btn.clicked.connect(self.renderRequested)
        for w in (self.codec_combo, self.quality_combo, self.res_combo,
                  self.fit_combo):
            w.currentIndexChanged.connect(self._on_setting)
        self.custom_w.editingFinished.connect(self._on_custom_res)
        self.custom_h.editingFinished.connect(self._on_custom_res)
        self.filename_edit.editingFinished.connect(self._on_filename)
        self.open_after.toggled.connect(self._on_open_after)
        self.res_combo.currentIndexChanged.connect(self._toggle_custom)
        self._toggle_custom()

    # -- state sync ------------------------------------------------------------
    def load_from_project(self, project: Project):
        self.codec_combo.setCurrentIndex(
            list(CODEC_LABELS).index(project.codec))
        self.quality_combo.setCurrentIndex(
            list(QUALITY_LABELS).index(project.quality))
        self.res_combo.setCurrentIndex(
            list(RESOLUTION_LABELS).index(project.resolution_mode))
        self.fit_combo.setCurrentIndex(list(FIT_LABELS).index(project.fit_mode))
        self.custom_w.setText(str(project.custom_width))
        self.custom_h.setText(str(project.custom_height))
        self.filename_edit.setText(project.output_filename)
        self.open_after.setChecked(project.open_output_folder)
        self.folder_label.setText(project.output_directory
                                  or "(same folder as frames)")
        self._toggle_custom()

    def apply_to_project(self, project: Project):
        project.codec = list(CODEC_LABELS)[self.codec_combo.currentIndex()]
        project.quality = list(QUALITY_LABELS)[self.quality_combo.currentIndex()]
        project.resolution_mode = list(RESOLUTION_LABELS)[self.res_combo.currentIndex()]
        project.fit_mode = list(FIT_LABELS)[self.fit_combo.currentIndex()]
        project.open_output_folder = self.open_after.isChecked()

    def update_summary(self, project: Project, frame_count: int,
                       src_res, fps: float):
        if project is None or frame_count <= 0:
            self.summary.setText("No project loaded.")
            self.forge_btn.setEnabled(False)
            return
        self.forge_btn.setEnabled(True)
        w, h = src_res
        spec_like_w, spec_like_h = self._target_res(w, h)
        size = estimate_output_size(self._fake_spec(fps), frame_count, w, h)
        duration = frame_count / fps if fps else 0
        self.summary.setText(
            f"<b>Format:</b> MP4 &nbsp;&nbsp; <b>Codec:</b> "
            f"{CODEC_LABELS[self._codec()]}<br>"
            f"<b>Resolution:</b> {spec_like_w} \u00d7 {spec_like_h} &nbsp;&nbsp; "
            f"<b>Frame Rate:</b> {fps:g} FPS<br>"
            f"<b>Frames:</b> {frame_count:,} &nbsp;&nbsp; "
            f"<b>Estimated Duration:</b> {duration:,.1f} s<br>"
            f"<b>Estimated File Size:</b> ~ {fmt_bytes(size)}")

    def add_history(self, text: str):
        self.history_list.insertItem(0, text)
        if self.history_list.count() > 20:
            self.history_list.takeItem(self.history_list.count() - 1)

    # -- helpers ----------------------------------------------------------------
    def _codec(self):
        return list(CODEC_LABELS)[self.codec_combo.currentIndex()]

    def _fake_spec(self, fps):
        from core.video_renderer import RenderSpec
        return RenderSpec(fps=fps, codec=self._codec(),
                          quality=list(QUALITY_LABELS)[self.quality_combo.currentIndex()],
                          resolution_mode=list(RESOLUTION_LABELS)[self.res_combo.currentIndex()],
                          custom_width=self._int_or(self.custom_w.text(), 1920),
                          custom_height=self._int_or(self.custom_h.text(), 1080))

    def _target_res(self, w, h):
        mode = list(RESOLUTION_LABELS)[self.res_combo.currentIndex()]
        if mode == "original":
            return w, h
        if mode == "custom":
            return self._int_or(self.custom_w.text(), 1920), self._int_or(self.custom_h.text(), 1080)
        return RESOLUTION_PRESETS[mode]

    @staticmethod
    def _int_or(text, default):
        try:
            return max(16, int(text))
        except (TypeError, ValueError):
            return default

    def _toggle_custom(self):
        self.custom_widget.setVisible(
            list(RESOLUTION_LABELS)[self.res_combo.currentIndex()] == "custom")

    def _on_setting(self, _=0):
        self.settingsChanged.emit()

    def _on_custom_res(self):
        self.settingsChanged.emit()

    def _on_filename(self):
        self.settingsChanged.emit()

    def _on_open_after(self, _checked):
        self.settingsChanged.emit()

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Output Folder",
            self.folder_label.text() if os.path.isdir(self.folder_label.text())
            else os.path.expanduser("~"))
        if folder:
            self.folder_label.setText(folder)
            self.settingsChanged.emit()

    def current_output_directory(self) -> str:
        text = self.folder_label.text()
        return text if os.path.isdir(text) else ""
