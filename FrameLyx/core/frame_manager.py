"""
Frame Lyx — core.frame_manager

Frame discovery, natural (numerical) sorting and lightweight sequence
validation.  This module deliberately never decodes full image data:
resolution probing uses QImageReader's metadata path, so a folder of
20,000 frames can be scanned almost instantly with minimal RAM use.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PySide6.QtGui import QImageReader

#: File extensions recognised as video source frames.
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

#: Maximum number of frames supported per project (advertised capacity).
MAX_FRAMES = 20_000

_NUMBER_RE = re.compile(r"(\d+)")


# ---------------------------------------------------------------------------
# Natural sorting
# ---------------------------------------------------------------------------

def natural_key(filename: str):
    """Sort key that orders embedded numbers numerically.

    ``frame_2.png`` sorts before ``frame_10.png``.  Each chunk is a
    uniform 3-tuple ``(kind, number, text)`` so comparisons never mix
    int with str.
    """
    key = []
    for token in _NUMBER_RE.split(filename):
        if token.isdigit():
            key.append((0, int(token), ""))
        else:
            key.append((1, 0, token.lower()))
    return key


def is_image_file(filename: str) -> bool:
    """True when *filename* has a supported image extension."""
    return os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS


def _number_pattern(filename: str) -> str:
    """Collapse digit runs so ``frame_0001.png`` and ``frame_0002.png``
    share the pattern ``frame_####.png``.  Used for gap/duplicate checks."""
    stem, ext = os.path.splitext(filename)
    return _NUMBER_RE.sub("#", stem).lower() + ext.lower()


def _trailing_number(filename: str) -> Optional[int]:
    """Last number embedded in the stem (typical frame counters count up
    at the end of the name, e.g. ``render001.jpg``)."""
    stem = os.path.splitext(filename)[0]
    found = _NUMBER_RE.findall(stem)
    return int(found[-1]) if found else None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SequenceIssue:
    """A single problem detected while validating a frame sequence."""
    kind: str        # "missing" | "duplicate" | "corrupt" | "resolution"
    message: str


@dataclass
class FrameSequence:
    """An ordered list of frame files plus lightweight metadata."""
    directory: str = ""
    files: List[str] = field(default_factory=list)            # absolute paths
    numbers: List[Optional[int]] = field(default_factory=list)  # per file
    resolution: Optional[Tuple[int, int]] = None              # first frame

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def is_empty(self) -> bool:
        return not self.files

    def path_at(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.files):
            return self.files[index]
        return None

    def name_at(self, index: int) -> str:
        path = self.path_at(index)
        return os.path.basename(path) if path else ""


@dataclass
class ValidationResult:
    """Outcome of :func:`validate_sequence`."""
    resolution: Optional[Tuple[int, int]] = None
    mixed_resolutions: bool = False
    corrupt_files: List[str] = field(default_factory=list)
    missing_numbers: Dict[str, List[int]] = field(default_factory=dict)
    duplicates: List[str] = field(default_factory=list)
    issues: List[SequenceIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


# ---------------------------------------------------------------------------
# Scanning / probing
# ---------------------------------------------------------------------------

def scan_directory(directory: str) -> FrameSequence:
    """Scan *directory* for supported images and return them in natural
    numerical order.  Only directory entries are read — no image data."""
    seq = FrameSequence(directory=os.path.abspath(directory))
    try:
        entries = os.listdir(directory)
    except OSError:
        return seq

    names = [e for e in entries
             if is_image_file(e) and not e.startswith(".")]
    names.sort(key=natural_key)

    for name in names:
        seq.files.append(os.path.join(seq.directory, name))
        seq.numbers.append(_trailing_number(name))
    return seq


def probe_resolution(path: str) -> Optional[Tuple[int, int]]:
    """Read an image's pixel size without decoding pixel data when the
    format allows it (PNG/JPEG store dimensions in their headers)."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        return size.width(), size.height()
    image = reader.read()  # header-less fallback
    if not image.isNull():
        return image.width(), image.height()
    return None


def validate_sequence(seq: FrameSequence, probe_sample: int = 16) -> ValidationResult:
    """Validate a sequence cheaply.

    * Resolution is read from headers of evenly-spaced sample frames
      (never the whole sequence) so a 20,000 frame project stays fast.
    * Corrupt-file detection also samples; FFmpeg catches anything else
      at render time.
    * Missing-frame gaps and duplicate numbers are derived from file
      *names* alone, which costs nothing.
    """
    result = ValidationResult()

    if seq.is_empty:
        result.issues.append(SequenceIssue(
            "missing", "No image frames were found in the selected folder."))
        return result

    # --- Resolution sampling --------------------------------------------
    step = max(1, seq.count // max(1, probe_sample))
    samples = list(range(0, seq.count, step))[:probe_sample]
    if seq.count - 1 not in samples:
        samples.append(seq.count - 1)

    resolutions: Dict[Tuple[int, int], int] = {}
    for idx in samples:
        res = probe_resolution(seq.files[idx])
        if res is None:
            result.corrupt_files.append(seq.files[idx])
        else:
            resolutions[res] = resolutions.get(res, 0) + 1

    if resolutions:
        # Most common sampled resolution wins; first frame's size is the
        # project resolution.
        first = probe_resolution(seq.files[0])
        result.resolution = first if first else max(
            resolutions, key=lambda r: resolutions[r])
        result.mixed_resolutions = len(resolutions) > 1
        if result.mixed_resolutions:
            pretty = ", ".join(f"{w}\u00d7{h}" for w, h in sorted(resolutions))
            result.issues.append(SequenceIssue(
                "resolution",
                "Frames have mixed resolutions (" + pretty + "). The first "
                "frame's resolution is used and everything is scaled "
                "automatically during rendering."))

    for path in result.corrupt_files:
        result.issues.append(SequenceIssue(
            "corrupt", "Corrupted or unreadable image (will be skipped by "
            "the encoder if possible): " + os.path.basename(path)))

    # --- Missing frame detection (name based, free) ----------------------
    groups: Dict[str, List[int]] = {}
    for path, number in zip(seq.files, seq.numbers):
        if number is None:
            continue
        pattern = _number_pattern(os.path.basename(path))
        groups.setdefault(pattern, []).append(number)

    for pattern, numbers in groups.items():
        present = set(numbers)
        gaps = [n for n in range(min(numbers), max(numbers) + 1)
                if n not in present]
        if gaps:
            preview = ", ".join(str(g) for g in gaps[:10])
            more = "" if len(gaps) <= 10 else f" \u2026 (+{len(gaps) - 10} more)"
            result.missing_numbers[pattern] = gaps
            result.issues.append(SequenceIssue(
                "missing",
                f"{len(gaps)} missing frame number(s) detected in pattern "
                f"'{pattern}': {preview}{more}"))

    # --- Duplicate detection ---------------------------------------------
    seen: Dict[Tuple[str, int], List[str]] = {}
    for path, number in zip(seq.files, seq.numbers):
        if number is None:
            continue
        key = (_number_pattern(os.path.basename(path)), number)
        seen.setdefault(key, []).append(os.path.basename(path))
    for (pattern, number), names in seen.items():
        if len(names) > 1:
            result.duplicates.append(f"{pattern} #{number}: " + ", ".join(names))
            result.issues.append(SequenceIssue(
                "duplicate",
                f"Duplicate frame number {number} in pattern '{pattern}' "
                f"({len(names)} files). All of them are kept in natural order."))
    return result
