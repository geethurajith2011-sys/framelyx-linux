"""
Frame Lyx — ui.main_window

The main studio window: top bar, left navigation, frame preview workspace,
project/frames/settings pages, persistent timeline, drag & drop, playback,
and the CREATE VIDEO render pipeline.
"""

from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import (QColor, QFont, QImage, QImageReader, QKeySequence,
                           QPixmap, QPainter, QShortcut)
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from core.frame_manager import (FrameSequence, MAX_FRAMES, ValidationResult,
                                scan_directory, validate_sequence)
from core.project_manager import (Autosave, Project, RecentProjects,
                                  PROJECT_EXTENSION, LEGACY_EXTENSION,
                                  app_settings, load_project, save_project)
from core.video_renderer import (CODEC_LABELS, RESOLUTION_LABELS,
                                 RenderSpec, detect_ffmpeg)
from workers.render_worker import RenderWorker
from ui.export_panel import ExportPanel
from ui.render_dialog import RenderProgressDialog
from ui.settings_dialog import SettingsDialog
from ui.timeline import TimelineWidget
from ui.welcome_screen import WelcomeScreen

FPS_PRESETS = [12, 15, 24, 25, 30, 48, 50, 60]
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp)"


def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:,.1f} seconds"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


class ValidationWorker(QThread):
    """Runs sequence validation off the GUI thread."""
    validated = Signal(object)

    def __init__(self, sequence: FrameSequence, parent=None):
        super().__init__(parent)
        self._sequence = sequence

    def run(self):
        self.validated.emit(validate_sequence(self._sequence))


class PreviewWidget(QWidget):
    """Main workspace viewer. Only ONE image lives in memory at a time,
    decoded at display resolution via QImageReader's scaled decode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("cls", "viewer")
        self.setMinimumSize(320, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image = QImage()
        self._frame_text = "No project loaded"
        self._res_text = ""

    def set_frame(self, index: int, total: int, path: str | None,
                  resolution):
        self._image = QImage()
        if path and os.path.isfile(path):
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            # Decode directly at ~viewport size — full-res never hits RAM.
            target = self._fit_size(resolution)
            if resolution and resolution[0] and target != resolution:
                reader.setScaledSize(target)
            self._image = reader.read()
        self._frame_text = f"Frame {index + 1} / {total}" if total else "No frames"
        w, h = resolution if resolution else (0, 0)
        self._res_text = f"{w} \u00d7 {h}" if w else ""
        self.update()

    def clear(self):
        self._image = QImage()
        self._frame_text = "No project loaded"
        self._res_text = ""
        self.update()

    def _fit_size(self, resolution):
        if not resolution:
            return None
        dpr = self.devicePixelRatioF() or 1.0
        avail_w = max(1, int(self.width() * dpr * 0.92))
        avail_h = max(1, int(self.height() * dpr * 0.88))
        sw, sh = resolution
        scale = min(avail_w / sw, avail_h / sh, 1.0)
        from PySide6.QtCore import QSize
        return QSize(max(1, int(sw * scale)), max(1, int(sh * scale)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(23, 24, 28))
        if not self._image.isNull():
            scaled = self._image.scaled(
                int(self.width() * 0.92), int(self.height() * 0.86),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
        p.setPen(QColor(232, 234, 237))
        f = QFont(self.font()); f.setBold(True); p.setFont(f)
        p.drawText(14, 24, self._frame_text)
        if self._res_text:
            p.setPen(QColor(154, 163, 173))
            p.drawText(self.width() - 130, 24, 116, 18,
                       Qt.AlignRight, self._res_text)
        p.end()


class ProjectPage(QWidget):
    """Project settings: name, frame folder, FPS + live project info."""
    changed = Signal()
    folderRequested = Signal()
    rescanRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setProperty("cls", "panel")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        title = QLabel("PROJECT"); title.setProperty("cls", "panelTitle")
        lay.addWidget(title)

        form = QGridLayout()
        form.setVerticalSpacing(8)
        self.name_edit = QLineEdit()
        self.folder_edit = QLineEdit(); self.folder_edit.setReadOnly(True)
        browse = QPushButton("Choose Frame Folder\u2026")
        rescan = QPushButton("Rescan")
        row = QHBoxLayout(); row.addWidget(self.folder_edit, 1)
        row.addWidget(browse); row.addWidget(rescan)

        self.fps_combo = QComboBox()
        self.fps_combo.addItems([f"{f} FPS" for f in FPS_PRESETS] + ["Custom FPS"])
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 240.0); self.fps_spin.setDecimals(2)
        self.fps_spin.setValue(24.0)
        self.fps_spin.setVisible(False)
        fps_row = QHBoxLayout(); fps_row.addWidget(self.fps_combo)
        fps_row.addWidget(self.fps_spin); fps_row.addStretch(1)

        form.addWidget(QLabel("Project Name:"), 0, 0)
        form.addWidget(self.name_edit, 0, 1)
        form.addWidget(QLabel("Frame Folder:"), 1, 0)
        form.addLayout(row, 1, 1)
        form.addWidget(QLabel("Frame Rate:"), 2, 0)
        form.addLayout(fps_row, 2, 1)
        lay.addLayout(form)

        info_title = QLabel("PROJECT INFO"); info_title.setProperty("cls", "panelTitle")
        lay.addSpacing(6); lay.addWidget(info_title)
        self.info = QLabel(""); self.info.setProperty("cls", "muted")
        self.info.setTextFormat(Qt.RichText)
        lay.addWidget(self.info)
        root.addWidget(card)

        browse.clicked.connect(self.folderRequested)
        rescan.clicked.connect(self.rescanRequested)
        self.name_edit.editingFinished.connect(self._on_name)
        self.fps_combo.currentIndexChanged.connect(self._on_fps_mode)
        self.fps_spin.valueChanged.connect(self._on_fps_value)

    def set_fps(self, fps: float):
        if fps in FPS_PRESETS:
            self.fps_combo.setCurrentIndex(FPS_PRESETS.index(fps))
            self.fps_spin.setVisible(False)
        else:
            self.fps_combo.setCurrentIndex(len(FPS_PRESETS))
            self.fps_spin.setVisible(True)
            self.fps_spin.setValue(fps)

    def current_fps(self) -> float:
        if self.fps_combo.currentIndex() == len(FPS_PRESETS):
            return self.fps_spin.value()
        return float(FPS_PRESETS[self.fps_combo.currentIndex()])

    def _on_name(self):
        self.changed.emit()

    def _on_fps_mode(self, index):
        self.fps_spin.setVisible(index == len(FPS_PRESETS))
        self.changed.emit()

    def _on_fps_value(self, _v):
        self.changed.emit()


class FramesPage(QWidget):
    """Frame sequence report: counts, validation results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setProperty("cls", "panel")
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 12, 16, 12)
        title = QLabel("FRAME SEQUENCE"); title.setProperty("cls", "panelTitle")
        lay.addWidget(title)
        self.summary = QLabel("No sequence loaded.")
        self.summary.setProperty("cls", "muted"); self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        self.issues_title = QLabel("VALIDATION")
        self.issues_title.setProperty("cls", "panelTitle")
        lay.addWidget(self.issues_title)
        self.issues = QListWidget(); self.issues.setMaximumHeight(180)
        lay.addWidget(self.issues)
        self.note = QLabel(""); self.note.setProperty("cls", "muted")
        lay.addWidget(self.note)
        root.addWidget(card)

    def show_result(self, seq: FrameSequence, result):
        self.issues.clear()
        if seq.is_empty:
            self.summary.setText("No sequence loaded.")
            return
        res = result.resolution if result else seq.resolution
        w, h = res if res else ("?", "?")
        self.summary.setText(
            f"<b>Folder:</b> {seq.directory}<br>"
            f"<b>Frames:</b> {seq.count:,} &nbsp;&nbsp; "
            f"<b>Resolution:</b> {w} \u00d7 {h}")
        if result is None:
            self.issues.addItem("Validating\u2026")
            return
        if result.ok:
            self.issues.addItem("\u2713 Sequence looks great \u2014 no issues found.")
        for issue in result.issues:
            icon = {"missing": "\u26a0", "duplicate": "\u29d6",
                    "corrupt": "\u2717", "resolution": "\u26a0"}.get(issue.kind, "\u2022")
            self.issues.addItem(f"{icon}  {issue.message}")
        self.note.setText("All checks run on file names and image headers only \u2014 "
                          "full images are never loaded, keeping RAM usage flat "
                          f"even with {MAX_FRAMES:,} frames.")


class SettingsPage(QWidget):
    """Inline settings: FFmpeg path + theme."""

    def __init__(self, on_theme_change, parent=None):
        super().__init__(parent)
        self._settings = app_settings()
        self._on_theme_change = on_theme_change
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        card = QFrame(); card.setProperty("cls", "panel")
        lay = QVBoxLayout(card); lay.setContentsMargins(16, 12, 16, 12)
        title = QLabel("SETTINGS"); title.setProperty("cls", "panelTitle")
        lay.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("FFmpeg Path:"))
        self.ffmpeg_edit = QLineEdit(
            self._settings.value("ffmpeg_path", "") or detect_ffmpeg() or "")
        detect = QPushButton("Automatically Detect FFmpeg")
        browse = QPushButton("Browse\u2026")
        row.addWidget(self.ffmpeg_edit, 1); row.addWidget(detect); row.addWidget(browse)
        lay.addLayout(row)
        self.ffmpeg_status = QLabel(); lay.addWidget(self.ffmpeg_status)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Theme", "Light Theme"])
        self.theme_combo.setCurrentIndex(
            0 if self._settings.value("theme", "dark") == "dark" else 1)
        theme_row.addWidget(self.theme_combo, 1)
        lay.addLayout(theme_row)

        hint = QLabel("Tip: Settings are also available from the top bar and "
                      "persist automatically.")
        hint.setProperty("cls", "muted")
        lay.addWidget(hint)
        root.addWidget(card)

        self.ffmpeg_edit.textChanged.connect(self._save_ffmpeg)
        detect.clicked.connect(self._detect)
        browse.clicked.connect(self._browse)
        self.theme_combo.currentIndexChanged.connect(self._change_theme)

    def _save_ffmpeg(self, text):
        self._settings.setValue("ffmpeg_path", text.strip())
        ok = os.path.isfile(text.strip())
        self.ffmpeg_status.setText(
            "\u2713 FFmpeg found." if ok else
            "\u2717 FFmpeg was not found. Please install FFmpeg and configure it in Settings.")
        self.ffmpeg_status.setStyleSheet(
            "color: #2fd48f;" if ok else "color: #f0566a;")

    def _detect(self):
        path = detect_ffmpeg()
        if path:
            self.ffmpeg_edit.setText(path)
        else:
            self.ffmpeg_status.setText("\u2717 FFmpeg was not found. Please install "
                                       "FFmpeg and configure it in Settings.")
            self.ffmpeg_status.setStyleSheet("color: #f0566a;")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select FFmpeg Executable",
                                              os.path.expanduser("~"))
        if path:
            self.ffmpeg_edit.setText(path)

    def _change_theme(self, index):
        theme = "dark" if index == 0 else "light"
        self._settings.setValue("theme", theme)
        self._on_theme_change(theme)


class MainWindow(QMainWindow):
    """Frame Lyx main studio window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Frame Lyx \u2014 Join Image Frames \u00b7 Create Videos")
        self.resize(1360, 860)

        self.project: Project | None = None
        self.sequence = FrameSequence()
        self.validation: ValidationResult | None = None
        self.current_frame = 0
        self.render_worker: RenderWorker | None = None
        self.render_dialog: RenderProgressDialog | None = None
        self._validation_worker: ValidationWorker | None = None

        self.autosave = Autosave()
        self.recent = RecentProjects()
        self._history_settings = app_settings()

        # Playback engine — a timer, so preview respects the chosen FPS.
        self.play_timer = QTimer(self)
        self.play_timer.setTimerType(Qt.PreciseTimer)
        self.play_timer.timeout.connect(self._playback_tick)

        self._build_ui()
        self._build_shortcuts()

        # Autosave every 30 s (crash recovery) — never blocks, writes are
        # tiny JSON and atomic.
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(30_000)
        self._autosave_timer.timeout.connect(self._autosave_now)
        self._autosave_timer.start()

        self.show_welcome(True)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # -- welcome page -------------------------------------------------
        self.welcome = WelcomeScreen()
        self.welcome.createRequested.connect(self.new_project)
        self.welcome.openRequested.connect(self.open_project_dialog)
        self.welcome.openPathRequested.connect(self.open_project_path)
        self.welcome.folderDropped.connect(self.set_frame_folder)
        self.welcome.filesDropped.connect(self._files_dropped)
        self.stack.addWidget(self.welcome)

        # -- studio page ---------------------------------------------------
        studio = QWidget()
        s_layout = QHBoxLayout(studio)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(0)

        sidebar = QFrame(); sidebar.setProperty("cls", "sidebar")
        sidebar.setFixedWidth(190)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(10, 14, 10, 14)
        sb.setSpacing(4)
        self.nav_buttons = []
        for label, icon in (("Project", "\u25a3"), ("Frames", "\u229e"),
                            ("Timeline", "\u23f1"), ("Export", "\u2b27"),
                            ("Settings", "\u2699")):
            btn = QPushButton(f"  {icon}  {label}")
            btn.setProperty("cls", "nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._nav_clicked)
            sb.addWidget(btn)
            self.nav_buttons.append(btn)
        sb.addStretch(1)
        self.sidebar_status = QLabel("No project")
        self.sidebar_status.setProperty("cls", "muted")
        self.sidebar_status.setWordWrap(True)
        sb.addWidget(self.sidebar_status)
        s_layout.addWidget(sidebar)

        right = QWidget()
        r = QVBoxLayout(right)
        r.setContentsMargins(12, 12, 12, 4)
        r.setSpacing(10)

        # preview workspace (always visible)
        self.preview = PreviewWidget()
        r.addWidget(self.preview, 1)

        # page stack inside a scroll area (fixed share of the window)
        self.pages = QStackedWidget()
        self.project_page = ProjectPage()
        self.frames_page = FramesPage()
        self.timeline_info = QLabel(
            "\u2022  Space \u2014 play / pause\n"
            "\u2022  \u2190 / \u2192 \u2014 previous / next frame\n"
            "\u2022  Home / End \u2014 jump to first / last frame\n"
            "\u2022  Click any thumbnail on the timeline to jump\n"
            f"\u2022  Thumbnails load lazily \u2014 safe for {MAX_FRAMES:,} frames")
        self.timeline_info.setProperty("cls", "muted")
        self.export_panel = ExportPanel()
        self.settings_page = SettingsPage(self._apply_theme)
        for w in (self.project_page, self.frames_page, self.timeline_info,
                  self.export_panel, self.settings_page):
            self.pages.addWidget(w)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setWidget(self.pages)
        page_scroll.setFixedHeight(330)
        page_scroll.setFrameShape(QFrame.NoFrame)
        r.addWidget(page_scroll)

        # persistent timeline
        self.timeline = TimelineWidget()
        self.timeline.playToggled.connect(self.set_playing)
        self.timeline.stopRequested.connect(lambda: self.set_playing(False))
        self.timeline.stepRequested.connect(self.step_frames)
        self.timeline.jumpRequested.connect(self.jump_to)
        self.timeline.seekRequested.connect(self._seek)
        r.addWidget(self.timeline)

        s_layout.addWidget(right, 1)
        self.stack.addWidget(studio)

        self.nav_buttons[0].setChecked(True)
        self.setCentralWidget(central)
        self.setAcceptDrops(True)

        # page wiring
        self.project_page.changed.connect(self._project_edited)
        self.project_page.folderRequested.connect(self.choose_frame_folder)
        self.project_page.rescanRequested.connect(self.rescan_frames)
        self.export_panel.settingsChanged.connect(self._export_edited)
        self.export_panel.renderRequested.connect(self.forge_video)
        self._load_render_history()

    def _build_topbar(self):
        bar = QFrame(); bar.setProperty("cls", "topbar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 8, 18, 8)
        mark = QLabel()
        mark_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 os.pardir, "assets", "icons",
                                 "framelyx_mark.png")
        if os.path.isfile(mark_path):
            mark.setPixmap(QPixmap(mark_path).scaled(
                36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        mark.setStyleSheet("border: none;")
        logo = QLabel("FRAME")
        logo.setProperty("cls", "logo")
        logo2 = QLabel("LYX")
        logo2.setProperty("cls", "logoAccent")
        self.project_label = QLabel("No Project")
        self.project_label.setProperty("cls", "h2")
        lay.addWidget(mark)
        lay.addSpacing(4)
        lay.addWidget(logo)
        lay.addWidget(logo2)
        lay.addSpacing(18)
        lay.addWidget(self.project_label)
        lay.addStretch(1)
        for text, slot in (("New Project", self.new_project),
                           ("Open Project", self.open_project_dialog),
                           ("Save Project", self.save_project_action),
                           ("Settings", self.open_settings_dialog)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            lay.addWidget(btn)
        return bar

    def _build_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._space_toggle)
        QShortcut(QKeySequence(Qt.Key_Left), self,
                  activated=lambda: self.step_frames(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self,
                  activated=lambda: self.step_frames(1))
        QShortcut(QKeySequence(Qt.Key_Home), self, activated=lambda: self.jump_to(0))
        QShortcut(QKeySequence(Qt.Key_End), self, activated=lambda: self.jump_to(-1))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_project)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_project_dialog)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_project_action)

    # ------------------------------------------------------------ project
    def new_project(self):
        name, ok = QInputDialog.getText(
            self, "New Project", "Project Name:", text="Untitled Project")
        if not ok:
            return
        project = Project(name=name.strip() or "Untitled Project")
        project.output_filename = Project.default_output_filename(project.name)
        self._set_project(project)
        self.show_welcome(False)
        self.pages.setCurrentIndex(0)
        if QMessageBox.question(
                self, "Choose Frames",
                "Project created.\n\nSelect the folder containing your image "
                "frames now?") == QMessageBox.Yes:
            self.choose_frame_folder()

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Frame Lyx Project", os.path.expanduser("~"),
            f"Frame Lyx Project (*{PROJECT_EXTENSION} *{LEGACY_EXTENSION})")
        if path:
            self.open_project_path(path)

    def open_project_path(self, path: str):
        try:
            project = load_project(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Open Project",
                                 f"Could not open project:\n{exc}")
            return
        self._set_project(project)
        self.recent.add(path, project.name)
        self.show_welcome(False)
        if project.frame_directory:
            self._load_sequence(project.frame_directory)

    def save_project_action(self):
        if self.project is None:
            return
        path = self.project.file_path
        if not path:
            suggested = self.project.name.replace(" ", "_") + PROJECT_EXTENSION
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project", os.path.expanduser(suggested),
                f"Frame Lyx Project (*{PROJECT_EXTENSION} *{LEGACY_EXTENSION})")
            if not path:
                return
        try:
            final = save_project(self.project, path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save Project",
                                 f"Could not save project:\n{exc}")
            return
        self.recent.add(final, self.project.name)
        self.project_label.setText(self.project.name)
        self.setWindowTitle(f"Frame Lyx \u2014 {self.project.name}")
        self._autosave.clear()

    def open_settings_dialog(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._apply_theme(dlg.current_theme())
            self.settings_page.ffmpeg_edit.setText(dlg.ffmpeg_path())

    def _apply_theme(self, theme: str):
        from PySide6.QtWidgets import QApplication
        from ui import theme as theme_mod
        app = QApplication.instance()
        if app:
            theme_mod.apply_theme(app, theme)

    def _set_project(self, project: Project):
        self.project = project
        self.validation = None
        self.current_frame = project.current_frame or 0
        self.project_label.setText(project.name)
        self.setWindowTitle(f"Frame Lyx \u2014 {project.name}")
        # push project state into the pages
        self.project_page.name_edit.setText(project.name)
        self.project_page.folder_edit.setText(project.frame_directory)
        self.project_page.set_fps(project.fps)
        self.export_panel.load_from_project(project)
        if project.frame_directory:
            self._load_sequence(project.frame_directory)
        else:
            self._refresh_all()

    def _project_edited(self):
        if self.project is None:
            return
        self.project.name = self.project_page.name_edit.text().strip() or "Untitled Project"
        self.project.fps = self.project_page.current_fps()
        if not self.project.output_filename:
            self.project.output_filename = Project.default_output_filename(self.project.name)
        self.project.touch()
        self.project_label.setText(self.project.name)
        self._refresh_all()

    def _export_edited(self):
        if self.project is None:
            return
        self.export_panel.apply_to_project(self.project)
        self.project.custom_width = self.export_panel._int_or(
            self.export_panel.custom_w.text(), 1920)
        self.project.custom_height = self.export_panel._int_or(
            self.export_panel.custom_h.text(), 1080)
        self.project.output_filename = self.export_panel.filename_edit.text().strip()
        self.project.output_directory = self.export_panel.current_output_directory()
        self.project.touch()
        self._update_export_summary()

    # -------------------------------------------------------------- frames
    def choose_frame_folder(self):
        start = (self.project.frame_directory if self.project and self.project.frame_directory
                 else os.path.expanduser("~"))
        folder = QFileDialog.getExistingDirectory(self, "Choose Frame Folder", start)
        if folder:
            self.set_frame_folder(folder)

    def set_frame_folder(self, folder: str):
        if self.project is None:
            project = Project(name=os.path.basename(folder.rstrip(os.sep)) or "Untitled Project")
            project.output_filename = Project.default_output_filename(project.name)
            self._set_project(project)
            self.show_welcome(False)
        self.project.frame_directory = os.path.abspath(folder)
        self.project.touch()
        self.project_page.folder_edit.setText(self.project.frame_directory)
        self._load_sequence(self.project.frame_directory)

    def _files_dropped(self, files):
        """Loose image files dropped: copy the set into a frame folder
        next to the first file, under <parent>/FrameLyx_Frames."""
        if not files:
            return
        first = files[0]
        target = os.path.join(os.path.dirname(os.path.abspath(first)),
                              "FrameLyx_Frames")
        os.makedirs(target, exist_ok=True)
        import shutil
        for src in files:
            dst = os.path.join(target, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dst):
                try:
                    shutil.copy2(src, dst)
                except OSError as exc:
                    QMessageBox.warning(self, "Drag & Drop",
                                        f"Could not copy {src}:\n{exc}")
        self.set_frame_folder(target)

    def rescan_frames(self):
        if self.project and self.project.frame_directory:
            self._load_sequence(self.project.frame_directory)

    def _load_sequence(self, directory: str):
        # Fast: directory listing + natural sort only, no image decoding.
        self.sequence = scan_directory(directory)
        self.sequence.resolution = None
        self.validation = None
        self.current_frame = min(self.current_frame, max(0, self.sequence.count - 1))
        self.set_playing(False)
        self.timeline.set_sequence(self.sequence.files,
                                   self.project.fps if self.project else 24)
        if not self.sequence.is_empty:
            self.sequence.resolution = self._probe_first_resolution()
        self._refresh_all()
        self.frames_page.show_result(self.sequence, None)
        # Validation (header sampling) runs in the background.
        self._validation_worker = ValidationWorker(self.sequence)
        self._validation_worker.validated.connect(self._on_validated)
        self._validation_worker.start()

    def _probe_first_resolution(self):
        from core.frame_manager import probe_resolution
        return probe_resolution(self.sequence.files[0])

    def _on_validated(self, result: ValidationResult):
        self.validation = result
        if result.resolution:
            self.sequence.resolution = result.resolution
        self.frames_page.show_result(self.sequence, result)
        self._update_project_info()
        self._update_export_summary()
        if not result.ok and any(i.kind == "corrupt" for i in result.issues):
            QMessageBox.warning(
                self, "Corrupted Images",
                "Some frames could not be read.\n\nSee the Frames page for "
                "details. Corrupted frames may be skipped by the encoder.")

    # ------------------------------------------------------------- refresh
    def _refresh_all(self):
        self._update_project_info()
        self._update_export_summary()
        self.frames_page.show_result(self.sequence, self.validation)
        self._go_to(self.current_frame)
        if self.sequence.is_empty:
            self.sidebar_status.setText("No frames detected")
        else:
            self.sidebar_status.setText(
                f"{self.sequence.count:,} frames\n"
                f"{self.sequence.resolution[0]}\u00d7{self.sequence.resolution[1]}"
                if self.sequence.resolution else f"{self.sequence.count:,} frames")
        self._update_welcome_recents()

    def _update_project_info(self):
        p, seq = self.project, self.sequence
        if p is None:
            self.project_page.info.setText("No project loaded.")
            return
        fps = self.project_page.current_fps()
        frames = seq.count
        duration = frames / fps if fps else 0
        if seq.resolution:
            out_res = seq.resolution
        else:
            out_res = ("\u2014", "\u2014")
        mode = p.resolution_mode
        out_text = (f"{out_res[0]} \u00d7 {out_res[1]} (Original)" if mode == "original"
                    else mode.upper() if mode in ("720p", "1080p", "1440p", "4k")
                    else f"{p.custom_width} \u00d7 {p.custom_height} (Custom)")
        self.project_page.info.setText(
            f"<b>Project:</b> {p.name}<br>"
            f"<b>Frames:</b> {frames:,}<br>"
            f"<b>Resolution:</b> "
            f"{f'{seq.resolution[0]} \u00d7 {seq.resolution[1]}' if seq.resolution else '\u2014'}<br>"
            f"<b>Frame Rate:</b> {fps:g} FPS<br>"
            f"<b>Estimated Duration:</b> {fmt_duration(duration)}<br>"
            f"<b>Output Resolution:</b> {out_text}<br>"
            f"<b>Output Format:</b> MP4")

    def _update_export_summary(self):
        fps = self.project_page.current_fps() if self.project else 24
        self.export_panel.update_summary(
            self.project, self.sequence.count,
            self.sequence.resolution or (0, 0), fps)

    def _update_welcome_recents(self):
        self.welcome.load_recents(self.recent.list())

    def show_welcome(self, welcome: bool):
        self.stack.setCurrentIndex(0 if welcome else 1)
        if welcome:
            self._update_welcome_recents()

    def _nav_clicked(self):
        clicked = self.sender()
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(btn is clicked)
            if btn is clicked:
                self.pages.setCurrentIndex(i)

    # ------------------------------------------------------------ playback
    def _space_toggle(self):
        if self.sequence.is_empty:
            return
        self.set_playing(not self.play_timer.isActive())

    def set_playing(self, playing: bool):
        if playing and self.sequence.is_empty:
            return
        fps = self.project_page.current_fps() if self.project else 24
        if playing:
            if self.current_frame >= self.sequence.count - 1:
                self.current_frame = 0
            self.play_timer.start(int(1000 / max(1.0, fps)))
        else:
            self.play_timer.stop()
        self.timeline.set_playing(playing)

    def step_frames(self, delta: int):
        self.set_playing(False)
        self._go_to(self.current_frame + delta)

    def jump_to(self, target: int):
        self.set_playing(False)
        self._go_to(0 if target == 0 else max(0, self.sequence.count - 1))

    def _seek(self, index: int):
        self._go_to(index)

    def _playback_tick(self):
        nxt = self.current_frame + 1
        if nxt >= self.sequence.count:
            self.set_playing(False)
            return
        self._go_to(nxt, from_playback=True)

    def _go_to(self, index: int, from_playback: bool = False):
        index = max(0, min(index, max(0, self.sequence.count - 1)))
        self.current_frame = index
        path = self.sequence.path_at(index)
        self.preview.set_frame(index, self.sequence.count, path,
                               self.sequence.resolution)
        seconds = index / self.project_page.current_fps() if self.project else 0
        self.timeline.set_position(index, seconds)
        if self.project:
            self.project.current_frame = index
            self.project.touch()

    # -------------------------------------------------------------- render
    def forge_video(self):
        if self.project is None or self.sequence.is_empty:
            QMessageBox.warning(self, "Forge Video",
                                "No image frames were found in the selected folder.")
            return
        ffmpeg_path = SettingsDialog.ffmpeg_path()
        if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
            QMessageBox.critical(
                self, "FFmpeg Missing",
                "FFmpeg was not found. Please install FFmpeg and configure "
                "it in Settings.")
            return
        if self.render_worker is not None and self.render_worker.isRunning():
            QMessageBox.information(self, "Forge Video",
                                    "A render is already running.")
            return

        self.export_panel.apply_to_project(self.project)
        self.project.fps = self.project_page.current_fps()
        output = self.project.output_path()
        if not self.project.output_directory:
            suggested = output
            chosen, _ = QFileDialog.getSaveFileName(
                self, "Choose Output Video", suggested, "MP4 Video (*.mp4)")
            if not chosen:
                return
            if not chosen.lower().endswith(".mp4"):
                chosen += ".mp4"
            output = chosen
            self.project.output_directory = os.path.dirname(chosen)
            self.project.output_filename = os.path.basename(chosen)

        spec = RenderSpec(
            fps=self.project.fps, codec=self.project.codec,
            quality=self.project.quality, resolution_mode=self.project.resolution_mode,
            custom_width=self.project.custom_width,
            custom_height=self.project.custom_height,
            fit_mode=self.project.fit_mode, output_path=output)
        error = spec.validate()
        if error:
            QMessageBox.warning(self, "Forge Video", error)
            return

        files = list(self.sequence.files)
        self.render_worker = RenderWorker(ffmpeg_path, files, spec)
        self.render_dialog = RenderProgressDialog(self.project.name, self)
        self.render_dialog.cancelRequested.connect(self.render_worker.cancel)
        self.render_worker.progress.connect(self.render_dialog.on_progress)
        self.render_worker.finished_render.connect(self._on_render_finished)
        self.set_playing(False)
        self.render_worker.start()
        self.render_dialog.show()

    def _on_render_progress(self, processed, total, current, eta):
        if self.render_dialog:
            self.render_dialog.on_progress(processed, total, current, eta)

    def _on_render_finished(self, success: bool, message: str, output: str):
        if self.render_dialog:
            self.render_dialog.accept()
            self.render_dialog = None
        worker, self.render_worker = self.render_worker, None
        if worker:
            worker.deleteLater()
        if success:
            self.export_panel.add_history(
                f"\u2713 {self.project.name} \u2192 {output}  "
                f"({self.sequence.count:,} frames)")
            self._record_history(output)
            box = QMessageBox(self)
            box.setWindowTitle("Render Complete")
            box.setText(f"Video created successfully!\n\n{output}")
            open_video = box.addButton("Open Video", QMessageBox.AcceptRole)
            open_folder = box.addButton("Open Folder", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Close)
            box.exec()
            clicked = box.clickedButton()
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            if clicked is open_video:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output))
            elif clicked is open_folder:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(os.path.dirname(output)))
        elif message != "Rendering cancelled.":
            QMessageBox.critical(self, "Render Failed", message)

    def _record_history(self, output: str):
        try:
            items = json.loads(self._history_settings.value("render_history", "[]"))
        except (TypeError, ValueError):
            items = []
        items.insert(0, {"project": self.project.name, "output": output,
                         "frames": self.sequence.count, "fps": self.project.fps,
                         "codec": CODEC_LABELS[self.project.codec]})
        self._history_settings.setValue("render_history",
                                        json.dumps(items[:20]))

    def _load_render_history(self):
        try:
            items = json.loads(self._history_settings.value("render_history", "[]"))
        except (TypeError, ValueError):
            items = []
        for item in reversed(items):
            self.export_panel.add_history(
                f"\u2713 {item.get('project', '?')} \u2192 {item.get('output', '?')}  "
                f"({item.get('frames', 0):,} frames)")

    # --------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        folders, files = [], []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isdir(path):
                folders.append(path)
            elif path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                files.append(path)
        if folders:
            self.set_frame_folder(folders[0])
        elif files:
            self._files_dropped(files)

    # ------------------------------------------------------------- lifecycle
    def _autosave_now(self):
        if self.project is not None and self.project.file_path or \
                (self.project is not None and self.project.dirty):
            self.autosave.save(self.project)

    def closeEvent(self, event):
        self.set_playing(False)
        self._autosave_now()
        if self.render_worker is not None and self.render_worker.isRunning():
            if QMessageBox.question(
                    self, "Render in progress",
                    "A video is still rendering. Quit and cancel the render?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.render_worker.cancel()
            self.render_worker.wait(5000)
        self.timeline.strip.shutdown()
        super().closeEvent(event)
