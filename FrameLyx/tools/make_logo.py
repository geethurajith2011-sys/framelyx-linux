#!/usr/bin/env python3
"""
Frame Lyx — brand asset generator.

Recreates the Frame Lyx logo (stacked photo frames -> gradient arrow ->
film frame with play button) as vector SVG and renders the PNG assets
used by the application:

    assets/icons/framelyx.png        512px app icon (dark navy rounded tile)
    assets/icons/framelyx_mark.png   transparent mark for UI embedding

Run:  python tools/make_logo.py
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, os.pardir, "assets", "icons"))

# Brand palette (from the logo): deep navy base, cyan -> blue -> magenta.
NAVY = "#0b0e1c"
CYAN = "#29d3ff"
BLUE = "#3b7bff"
MAGENTA = "#c438f5"

DEFS = f"""
  <defs>
    <linearGradient id="gback" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="{MAGENTA}"/>
      <stop offset="1" stop-color="{BLUE}"/>
    </linearGradient>
    <linearGradient id="gframe" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="{BLUE}"/>
      <stop offset="1" stop-color="{CYAN}"/>
    </linearGradient>
    <linearGradient id="gimg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#5cc4ff"/>
      <stop offset="1" stop-color="#2456e8"/>
    </linearGradient>
    <linearGradient id="gplay" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{CYAN}"/>
      <stop offset="0.55" stop-color="#7c5cff"/>
      <stop offset="1" stop-color="{MAGENTA}"/>
    </linearGradient>
  </defs>
"""

# The logo mark, drawn on a 512x512 canvas.
MARK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  {DEFS}
  <!-- stacked photo frames -->
  <rect x="46" y="208" width="152" height="114" rx="14" fill="url(#gback)"/>
  <rect x="84" y="174" width="164" height="126" rx="14" fill="url(#gframe)"/>
  <rect x="126" y="134" width="186" height="150" rx="16" fill="#eef7ff"/>
  <rect x="141" y="149" width="156" height="120" rx="8" fill="url(#gimg)"/>
  <circle cx="264" cy="184" r="15" fill="#eef7ff"/>
  <path d="M141 269 L207 203 L243 239 L269 213 L297 241 L297 261 Q297 269 289 269 Z"
        fill="#17359e"/>
  <path d="M141 269 L207 203 L243 239 L212 269 Z" fill="#2b5cf0"/>

  <!-- conversion arrow -->
  <path d="M186 380 Q272 404 330 328" stroke="url(#gplay)" stroke-width="22"
        fill="none" stroke-linecap="round"/>
  <path d="M300 296 L354 302 L322 352 Z" fill="url(#gplay)"/>

  <!-- film frame with play button -->
  <rect x="328" y="138" width="154" height="198" rx="20" fill="url(#gplay)"/>
  <rect x="342" y="152" width="126" height="170" rx="12" fill="{NAVY}"/>
  <g fill="#9fe6ff" opacity="0.92">
    <rect x="350" y="172" width="14" height="18" rx="4"/>
    <rect x="350" y="216" width="14" height="18" rx="4"/>
    <rect x="350" y="260" width="14" height="18" rx="4"/>
    <rect x="350" y="304" width="14" height="18" rx="4"/>
    <rect x="446" y="172" width="14" height="18" rx="4"/>
    <rect x="446" y="216" width="14" height="18" rx="4"/>
    <rect x="446" y="260" width="14" height="18" rx="4"/>
    <rect x="446" y="304" width="14" height="18" rx="4"/>
  </g>
  <path d="M386 204 L452 237 L386 270 Z" fill="#f4f8ff"/>
</svg>
"""

# Square app icon: the mark on a dark rounded tile.
ICON = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0d1124"/>
      <stop offset="1" stop-color="#080a16"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="496" height="496" rx="108" fill="url(#tile)"/>
  {MARK.replace('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">', '')
       .replace('</svg>', '')}
</svg>
"""


def render(svg_text: str, out_png: str, size: int = 512) -> None:
    renderer = QSvgRenderer(bytes(svg_text, "utf-8"))
    if not renderer.isValid():
        raise RuntimeError(f"invalid SVG for {out_png}")
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    image.save(out_png)
    print("wrote", out_png)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    render(ICON, os.path.join(OUT, "framelyx.png"), 512)
    render(MARK, os.path.join(OUT, "framelyx_mark.png"), 512)
    # Keep the vector sources next to the PNGs for future edits.
    with open(os.path.join(OUT, "framelyx.svg"), "w", encoding="utf-8") as fh:
        fh.write(MARK)
    with open(os.path.join(OUT, "framelyx_icon.svg"), "w", encoding="utf-8") as fh:
        fh.write(ICON)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
