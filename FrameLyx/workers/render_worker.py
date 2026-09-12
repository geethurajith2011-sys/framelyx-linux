"""
Frame Lyx — workers.render_worker

Background QThread that drives :class:`core.video_renderer.VideoRenderer`.
The GUI thread stays fully responsive; progress, completion and errors
arrive as Qt signals.  Cancellation is cooperative and instant-feeling.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QThread, Signal

from core.video_renderer import RenderSpec, VideoRenderer


class RenderWorker(QThread):
    """Renders a frame sequence to MP4 off the GUI thread."""

    #: processed_frames, total_frames, current_filename, eta_seconds
    progress = Signal(int, int, str, float)
    #: success, message, output_path
    finished_render = Signal(bool, str, str)

    def __init__(self, ffmpeg_path: str, files: List[str], spec: RenderSpec,
                 parent=None) -> None:
        super().__init__(parent)
        self._files = list(files)
        self._spec = spec
        self._ffmpeg_path = ffmpeg_path
        self._renderer: VideoRenderer | None = None

    def run(self) -> None:  # executed on the worker thread
        self._renderer = VideoRenderer(self._ffmpeg_path)

        def on_progress(processed: int, total: int, current: str, eta: float):
            # queued-connection safe: emit only, never touch widgets here
            self.progress.emit(processed, total, current, eta)

        success, message = self._renderer.render(
            self._files, self._spec, progress_cb=on_progress)
        output = message if success else ""
        self.finished_render.emit(success, message, output)

    def cancel(self) -> None:
        if self._renderer is not None:
            self._renderer.cancel()
        elif self.isRunning():
            self.terminate()  # last resort before FFmpeg even started
