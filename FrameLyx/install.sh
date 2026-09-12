#!/usr/bin/env bash
# ============================================================================
#  Frame Lyx installer
#  "Join Image Frames · Create Videos"
#
#  Detects your Linux distribution, installs Python 3 + FFmpeg if needed,
#  copies the app into ~/.local/share/framelyx, creates an isolated Python
#  environment, and registers a launcher + desktop menu entry.
#
#  Usage:   chmod +x install.sh && ./install.sh
#  Options: --uninstall   remove Frame Lyx (asks before deleting settings)
#           --no-deps     skip system package installation (apt/dnf/pacman)
#  Support: Debian/Ubuntu, Arch, Fedora, openSUSE
# ============================================================================
set -Eeuo pipefail

APP_ID="framelyx"
APP_NAME="Frame Lyx"
APP_TAGLINE="Join Image Frames · Create Videos"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Target locations -------------------------------------------------------
REAL_USER="${SUDO_USER:-$USER}"
USER_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6 || true)"
USER_HOME="${USER_HOME:-$HOME}"
DATA_DIR="$USER_HOME/.local/share/$APP_ID"
APP_DIR="$DATA_DIR/app"
VENV_DIR="$DATA_DIR/venv"
BIN_DIR="$USER_HOME/.local/bin"
DESKTOP_DIR="$USER_HOME/.local/share/applications"
ICON_DIR="$USER_HOME/.local/share/icons/hicolor/512x512/apps"
CONFIG_DIR="$USER_HOME/.config/FrameLyx"

# --- Pretty output ----------------------------------------------------------
if [[ -t 1 ]]; then
  C0=$'\e[0m'; CB=$'\e[1m'
  CP=$'\e[38;5;213m'   # magenta   (Frame Lyx gradient accent)
  CT=$'\e[38;5;80m'    # cyan      (Frame Lyx secondary)
  CR=$'\e[38;5;203m'   # error red
  CY=$'\e[38;5;220m'   # warning yellow
  CG=$'\e[38;5;245m'   # muted grey
else
  C0=""; CB=""; CP=""; CT=""; CR=""; CY=""; CG=""
fi

banner() {
  printf '%s' "$CP"
  cat <<'EOF'

   ███████╗██████╗  █████╗ ███╗   ███╗███████╗    ██╗  ██╗   ██╗██╗  ██╗
   ██╔════╝██╔══██╗██╔══██╗████╗ ████║██╔════╝    ██║  ╚██╗ ██╔╝╚██╗██╔╝
   █████╗  ██████╔╝███████║██╔████╔██║███████╗    ██║   ╚███╔╝  ╚███╔╝
   ██╔══╝  ██╔══██╗██╔══██║██║╚██╔╝██║██╔══██║    ██║   ██╔██╗   ██╔██╗
   ██║     ██║  ██║██║  ██║██║ ╚═╝ ██║██║  ██║    ███████╔╝ ██╗██╔╝ ██╗
   ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝    ╚══════╝  ╚═╝╚═╝  ╚═╝

              Join Image Frames · Create Videos
EOF
  printf '%s\n' "$C0"
}

info()  { printf '%s\n' "${CT}[ info ]${C0} $*"; }
warn()  { printf '%s\n' "${CY}[ warn ]${C0} $*"; }
error() { printf '%s\n' "${CR}[error]${C0} $*" >&2; }
die()   { error "$*"; printf '%s\n' "${CG}Install aborted. Fix the problem above and re-run.${C0}" >&2; exit 1; }
step()  { printf '\n%s\n' "${CB}${CP}==> $*${C0}"; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

on_error() {
  error "Install failed at line $1 (exit code $2)."
  error "Read the messages above, fix the issue, then re-run ./install.sh"
}
trap 'on_error $LINENO $?' ERR

# --- Distro detection -------------------------------------------------------
PKG_MGR=""
DISTRO_ID="unknown"

detect_distro() {
  step "Detecting Linux distribution"
  if [[ ! -r /etc/os-release ]]; then
    die "/etc/os-release not found — cannot detect your distribution."
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO_ID="${ID:-unknown}"
  local like="${ID_LIKE:-}"
  case "$DISTRO_ID|$like" in
    debian*|*debian*|*ubuntu*|*mint*|*pop*|*elementary*|*zorin*|*kali*) PKG_MGR="apt" ;;
    arch*|*arch*|*manjaro*|*endeavouros*|*garuda*|*cachyos*)            PKG_MGR="pacman" ;;
    fedora*|*fedora*|*rhel*|*centos*|*rocky*|*alma*|*nobara*)           PKG_MGR="dnf" ;;
    opensuse*|*suse*)                                                    PKG_MGR="zypper" ;;
    *) PKG_MGR="" ;;
  esac
  info "Detected: ${DISTRO_ID} (package manager: ${PKG_MGR:-none})"
}

pkg_install() {
  # pkg_install <package...> — best-effort system package install via sudo.
  local pkgs=("$@")
  case "$PKG_MGR" in
    apt)    sudo apt-get update -y && sudo apt-get install -y "${pkgs[@]}" ;;
    dnf)    sudo dnf install -y "${pkgs[@]}" ;;
    pacman) sudo pacman -S --needed --noconfirm "${pkgs[@]}" ;;
    zypper) sudo zypper install -y "${pkgs[@]}" ;;
    *)      return 1 ;;
  esac
}

python_pkgs() {
  case "$PKG_MGR" in
    apt)    echo "python3 python3-venv python3-pip" ;;
    dnf)    echo "python3 python3-pip" ;;
    pacman) echo "python python-pip" ;;
    zypper) echo "python3 python3-pip" ;;
    *)      echo "" ;;
  esac
}

# --- System dependencies ----------------------------------------------------
install_system_deps() {
  step "Checking system dependencies"

  if ! need_cmd python3; then
    if [[ -n "$PKG_MGR" ]]; then
      info "Installing Python 3…"
      pkg_install $(python_pkgs)
    else
      die "python3 not found and your distribution is unsupported. Install Python 3.9+ manually."
    fi
  fi
  info "Python: $(python3 --version)"

  if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
    if [[ "$PKG_MGR" == "apt" ]]; then
      warn "The venv module needs python3-venv on Debian/Ubuntu — installing it."
      pkg_install python3-venv
    else
      warn "python3 venv/ensurepip appears unavailable; creating the venv may fail."
    fi
  fi

  if need_cmd ffmpeg; then
    info "FFmpeg found: $(ffmpeg -version 2>/dev/null | head -n1 | cut -d' ' -f1-3)"
  elif [[ -n "$PKG_MGR" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "FFmpeg is required for rendering. Install it now with $PKG_MGR? [Y/n] " ans
      [[ "${ans,,}" == "n" ]] && { warn "Skipping FFmpeg — rendering will not work until it is installed."; return 0; }
    fi
    info "Installing FFmpeg…"
    pkg_install ffmpeg || warn "FFmpeg installation failed — install it manually, then re-run."
  else
    warn "FFmpeg not found and no supported package manager. Rendering needs FFmpeg — install it manually."
  fi
}

# --- Application files ------------------------------------------------------
install_app_files() {
  step "Installing application files → $APP_DIR"
  mkdir -p "$APP_DIR"
  # Copy the source tree, excluding caches, venvs and VCS metadata.
  (cd "$SRC_DIR" && tar -cf - \
      --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='.venv' --exclude='.git' \
      --exclude='install.sh' .) | tar -xf - -C "$APP_DIR"
  info "Source copied ($(du -sh "$APP_DIR" | cut -f1))."
}

# --- Python environment -----------------------------------------------------
setup_venv() {
  step "Creating Python virtual environment → $VENV_DIR"
  rm -rf "$VENV_DIR"
  python3 -m venv --system-site-packages "$VENV_DIR" \
    || die "Could not create the virtual environment (is python3-venv installed?)."

  if "$VENV_DIR/bin/python" -c "import PySide6" >/dev/null 2>&1; then
    info "PySide6 already available — skipping pip download."
  else
    info "Installing Python dependencies (PySide6)…"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" \
      || die "pip install failed — check your network connection and re-run."
  fi
  info "Environment ready (PySide6 import OK)."
}

# --- Launcher + desktop entry ------------------------------------------------
install_launcher() {
  step "Creating launcher ($BIN_DIR/$APP_ID) and desktop entry"
  mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

  cat > "$BIN_DIR/$APP_ID" <<EOF
#!/usr/bin/env bash
# Frame Lyx launcher — runs the GUI inside its dedicated virtual environment.
exec "$VENV_DIR/bin/python" "$APP_DIR/main.py" "\$@"
EOF
  chmod +x "$BIN_DIR/$APP_ID"

  # Icon into the hicolor scheme so every desktop environment finds it.
  if [[ -f "$APP_DIR/assets/icons/framelyx.png" ]]; then
    mkdir -p "$ICON_DIR"
    cp -f "$APP_DIR/assets/icons/framelyx.png" "$ICON_DIR/$APP_ID.png"
  fi

  cat > "$DESKTOP_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Frame Lyx
GenericName=Frame Sequence to Video Studio
Comment=$APP_TAGLINE
Exec=$BIN_DIR/$APP_ID
TryExec=$BIN_DIR/$APP_ID
Icon=$ICON_DIR/$APP_ID.png
Terminal=false
Categories=AudioVideo;Video;Graphics;Utility;
Keywords=frames;sequence;video;mp4;ffmpeg;h264;h265;animation;
StartupNotify=true
StartupWMClass=Frame Lyx
EOF

  if need_cmd update-desktop-database; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  fi
  if need_cmd gtk-update-icon-cache; then
    gtk-update-icon-cache -tf "$USER_HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
  fi

  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not in your PATH. Add it:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
  esac
  info "Launcher and desktop entry created."
}

# --- Uninstall ----------------------------------------------------------------
uninstall() {
  step "Removing Frame Lyx"
  local removed=0
  for target in "$DATA_DIR" "$BIN_DIR/$APP_ID" \
                "$DESKTOP_DIR/$APP_ID.desktop" "$ICON_DIR/$APP_ID.png"; do
    if [[ -e "$target" ]]; then
      rm -rf "$target"
      info "Removed: $target"
      removed=1
    fi
  done
  if [[ -d "$CONFIG_DIR" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "Also delete your settings and recent projects ($CONFIG_DIR)? [y/N] " ans
      if [[ "${ans,,}" == "y" ]]; then rm -rf "$CONFIG_DIR"; info "Settings removed."; fi
    else
      warn "Settings kept: $CONFIG_DIR (delete manually if desired)."
    fi
  fi
  [[ $removed -eq 1 ]] && info "$APP_NAME has been uninstalled." \
                        || warn "Nothing found to uninstall."
}

# --- Summary -------------------------------------------------------------------
print_success() {
  banner
  printf '%s\n' "${CB}${CP}  $APP_NAME was installed successfully!${C0}"
  printf '%s\n' "${CT}  $APP_TAGLINE${C0}"
  printf '\n%s\n' "${CB}  What was installed:${C0}"
  printf '%s\n' "${CG}   • App files        → $APP_DIR${C0}"
  printf '%s\n' "${CG}   • Python venv      → $VENV_DIR${C0}"
  printf '%s\n' "${CG}   • Launcher         → $BIN_DIR/$APP_ID${C0}"
  printf '%s\n' "${CG}   • Desktop entry    → $DESKTOP_DIR/$APP_ID.desktop${C0}"
  printf '\n%s\n' "${CB}  Get started:${C0}"
  printf '%s\n' "${CP}     framelyx${C0}     ${CG}# or launch “Frame Lyx” from your app menu${C0}"
  printf '\n%s\n' "${CG}  Projects: *.framelyx  ·  Config: ~/.config/FrameLyx/  ·  Data: $DATA_DIR${C0}"
  printf '%s\n' ""
}

usage() {
  cat <<EOF
$APP_NAME installer — $APP_TAGLINE

Usage: ./install.sh [option]
  (no option)   install $APP_NAME
  --uninstall   remove $APP_NAME
  --no-deps     skip system package installation (Python/FFmpeg)
  --help        show this help
EOF
}

main() {
  banner
  case "${1:-}" in
    --uninstall) uninstall; exit 0 ;;
    --help|-h)   usage; exit 0 ;;
    --no-deps)   detect_distro; install_app_files; setup_venv; install_launcher; print_success ;;
    "")          detect_distro; install_system_deps; install_app_files; setup_venv; install_launcher; print_success ;;
    *)           die "Unknown option: $1 (see ./install.sh --help)" ;;
  esac
}

main "$@"
