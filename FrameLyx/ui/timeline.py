"""
Frame Lyx — ui.timeline

Virtualised thumbnail timeline + transport controls.

Only the thumbnails actually visible in the viewport are decoded, at
thumbnail size, on a single background loader thread with a priority
queue (the playhead area is prioritised).  A bounded LRU cache keeps RAM
flat even with 20,000 frames — full images are never loaded here.
"""

from __future__ import annotations

import queue
from collections import OrderedDict

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSlider, QVBoxLayout, QWidget)

THUMB_W, THUMB_H = 128, 72        # 16:9 cells
CELL_PAD = 6
CELL_W = THUMB_W + CELL_PAD
STRIP_H = THUMB_H + 34            # strip + caption band
CACHE_LIMIT = 800                 # LRU bound (~800 tiny images max)


class _ThumbLoader(QThread):
    """Background decoder: pulls indexes from a priority queue."""
    thumbReady = Signal(int, QImage)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = 0

    def request(self, index: int, path: str, priority: int = 0):
        self._seq += 1
        self._queue.put((priority, self._seq, index, path))

    def clear_pending(self):
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def run(self):
        while True:
            try:
                _, _, index, path = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if path is None:            # poison pill -> exit
                return
            reader = QImageReader(path)
            # Decode at 2x cell size for HiDPI; tiny memory footprint.
            reader.setScaledSize(QSize(THUMB_W * 2, THUMB_H * 2))
            img = reader.read()
            if not img.isNull():
                self.thumbReady.emit(index, img)


class ThumbnailStrip(QWidget):
    """Custom-painted, virtualised filmstrip."""
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._current = 0
        self._cache: OrderedDict[int, QImage] = OrderedDict()
        self._pending: set[int] = set()
        self._scroll: QScrollArea | None = None   # owning scroll area
        self.setFixedHeight(STRIP_H)

        self._loader = _ThumbLoader()
        self._loader.thumbReady.connect(self._on_thumb)
        self._loader.start()

    # -- API -------------------------------------------------------------
    def set_scroll_area(self, scroll: QScrollArea):
        self._scroll = scroll

    def set_sequence(self, files: list[str]):
        self._files = files
        self._cache.clear()
        self._pending.clear()
        self._loader.clear_pending()
        self._current = min(self._current, max(0, len(files) - 1))
        self.updateGeometry()
        self.update()

    def set_current(self, index: int, scroll_to: bool = True):
        index = max(0, min(index, max(0, len(self._files) - 1)))
        self._current = index
        if scroll_to:
            x = index * CELL_W
            scroll = self._scroll
            if isinstance(scroll, QScrollArea):
                bar = scroll.horizontalScrollBar()
                view_w = scroll.viewport().width()
                if x < bar.value() + view_w * 0.15:
                    bar.setValue(max(0, x - view_w // 2))
                elif x > bar.value() + view_w * 0.85:
                    bar.setValue(x - view_w // 2)
        self.update()

    def shutdown(self):
        self._loader.request(0, None, priority=-1)   # poison pill
        self._loader.wait(3000)                      # join cleanly on exit

    # -- internals ---------------------------------------------------------
    def _on_thumb(self, index: int, image: QImage):
        self._cache[index] = image
        self._pending.discard(index)
        while len(self._cache) > CACHE_LIMIT:
            self._cache.popitem(last=False)          # evict oldest
        self.update()

    def sizeHint(self):
        return QSize(max(400, len(self._files) * CELL_W), STRIP_H)

    def paintEvent(self, event):
        painter = QPainter(self)
        pal = self.palette()
        bg = pal.color(pal.ColorRole.Window)
        text = pal.color(pal.ColorRole.Text)
        painter.fillRect(self.rect(), bg)
        if not self._files:
            painter.setPen(QColor(120, 128, 138))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No frames loaded — open a project to build the timeline")
            painter.end()
            return

        scroll = self._scroll
        offset = scroll.horizontalScrollBar().value() if isinstance(scroll, QScrollArea) else 0
        view_w = scroll.viewport().width() if isinstance(scroll, QScrollArea) else self.width()

        first = max(0, offset // CELL_W - 1)
        last = min(len(self._files) - 1, (offset + view_w) // CELL_W + 1)

        font = QFont(self.font())
        font.setPointSizeF(max(7.5, self.font().pointSizeF() - 1.5))
        painter.setFont(font)
        accent = QColor("#29d3ff")

        for idx in range(first, last + 1):
            x = idx * CELL_W - offset
            y = 6
            selected = idx == self._current
            # cell background
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(24, 30, 58) if not selected
                             else QColor(34, 48, 85))
            painter.drawRoundedRect(x, y, THUMB_W, THUMB_H + 20, 6, 6)
            img = self._cache.get(idx)
            if img is not None:
                painter.drawImage(x + 4, y + 4, img.scaled(
                    THUMB_W - 8, THUMB_H - 8,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                painter.fillRect(x + 4, y + 4, THUMB_W - 8, THUMB_H - 8,
                                 QColor(16, 20, 40))
                if idx not in self._pending:
                    self._pending.add(idx)
                    # priority 0 = near playhead (loaded first)
                    prio = 0 if abs(idx - self._current) < 40 else 1
                    self._loader.request(idx, self._files[idx], priority=prio)
            painter.setPen(text if not selected else accent)
            painter.drawText(x, y + THUMB_H + 2, THUMB_W, 16,
                             Qt.AlignCenter, str(idx + 1))
            if selected:
                pen = painter.pen()
                pen.setColor(accent)
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(x, y, THUMB_W, THUMB_H + 20, 6, 6)
        painter.end()

    def mousePressEvent(self, event):
        scroll = self._scroll
        offset = scroll.horizontalScrollBar().value() if isinstance(scroll, QScrollArea) else 0
        index = int((event.position().x() + offset) // CELL_W)
        if 0 <= index < len(self._files):
            self.seekRequested.emit(index)
        super().mousePressEvent(event)


class TimelineWidget(QWidget):
    """Transport controls + filmstrip + scrubber."""
    playToggled = Signal(bool)
    stopRequested = Signal()
    stepRequested = Signal(int)          # +/- frame steps
    jumpRequested = Signal(int)          # 0=first, -1=last
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 8)
        root.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.btn_first = QPushButton("\u23ee")
        self.btn_prev = QPushButton("\u25c0")
        self.btn_play = QPushButton("\u25b6")
        self.btn_stop = QPushButton("\u23f9")
        self.btn_next = QPushButton("\u25b6\u25b6")
        self.btn_last = QPushButton("\u23ed")
        for b in (self.btn_first, self.btn_prev, self.btn_play,
                  self.btn_stop, self.btn_next, self.btn_last):
            b.setProperty("cls", "tool")
            b.setFixedWidth(46)
        self.btn_play.setFixedWidth(56)

        self.frame_label = QLabel("Frame 0 / 0")
        self.frame_label.setProperty("cls", "muted")
        self.time_label = QLabel("00:00.0")
        self.time_label.setProperty("cls", "muted")

        controls.addWidget(self.btn_first)
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_stop)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.btn_last)
        controls.addSpacing(12)
        controls.addWidget(self.frame_label)
        controls.addStretch(1)
        controls.addWidget(self.time_label)
        root.addLayout(controls)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setSingleStep(1)
        root.addWidget(self.slider)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(ThumbnailStrip())
        self.scroll.setFixedHeight(STRIP_H + 14)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.verticalScrollBar().setEnabled(False)
        root.addWidget(self.scroll)

        self.strip = self.scroll.widget()
        self.strip.set_scroll_area(self.scroll)
        self.strip.seekRequested.connect(self._on_strip_seek)
        self.slider.valueChanged.connect(self._on_slider)
        self.btn_first.clicked.connect(lambda: self.jumpRequested.emit(0))
        self.btn_last.clicked.connect(lambda: self.jumpRequested.emit(-1))
        self.btn_prev.clicked.connect(lambda: self.stepRequested.emit(-1))
        self.btn_next.clicked.connect(lambda: self.stepRequested.emit(1))
        self.btn_play.clicked.connect(self._on_play)
        self.btn_stop.clicked.connect(self.stopRequested)

    # -- API -----------------------------------------------------------------
    def set_sequence(self, files, fps: float):
        self.strip.set_sequence(files)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(files) - 1))
        self.slider.blockSignals(False)
        self.set_position(0, 0.0)
        if fps:
            self.slider.setPageStep(max(1, int(fps)))

    def set_position(self, index: int, seconds: float = None):
        total = max(0, len(self.strip._files) - 1)
        self.frame_label.setText(f"Frame {index + 1} / {total + 1}")
        if seconds is not None:
            m, s = divmod(seconds, 60)
            self.time_label.setText(f"{int(m):02d}:{s:04.1f}")
        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self.strip.set_current(index)

    def set_playing(self, playing: bool):
        self.btn_play.setText("\u23f8" if playing else "\u25b6")

    # -- internals -------------------------------------------------------------
    def _on_play(self):
        playing = self.btn_play.text() == "\u25b6"
        self.set_playing(playing)
        self.playToggled.emit(playing)

    def _on_slider(self, value):
        self.seekRequested.emit(value)

    def _on_strip_seek(self, index):
        self.slider.setValue(index)
        self.seekRequested.emit(index)
