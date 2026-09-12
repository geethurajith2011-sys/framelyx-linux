"""
Frame Lyx — core.project_manager

Project model, JSON persistence (``*.framelyx``), recent-projects list
and crash-recovery autosave.  Frame *paths* are not stored in the project
file — only the frame folder is — so reopening a project re-scans the
folder (keeps files small even for 10k-frame projects and adapts if new
frames were rendered).

Legacy ``*.frameforger`` project files (from the Frame Forger days) are
still opened transparently.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from PySide6.QtCore import QSettings, QStandardPaths

PROJECT_EXTENSION = ".framelyx"
LEGACY_EXTENSION = ".frameforger"
AUTOSAVE_NAME = "autosave.framelyx"
LEGACY_AUTOSAVE_NAME = "autosave.frameforger"

_ORG = "FrameLyx"
_APP = "FrameLyx"
_LEGACY_ORG = "FrameForger"
_LEGACY_APP = "FrameForger"

_VALID_CODECS = {"h264", "h265"}
_VALID_QUALITIES = {"draft", "standard", "high", "ultra"}
_VALID_RESOLUTION_MODES = {"original", "720p", "1080p", "1440p", "4k", "custom"}
_VALID_FIT_MODES = {"stretch", "fit", "crop"}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def config_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    path = os.path.join(base, "FrameLyx")
    os.makedirs(path, exist_ok=True)
    return path


def app_settings() -> QSettings:
    """Application QSettings under the Frame Lyx identity.

    On first run after the rebrand, settings stored under the old
    "FrameForger" identity (theme, FFmpeg path, recent projects, render
    history) are migrated once so nothing is lost for existing users.
    """
    settings = QSettings(_ORG, _APP)
    if not settings.value("migrated_from_frameforger", False, type=bool):
        legacy = QSettings(_LEGACY_ORG, _LEGACY_APP)
        for key in legacy.allKeys():
            if not settings.contains(key):
                settings.setValue(key, legacy.value(key))
        settings.setValue("migrated_from_frameforger", True)
        settings.sync()
    return settings


@dataclass
class Project:
    """Everything Frame Lyx needs to restore a working session."""
    name: str = "Untitled Project"
    frame_directory: str = ""
    fps: float = 24.0
    # --- output settings --------------------------------------------------
    codec: str = "h264"                 # "h264" | "h265"
    quality: str = "standard"           # draft | standard | high | ultra
    resolution_mode: str = "original"   # original|720p|1080p|1440p|4k|custom
    custom_width: int = 1920
    custom_height: int = 1080
    fit_mode: str = "fit"               # stretch | fit | crop
    output_directory: str = ""
    output_filename: str = ""
    current_frame: int = 0
    open_output_folder: bool = True
    created: str = field(default_factory=_now_iso)
    modified: str = field(default_factory=_now_iso)
    # Not serialised:
    file_path: str = ""
    dirty: bool = False

    # -- helpers -----------------------------------------------------------
    def output_path(self) -> str:
        name = self.output_filename.strip() or self.default_output_filename(self.name)
        if not name.lower().endswith(".mp4"):
            name += ".mp4"
        folder = self.output_directory or self.frame_directory or os.path.expanduser("~")
        return os.path.join(folder, name)

    @staticmethod
    def default_output_filename(project_name: str = "") -> str:
        base = project_name or "output"
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in base)
        return safe.strip().replace(" ", "_") + ".mp4"

    def touch(self) -> None:
        self.modified = _now_iso()
        self.dirty = True

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("file_path", None)
        data.pop("dirty", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        project = cls()
        for key, value in data.items():
            if hasattr(project, key) and key not in ("file_path", "dirty"):
                setattr(project, key, value)
        # Defensive: normalise any hand-edited values.
        project.codec = project.codec if project.codec in _VALID_CODECS else "h264"
        project.quality = project.quality if project.quality in _VALID_QUALITIES else "standard"
        if project.resolution_mode not in _VALID_RESOLUTION_MODES:
            project.resolution_mode = "original"
        if project.fit_mode not in _VALID_FIT_MODES:
            project.fit_mode = "fit"
        project.fps = max(1.0, float(project.fps))
        return project


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_project(project: Project, path: Optional[str] = None) -> str:
    """Atomically write the project as JSON and return the path used."""
    path = path or project.file_path
    if not path:
        raise ValueError("Project has no file path")
    if not path.endswith(PROJECT_EXTENSION):
        path += PROJECT_EXTENSION

    project.modified = _now_iso()
    project.file_path = path
    project.dirty = False

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(project.to_dict(), fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)          # atomic on POSIX and Windows
    return path


def load_project(path: str) -> Project:
    """Load a ``.framelyx`` (or legacy ``.frameforger``) file; raises on
    unreadable content."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or "name" not in data:
        raise ValueError("Not a valid Frame Lyx project file.")
    project = Project.from_dict(data)
    project.file_path = path
    return project


# ---------------------------------------------------------------------------
# Recent projects
# ---------------------------------------------------------------------------

class RecentProjects:
    """Small JSON-backed list of recently opened projects (max 10)."""

    MAX_ITEMS = 10

    def __init__(self) -> None:
        self._settings = app_settings()

    def _raw(self) -> List[dict]:
        try:
            data = json.loads(self._settings.value("recent_projects", "[]"))
            return data if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []

    def list(self) -> List[dict]:
        return [i for i in self._raw() if os.path.exists(i.get("path", ""))]

    def add(self, path: str, name: str) -> None:
        items = [i for i in self._raw() if i.get("path") != path]
        items.insert(0, {"path": path, "name": name, "opened": _now_iso()})
        self._settings.setValue("recent_projects",
                                json.dumps(items[: self.MAX_ITEMS]))

    def remove(self, path: str) -> None:
        items = [i for i in self._raw() if i.get("path") != path]
        self._settings.setValue("recent_projects", json.dumps(items))


# ---------------------------------------------------------------------------
# Autosave / crash recovery
# ---------------------------------------------------------------------------

class Autosave:
    """Autosaves unsaved projects into the app config folder so work can
    be recovered after a crash.  Projects that already have a file path are
    simply saved in place (the atomic write keeps the file always valid)."""

    def __init__(self) -> None:
        self._path = os.path.join(config_dir(), AUTOSAVE_NAME)
        self._legacy_path = os.path.join(config_dir(), LEGACY_AUTOSAVE_NAME)

    def save(self, project: Project) -> None:
        try:
            if project.file_path:
                save_project(project)
            else:
                real_path = project.file_path      # keep "unsaved" state
                save_project(project, self._path)
                project.file_path = real_path
        except OSError:
            pass  # autosave must never take the app down

    def has_recovery(self) -> bool:
        return os.path.exists(self._path) or os.path.exists(self._legacy_path)

    def load_recovery(self) -> Optional[Project]:
        path = (self._path if os.path.exists(self._path)
                else self._legacy_path)
        try:
            project = load_project(path)
            project.file_path = ""       # treat as unsaved
            project.dirty = True
            return project
        except (OSError, ValueError):
            return None

    def clear(self) -> None:
        for path in (self._path, self._legacy_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
