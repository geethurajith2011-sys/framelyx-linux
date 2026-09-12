"""
Frame Lyx — ui.render_dialog

Non-blocking render progress window: real progress bar, frames processed,
current frame name, ETA and cancellation.  The dialog is modal but all
work happens on the worker thread, so the UI never freezes.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QVBoxLayout)


def fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} seconds"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''} {s} seconds"
    h, m = divmod(m, 60)
    return f"{h} hour{'s' if h != 1 else ''} {m} minutes"


class RenderProgressDialog(QDialog):
    cancelRequested = Signal()

    def __init__(self, project_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rendering Video \u2014 Frame Lyx")
        self.setMinimumWidth(520)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel(f"Rendering Video\u2026  ({project_name})")
        self.title.setProperty("cls", "h2")
        root.addWidget(self.title)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        root.addWidget(self.bar)

        self.percent = QLabel("0%")
        self.percent.setProperty("cls", "h2")
        self.percent.setAlignment(Qt.AlignCenter)
        root.addWidget(self.percent)

        self.stats = QLabel("Frames Processed: 0 / 0")
        root.addWidget(self.stats)

        self.current = QLabel("Current Frame: \u2014")
        self.current.setProperty("cls", "muted")
        root.addWidget(self.current)

        self.eta = QLabel("Estimated Time Remaining: \u2014")
        self.eta.setProperty("cls", "muted")
        root.addWidget(self.eta)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("cls", "danger")
        row.addWidget(self.cancel_btn)
        root.addLayout(row)

        self.cancel_btn.clicked.connect(self.cancelRequested)

    def on_progress(self, processed: int, total: int, current: str, eta: float):
        pct = int(processed * 100 / total) if total else 0
        self.bar.setValue(pct)
        self.percent.setText(f"{pct}%")
        self.stats.setText(f"Frames Processed: {processed:,} / {total:,}")
        self.current.setText(f"Current Frame: {current}")
        self.eta.setText(f"Estimated Time Remaining: {fmt_eta(eta)}")

    def closeEvent(self, event):
        # Closing via the X must also cancel the render.
        self.cancelRequested.emit()
        super().closeEvent(event)
