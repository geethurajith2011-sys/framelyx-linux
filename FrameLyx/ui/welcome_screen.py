"""
Frame Lyx — ui.welcome_screen

Welcome screen shown when no project is open: branding,
primary actions and a drag-and-drop target for frame folders.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QVBoxLayout, QWidget)

from core.frame_manager import MAX_FRAMES


class DropArea(QFrame):
    """Drag & drop target accepting frame folders or loose image files."""
    folderDropped = Signal(str)
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cls", "panel")
        self.setMinimumHeight(120)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        icon = QLabel("\u25a3")
        icon.setStyleSheet("font-size: 34px; border: none; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)
        text = QLabel("Drop Your Frame Folder Here")
        text.setProperty("cls", "h2")
        text.setAlignment(Qt.AlignCenter)
        sub = QLabel(f"PNG \u00b7 JPG \u00b7 JPEG \u00b7 WEBP \u00b7 BMP  \u2014  "
                     f"up to {MAX_FRAMES:,} frames per project")
        sub.setProperty("cls", "muted")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(text)
        lay.addWidget(sub)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("border: 2px dashed #29d3ff; border-radius: 10px;")

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")

    def dropEvent(self, event):
        self.setStyleSheet("")
        folders, files = [], []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                folders.append(path)
            elif path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                files.append(path)
        if folders:
            self.folderDropped.emit(folders[0])
        elif files:
            self.filesDropped.emit(files)


class WelcomeScreen(QWidget):
    """Branding + actions + recents + drop area."""
    createRequested = Signal()
    openRequested = Signal()
    openPathRequested = Signal(str)
    folderDropped = Signal(str)
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setSpacing(14)

        root.addStretch(2)
        mark_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 os.pardir, "assets", "icons",
                                 "framelyx_mark.png")
        if os.path.isfile(mark_path):
            mark = QLabel()
            mark.setPixmap(QPixmap(mark_path).scaled(
                150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            mark.setAlignment(Qt.AlignCenter)
            mark.setStyleSheet("border: none;")
            root.addWidget(mark, 0, Qt.AlignHCenter)
        brand_row = QHBoxLayout()
        brand_row.setAlignment(Qt.AlignCenter)
        brand_row.setSpacing(12)
        logo1 = QLabel("Frame")
        logo1.setProperty("cls", "h1")
        logo1.setStyleSheet("font-size: 46px; font-weight: 800; "
                            "letter-spacing: 4px; border: none;")
        logo2 = QLabel("Lyx")
        logo2.setProperty("cls", "accent")
        logo2.setStyleSheet("font-size: 46px; font-weight: 800; "
                            "letter-spacing: 4px; border: none;")
        brand_row.addWidget(logo1)
        brand_row.addWidget(logo2)
        root.addLayout(brand_row)
        tagline = QLabel("Join Image Frames \u00b7 Create Videos")
        tagline.setProperty("cls", "accent")
        tagline.setStyleSheet("font-size: 17px; font-weight: 600; border: none;")
        tagline.setAlignment(Qt.AlignCenter)
        sub = QLabel("Professional Frame Sequence to Video Studio")
        sub.setProperty("cls", "muted")
        sub.setAlignment(Qt.AlignCenter)
        root.addWidget(tagline)
        root.addWidget(sub)
        root.addSpacing(16)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.setSpacing(14)
        create_btn = QPushButton("+  Create New Project")
        create_btn.setProperty("cls", "primary")
        create_btn.setMinimumHeight(46)
        create_btn.setMinimumWidth(230)
        open_btn = QPushButton("Open Existing Project")
        open_btn.setMinimumHeight(46)
        open_btn.setMinimumWidth(230)
        btn_row.addWidget(create_btn)
        btn_row.addWidget(open_btn)
        root.addLayout(btn_row)

        root.addSpacing(14)
        drop = DropArea()
        drop.setFixedWidth(520)
        drop.folderDropped.connect(self.folderDropped)
        drop.filesDropped.connect(self.filesDropped)
        wrap = QHBoxLayout()
        wrap.setAlignment(Qt.AlignCenter)
        wrap.addWidget(drop)
        root.addLayout(wrap)

        self.recents_title = QLabel("RECENT PROJECTS")
        self.recents_title.setProperty("cls", "panelTitle")
        self.recents_title.setAlignment(Qt.AlignCenter)
        self.recents = QListWidget()
        self.recents.setFixedWidth(520)
        self.recents.setMaximumHeight(120)
        self.recents.itemDoubleClicked.connect(
            lambda item: self.openPathRequested.emit(item.data(Qt.UserRole)))
        root.addSpacing(10)
        root.addWidget(self.recents_title)
        root.addWidget(self.recents, 0, Qt.AlignHCenter)
        root.addStretch(3)

        create_btn.clicked.connect(self.createRequested)
        open_btn.clicked.connect(self.openRequested)

    def load_recents(self, items):
        self.recents.clear()
        self.recents_title.setVisible(bool(items))
        self.recents.setVisible(bool(items))
        for item in items:
            row = QListWidgetItem_name(item)
            self.recents.addItem(row)


def QListWidgetItem_name(item: dict):
    from PySide6.QtWidgets import QListWidgetItem
    row = QListWidgetItem(f"{item.get('name', 'Project')}  \u2014  {item.get('path', '')}")
    row.setData(Qt.UserRole, item.get("path", ""))
    return row
