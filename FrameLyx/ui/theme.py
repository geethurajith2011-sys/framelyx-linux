"""
Frame Lyx — ui.theme

Palettes and application-wide QSS built around the Frame Lyx brand
(deep navy surfaces with cyan -> magenta gradient accents, from the
logo).  Widgets opt into variants via dynamic properties:
``setProperty("cls", "primary")`` etc.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Brand gradient (from the Frame Lyx logo): cyan -> magenta.
BRAND_GRADIENT = ("qlineargradient(x1:0,y1:0,x2:1,y2:0, "
                  "stop:0 #29d3ff, stop:1 #c438f5)")
BRAND_GRADIENT_HOVER = ("qlineargradient(x1:0,y1:0,x2:1,y2:0, "
                        "stop:0 #56e0ff, stop:1 #d55cff)")

DARK = {
    "bg":       "#0d1022",
    "panel":    "#151a33",
    "panel2":   "#1c2342",
    "border":   "#2b3358",
    "text":     "#e9edff",
    "muted":    "#8e97c2",
    "accent":   "#29d3ff",
    "accent_h": "#56e0ff",
    "accent2":  "#7c5cff",
    "danger":   "#f0566a",
    "ok":       "#2fd48f",
    "sel":      "#223055",
}

LIGHT = {
    "bg":       "#f1f3fa",
    "panel":    "#ffffff",
    "panel2":   "#eef1fa",
    "border":   "#d9def0",
    "text":     "#141a33",
    "muted":    "#5b6488",
    "accent":   "#0ea5e9",
    "accent_h": "#29b8f7",
    "accent2":  "#7c3aed",
    "danger":   "#d5394d",
    "ok":       "#17966a",
    "sel":      "#dce8fd",
}


def build_stylesheet(theme: str = "dark") -> str:
    c = DARK if theme == "dark" else LIGHT
    return f"""
* {{ outline: none; }}
QWidget {{
    background: {c['bg']}; color: {c['text']};
    font-family: 'Segoe UI','Ubuntu','Cantarell',sans-serif; font-size: 13px;
}}
QLabel {{ background: transparent; }}
QLabel[cls="h1"] {{ font-size: 26px; font-weight: 700; }}
QLabel[cls="h2"] {{ font-size: 16px; font-weight: 600; }}
QLabel[cls="muted"] {{ color: {c['muted']}; }}
QLabel[cls="accent"] {{ color: {c['accent']}; font-weight: 600; }}
QLabel[cls="logo"] {{
    font-size: 19px; font-weight: 800; letter-spacing: 2px;
    color: {c['text']};
}}
QLabel[cls="logoAccent"] {{
    font-size: 19px; font-weight: 800; letter-spacing: 2px;
    color: {c['accent']};
}}
QLabel[cls="panelTitle"] {{
    font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
    color: {c['muted']};
}}

QFrame[cls="panel"], QGroupBox {{
    background: {c['panel']};
    border: 1px solid {c['border']};
    border-radius: 10px;
}}
QFrame[cls="topbar"] {{
    background: {c['panel']}; border: none;
    border-bottom: 1px solid {c['border']};
}}
QFrame[cls="sidebar"] {{
    background: {c['panel']}; border: none;
    border-right: 1px solid {c['border']};
}}
QFrame[cls="viewer"] {{ background: {c['bg']}; border: 1px solid {c['border']}; border-radius: 10px; }}

QPushButton {{
    background: {c['panel2']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 7px;
    padding: 7px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {c['sel']}; border-color: {c['accent2']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['panel']}; }}
QPushButton[cls="primary"] {{
    background: {BRAND_GRADIENT}; color: #ffffff; border: none; font-weight: 800;
}}
QPushButton[cls="primary"]:hover {{ background: {BRAND_GRADIENT_HOVER}; }}
QPushButton[cls="primary"]:pressed {{ background: {BRAND_GRADIENT}; }}
QPushButton[cls="primary"]:disabled {{ background: {c['panel2']}; color: {c['muted']}; }}
QPushButton[cls="danger"] {{
    background: transparent; color: {c['danger']};
    border: 1px solid {c['danger']};
}}
QPushButton[cls="danger"]:hover {{ background: {c['danger']}; color: #ffffff; }}
QPushButton[cls="nav"] {{
    background: transparent; border: none; border-radius: 8px;
    text-align: left; padding: 10px 14px; font-size: 13.5px; color: {c['muted']};
}}
QPushButton[cls="nav"]:hover {{ background: {c['panel2']}; color: {c['text']}; }}
QPushButton[cls="nav"]:checked {{
    background: {c['sel']}; color: {c['text']};
    border-left: 3px solid {c['accent']};
}}
QPushButton[cls="tool"] {{ padding: 6px 12px; font-size: 15px; }}
QPushButton[cls="flat"] {{ background: transparent; border: none; color: {c['accent2']}; }}
QPushButton[cls="flat"]:hover {{ color: {c['accent']}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c['bg']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 7px; padding: 6px 10px;
    selection-background-color: {c['accent2']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {c['accent2']};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {c['panel']}; border: 1px solid {c['border']};
    selection-background-color: {c['sel']};
}}

QProgressBar {{
    background: {c['bg']}; border: 1px solid {c['border']};
    border-radius: 8px; height: 18px; text-align: center;
    color: {c['text']}; font-weight: 700;
}}
QProgressBar::chunk {{
    background: {BRAND_GRADIENT};
    border-radius: 7px;
}}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {c['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 5px; background: {c['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -6px 0;
    background: {c['accent']}; border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {BRAND_GRADIENT}; border-radius: 2px;
}}

QListWidget {{
    background: {c['panel']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 4px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {c['sel']}; }}
QToolTip {{
    background: {c['panel']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 6px; padding: 6px;
}}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 4px;
    border: 1px solid {c['border']}; background: {c['bg']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['sel']}; }}
QDialog {{ background: {c['bg']}; }}
"""


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    """Apply stylesheet + palette so native dialogs match too."""
    c = DARK if theme == "dark" else LIGHT
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["bg"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["panel"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["panel2"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.Highlight, QColor(c["accent2"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(c["panel"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["text"]))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(theme))
