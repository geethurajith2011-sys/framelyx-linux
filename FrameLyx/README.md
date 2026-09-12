# Frame Lyx

> Join Image Frames · Create Videos

Frame Lyx turns large image frame sequences — up to **~20,000 frames** —
into high-quality **MP4 videos** using FFmpeg. Built for animation renders,
Blender frame sequences, AI-generated video frames, game cinematics and any
image-to-video workflow.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Qt](https://img.shields.io/badge/GUI-PySide6-green) ![Engine](https://img.shields.io/badge/Engine-FFmpeg-orange)

---

## Features

- **Frame folder detection** with true *natural numerical ordering*
  (`frame_2.png` before `frame_10.png`) even with inconsistent names
  (`Untitled Project 1.png`, `frame_0001.png`, `render001.jpg`, mixed).
- **Formats:** PNG, JPG, JPEG, WEBP, BMP.
- **Real FFmpeg encoding** — frames are streamed through an ffconcat list;
  no image is ever fully loaded into Python, no files are duplicated, and
  temporary files are always cleaned up.
- **H.264 / H.265 (HEVC)** codecs with **Draft / Standard / High / Ultra**
  quality presets (CRF based).
- **Resolution control:** Original, 720p, 1080p, 1440p, 4K, Custom — with
  professional aspect handling: **Stretch**, **Fit (letterbox)**, **Crop**.
- **Frame rates:** 12/15/24/25/30/48/50/60 FPS or any custom value; duration
  updates live (`Duration = Frames ÷ FPS`).
- **Project system** (`.framelyx` JSON files): save, reopen, recent
  projects, 30-second **autosave** and **crash recovery**.
- **Virtualized timeline** — thumbnails are decoded lazily at thumbnail size
  on a background thread with a bounded LRU cache. RAM stays flat.
- **Playback preview** that respects the selected FPS (play/pause/stop,
  next/previous, first/last, click-to-seek).
- **Live render progress**: progress bar, %, frames processed, current frame
  name, ETA, and cancellation — the GUI never freezes (renders run on a
  worker thread; FFmpeg is a subprocess).
- **Sequence validation**: missing frame detection, duplicate detection,
  mixed-resolution warnings and corrupted-image reports — all computed from
  file names and image headers only.
- **Dark / Light themes** with a professional dark default.
- Drag & drop folders or loose images, keyboard shortcuts, render history,
  estimated output file size, open output video/folder after rendering.

---

## Installation

### Linux — one-command install

```bash
chmod +x install.sh && ./install.sh
```

The installer detects your distribution (Debian/Ubuntu, Arch, Fedora,
openSUSE), installs Python 3 and FFmpeg if missing, copies the app to
`~/.local/share/framelyx`, creates an isolated Python environment, and
registers a `framelyx` launcher plus an app-menu entry.
Run `./install.sh --uninstall` to remove it again
(`--no-deps` skips system package installation).

### 1. Python 3.9+ (manual setup, or Windows)

- **Linux:** `sudo apt install python3 python3-pip` (or your distro equivalent)
- **Windows:** <https://www.python.org/downloads/> (tick *Add to PATH*)

### 2. FFmpeg (required for rendering)

- **Linux:**
  ```bash
  sudo apt install ffmpeg        # Debian/Ubuntu
  sudo dnf install ffmpeg        # Fedora
  sudo pacman -S ffmpeg          # Arch
  ```
- **Windows:** download a build from <https://www.gyan.dev/ffmpeg/builds/>
  or <https://github.com/BtbN/FFmpeg-Builds/releases>, extract it, and either
  add `bin` to your PATH **or** point Frame Lyx to `ffmpeg.exe` in
  *Settings* (the app can also auto-detect common locations).

Verify: `ffmpeg -version`

### 3. Python dependencies

```bash
pip install -r requirements.txt      # installs PySide6
```

---

## Running

```bash
python main.py
```

---

## Project structure

```text
FrameLyx/
├── main.py                     # entry point
├── requirements.txt
├── tools/
│   └── make_logo.py            # regenerates brand assets (SVG -> PNG)
├── core/
│   ├── frame_manager.py        # scanning, natural sort, validation
│   ├── project_manager.py      # .framelyx JSON projects, recents, autosave
│   └── video_renderer.py       # real FFmpeg pipeline + progress parsing
├── workers/
│   └── render_worker.py        # QThread render worker (cancellation)
├── ui/
│   ├── main_window.py          # studio window, pages, playback, drag&drop
│   ├── timeline.py             # virtualized thumbnail timeline + transport
│   ├── export_panel.py         # export summary/settings + CREATE VIDEO
│   ├── welcome_screen.py       # branding + drop area + recents
│   ├── render_dialog.py        # progress window (ETA, cancel)
│   ├── settings_dialog.py      # FFmpeg path + theme
│   └── theme.py                # dark/light QSS themes (Frame Lyx brand)
└── assets/icons/               # framelyx.png app icon + logo mark + SVGs
```

---

## Workflow

1. **Create New Project** (or drag a frame folder onto the window).
2. Frame Lyx scans the folder, sorts frames naturally and validates them.
3. Pick the **FPS**, codec, quality, resolution and aspect mode.
4. Scrub the timeline / press **Space** to preview the animation.
5. Hit **▶ CREATE VIDEO** — watch live progress, or cancel at any time.
6. Save the project (`.framelyx`) to keep all settings for later.
   (Legacy `.frameforger` files from Frame Forger open transparently.)

### Keyboard shortcuts

| Key | Action |
|---|---|
| Space | Play / Pause |
| ← / → | Previous / Next frame |
| Home / End | First / Last frame |
| Ctrl+N / Ctrl+O / Ctrl+S | New / Open / Save project |

---

## Performance notes

- Scanning uses only `os.listdir` + sorting: 20,000 frames scan instantly.
- Resolution/corruption checks sample image headers, never decode everything.
- The preview decodes a single frame at display resolution at a time.
- Timeline thumbnails stream through one background loader with an LRU cache.
- Rendering pipes filenames (not pixels) to FFmpeg via a temp ffconcat file
  that is deleted afterwards — RAM usage is essentially constant.
