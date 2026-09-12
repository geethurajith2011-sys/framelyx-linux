"""
Frame Lyx — core.video_renderer

The genuine FFmpeg encoding pipeline.  A temporary ffconcat list file
streams the frames to FFmpeg in exact natural order — no image is ever
decoded by Python and no files are duplicated.

FFmpeg's concat demuxer picks its decoder from the FIRST file of the
list, so a sequence that mixes formats (PNG + JPG + WEBP\u2026) would drop
frames.  To stay correct for any project, the sequence is split into
*contiguous same-format runs*: each run is encoded to an intermediate
MPEG-TS segment with identical codec settings, and the segments are then
stream-copied (-c copy) into the final MP4.  Homogeneous projects — the
overwhelming majority — take the single-pass fast path with zero extra
temporary video data.

Progress is parsed from FFmpeg's machine-readable ``-progress`` stream.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

#: Resolution presets (width, height).
RESOLUTION_PRESETS = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "4k": (3840, 2160),
}

#: Quality preset -> (CRF, x264/x265 speed preset).
QUALITY_PRESETS = {
    "draft": (28, "veryfast"),
    "standard": (23, "medium"),
    "high": (20, "slow"),
    "ultra": (18, "slower"),
}

#: Rough bits-per-pixel used only for the *estimated* file size readout.
QUALITY_BPP = {"draft": 0.045, "standard": 0.080, "high": 0.120, "ultra": 0.170}

CODECS = {"h264": "libx264", "h265": "libx265"}
CODEC_LABELS = {"h264": "H.264 (AVC)", "h265": "H.265 / HEVC"}
QUALITY_LABELS = {"draft": "Draft", "standard": "Standard",
                  "high": "High Quality", "ultra": "Ultra Quality"}
RESOLUTION_LABELS = {"original": "Original Image Resolution",
                     "custom": "Custom Resolution", **
                     {k: k.upper() for k in RESOLUTION_PRESETS}}
FIT_LABELS = {"stretch": "Stretch", "fit": "Fit (letterbox)", "crop": "Crop"}


def detect_ffmpeg() -> Optional[str]:
    """Locate an FFmpeg executable (PATH first, then common Windows spots)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        r"C:\\ffmpeg\\bin\\ffmpeg.exe",
        r"C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.expanduser("~/ffmpeg/ffmpeg"),
        "/usr/local/bin/ffmpeg",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


@dataclass
class RenderSpec:
    """Everything the encoder needs, fully resolved (no UI types)."""
    fps: float
    codec: str = "h264"              # h264 | h265
    quality: str = "standard"        # see QUALITY_PRESETS
    resolution_mode: str = "original"
    custom_width: int = 1920
    custom_height: int = 1080
    fit_mode: str = "fit"            # stretch | fit | crop
    output_path: str = ""

    def target_resolution(self, src_w: int, src_h: int) -> Tuple[int, int]:
        if self.resolution_mode == "original":
            return src_w, src_h
        if self.resolution_mode == "custom":
            return self.custom_width, self.custom_height
        return RESOLUTION_PRESETS[self.resolution_mode]

    def validate(self) -> Optional[str]:
        if self.fps <= 0:
            return "Frame rate must be greater than zero."
        if self.codec not in CODECS:
            return "Unsupported codec: " + str(self.codec)
        if self.quality not in QUALITY_PRESETS:
            return "Unsupported quality preset: " + str(self.quality)
        if self.fit_mode not in FIT_LABELS:
            return "Unsupported aspect-ratio mode: " + str(self.fit_mode)
        if self.resolution_mode == "custom" and (
                self.custom_width < 16 or self.custom_height < 16):
            return "Custom resolution must be at least 16\u00d716 pixels."
        if not self.output_path:
            return "No output file was specified."
        return None


def build_scale_filter(spec: RenderSpec, src_w: int, src_h: int) -> str:
    """Professional aspect-ratio handling.

    * stretch \u2014 force exact target size (distorts if aspect differs)
    * fit     \u2014 scale down to fit, pad the remainder (letterbox)
    * crop    \u2014 scale up to cover, crop the overflow (centered)
    """
    out_w, out_h = spec.target_resolution(src_w, src_h)
    # Encoders need even dimensions for yuv420p.
    even = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    if spec.resolution_mode == "original":
        return even  # keep source size, only force even dims
    if spec.fit_mode == "stretch":
        return f"scale={out_w}:{out_h}"
    if spec.fit_mode == "fit":
        return (f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
                f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color=black")
    # crop
    return (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}")


def estimate_output_size(spec: RenderSpec, frame_count: int,
                         src_w: int, src_h: int) -> int:
    """Rough size estimate (bytes): duration x resolution x bpp heuristic."""
    if frame_count <= 0:
        return 0
    out_w, out_h = spec.target_resolution(src_w, src_h)
    duration = frame_count / spec.fps
    bpp = QUALITY_BPP.get(spec.quality, 0.08)
    bitrate = out_w * out_h * spec.fps * bpp      # bits per second
    return int(duration * bitrate / 8.0)


def _concat_escape(path: str) -> str:
    """Escape a path for the ffconcat list (single-quoted, forward slashes)."""
    return path.replace("\\", "/").replace("'", "'\\''")


def write_concat_list(files: List[str], fps: float, list_path: str) -> None:
    """Write an ffconcat playlist with one entry per frame.

    Each entry carries ``duration = 1/fps`` so the container timing is
    exact even for perfectly-formatted or irregular file names.  The last
    frame is repeated once because the concat demuxer drops the final
    duration otherwise (the redundant output frame is capped with
    ``-frames:v``).
    """
    duration = 1.0 / float(fps)
    with open(list_path, "w", encoding="utf-8") as fh:
        fh.write("ffconcat version 1.0\n")
        for path in files:
            fh.write(f"file '{_concat_escape(path)}'\n")
            fh.write(f"duration {duration:.6f}\n")
        if files:
            fh.write(f"file '{_concat_escape(files[-1])}'\n")


def _contiguous_format_runs(files: List[str]) -> List[List[str]]:
    """Split *files* into runs of consecutive files with the same image
    format (by extension).  Each run can be decoded by FFmpeg with a
    single decoder, which is what the concat demuxer requires."""
    runs: List[List[str]] = []
    for path in files:
        ext = os.path.splitext(path)[1].lower()
        if runs and os.path.splitext(runs[-1][-1])[1].lower() == ext:
            runs[-1].append(path)
        else:
            runs.append([path])
    return runs


class VideoRenderer:
    """Runs FFmpeg as a subprocess and reports real progress.

    Intended to live on a worker thread.  ``progress_cb(processed, total,
    current_name, eta_seconds)`` is invoked as FFmpeg reports progress.
    """

    def __init__(self, ffmpeg_path: str) -> None:
        self.ffmpeg_path = ffmpeg_path
        self._process: Optional[subprocess.Popen] = None
        self._cancelled = False

    def cancel(self) -> None:
        """Request graceful cancellation from any thread."""
        self._cancelled = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()          # SIGTERM: FFmpeg finalises cleanly
            except OSError:
                pass

    # -- internals -----------------------------------------------------------
    def _emit(self, cb, processed, total, current, eta):
        if cb:
            try:
                cb(min(processed, total), total, current, max(0.0, eta))
            except Exception:
                pass

    def _run(self, cmd: List[str]) -> Tuple[int, str]:
        """Run FFmpeg, return (returncode, stderr tail)."""
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            return -1, f"Could not launch FFmpeg: {exc}"
        stderr_tail = ""
        proc = self._process
        # stdout carries -progress key=value lines; drain it concurrently
        # with stderr to avoid any pipe deadlock.
        def drain_stdout():
            for _ in proc.stdout:
                pass
        import threading
        t = threading.Thread(target=drain_stdout, daemon=True)
        t.start()
        for line in proc.stderr:
            stderr_tail = (stderr_tail + line)[-2000:]
        code = proc.wait()
        t.join(timeout=5)
        self._process = None
        return code, stderr_tail.strip()

    def _encode_run(self, files: List[str], spec: RenderSpec, out_path: str,
                    frame_offset: int, total: int, started: float,
                    progress_cb, temp_files: List[str], to_mpegts: bool,
                    src_w: int, src_h: int) -> Tuple[bool, str]:
        """Encode one contiguous same-format run of frames."""
        fd, concat_path = tempfile.mkstemp(prefix="framelyx_",
                                           suffix=".ffconcat")
        os.close(fd)
        temp_files.append(concat_path)
        write_concat_list(files, spec.fps, concat_path)

        crf, speed = QUALITY_PRESETS[spec.quality]
        cmd = [
            self.ffmpeg_path, "-y", "-hide_banner", "-nostdin",
            "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_path,
            # Constant frame rate output at the user-selected FPS:
            "-vsync", "cfr", "-r", repr(float(spec.fps)),
            # Exactly one output frame per input frame (the repeated last
            # concat entry only exists to honour its duration):
            "-frames:v", str(len(files)),
            "-vf", build_scale_filter(spec, src_w, src_h),
            "-pix_fmt", "yuv420p",
            "-c:v", CODECS[spec.codec], "-crf", str(crf), "-preset", speed,
        ]
        if spec.codec == "h265":
            cmd += ["-x265-params", "log-level=error"]
        if to_mpegts:
            # Intermediate segment: MPEG-TS so segments can be stream-copied
            # together losslessly later.
            cmd += ["-f", "mpegts", out_path]
        else:
            if spec.codec == "h265":
                cmd += ["-tag:v", "hvc1"]
            cmd += ["-movflags", "+faststart",
                    "-metadata", "comment=Created with Frame Lyx",
                    "-progress", "pipe:1", "-nostats",
                    "-stats_period", "0.1",
                    out_path]

        # Progress is only parsed on the final (non-segment) pass; segment
        # passes report through the same callback after completion.
        self._cancelled = False
        if to_mpegts:
            code, err = self._run(cmd)
            if code != 0:
                return False, "FFmpeg error: " + (err or f"exit {code}")
            elapsed = time.monotonic() - started
            rate = (frame_offset + len(files)) / elapsed if elapsed > 0 else 1
            eta = (total - frame_offset - len(files)) / rate if rate > 0 else 0
            self._emit(progress_cb, frame_offset + len(files), total,
                       os.path.basename(files[-1]), eta)
            return True, out_path

        # Single-pass path with live progress parsing.
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            return False, f"Could not launch FFmpeg: {exc}"

        processed = 0
        for line in self._process.stdout:
            line = line.strip()
            if line.startswith("frame="):
                try:
                    processed = int(line.split("=", 1)[1])
                except ValueError:
                    pass
                elapsed = time.monotonic() - started
                if processed > 0 and elapsed > 0:
                    rate = (frame_offset + processed) / elapsed
                    eta = (total - frame_offset - processed) / rate
                    current = os.path.basename(
                        files[min(processed, len(files)) - 1])
                    self._emit(progress_cb, frame_offset + processed, total,
                               current, eta)

        stderr_out = self._process.stderr.read()
        code = self._process.wait()
        self._process = None
        if code == 0 and not self._cancelled:
            # The progress stream is sampled; guarantee a final 100% tick.
            self._emit(progress_cb, frame_offset + len(files), total,
                       os.path.basename(files[-1]), 0.0)
        if code != 0:
            detail = (stderr_out or "").strip().splitlines()
            detail = detail[-1] if detail else f"FFmpeg exited with code {code}."
            return False, "FFmpeg error: " + detail
        return True, out_path

    # -- public API ------------------------------------------------------------
    def render(self, files: List[str], spec: RenderSpec,
               progress_cb: Optional[Callable] = None) -> Tuple[bool, str]:
        """Encode *files* (natural order) into ``spec.output_path``.
        Returns ``(success, message)``."""
        error = spec.validate()
        if error:
            return False, error
        if not files:
            return False, "No image frames were found in the selected folder."
        if not os.path.isfile(self.ffmpeg_path):
            return False, ("FFmpeg was not found. Please install FFmpeg "
                           "and configure it in Settings.")

        total = len(files)
        started = time.monotonic()
        temp_files: List[str] = []
        out_dir = os.path.dirname(os.path.abspath(spec.output_path))
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            return False, f"Cannot create output folder: {exc}"

        try:
            runs = _contiguous_format_runs(files)
            if len(runs) == 1:
                # Fast path: homogeneous sequence, one single pass.
                self._cancelled = False
                ok, message = self._encode_run(
                    files, spec, spec.output_path, 0, total, started,
                    progress_cb, temp_files, to_mpegts=False,
                    src_w=1920, src_h=1080)
                if not ok:
                    self._discard_output(spec)
                    return False, message
            else:
                # Mixed-format sequence: encode contiguous format runs to
                # temp MPEG-TS segments, then losslessly concat them.
                done = 0
                segments: List[str] = []
                for run in runs:
                    if self._cancelled:
                        break
                    fd, seg = tempfile.mkstemp(prefix="framelyx_seg_",
                                               suffix=".ts")
                    os.close(fd)
                    temp_files.append(seg)
                    ok, message = self._encode_run(
                        run, spec, seg, done, total, started,
                        progress_cb, temp_files, to_mpegts=True,
                        src_w=1920, src_h=1080)
                    if not ok:
                        self._discard_output(spec)
                        return False, message
                    done += len(run)
                    segments.append(seg)

                if not self._cancelled:
                    fd, seg_list_path = tempfile.mkstemp(
                        prefix="framelyx_", suffix=".ffconcat")
                    os.close(fd)
                    temp_files.append(seg_list_path)
                    with open(seg_list_path, "w", encoding="utf-8") as fh:
                        fh.write("ffconcat version 1.0\n")
                        for seg in segments:
                            fh.write(f"file '{_concat_escape(seg)}'\n")
                    code, err = self._run([
                        self.ffmpeg_path, "-y", "-hide_banner", "-nostdin",
                        "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", seg_list_path, "-c", "copy",
                        "-movflags", "+faststart",
                        "-metadata", "comment=Created with Frame Lyx",
                        spec.output_path])
                    if code != 0:
                        self._discard_output(spec)
                        return False, "FFmpeg error: " + (err or f"exit {code}")
                    self._emit(progress_cb, total, total,
                               os.path.basename(files[-1]), 0.0)

            if self._cancelled:
                self._discard_output(spec)
                return False, "Rendering cancelled."
            if not os.path.exists(spec.output_path):
                return False, "FFmpeg finished but produced no output file."
            return True, spec.output_path
        finally:
            # Temp playlist/segment cleanup — always, even on exceptions.
            for path in temp_files:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

    @staticmethod
    def _discard_output(spec: RenderSpec) -> None:
        if os.path.exists(spec.output_path):
            try:
                os.remove(spec.output_path)
            except OSError:
                pass
