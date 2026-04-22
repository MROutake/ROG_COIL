"""
Wissenschaftliches Dark-Theme fuer Qt + matplotlib.

Palette orientiert an GitHub Dark / VS Code Dark+:
 - Hintergrund  #1e1f22 / Panel #252629
 - Textfarbe    #e6e6e6
 - Accent       #4da3ff  (kontrastreiches Blau)
 - Erfolg       #4ec9a0
 - Warnung      #e6b45a
"""

from __future__ import annotations

import matplotlib as _mpl
from cycler import cycler as _cycler


# Farb-Konstanten (auch aus anderen Widgets importierbar) -----------------
BG_WINDOW   = "#1e1f22"
BG_PANEL    = "#252629"
BG_ELEVATED = "#2d2f34"
BG_INPUT    = "#1a1b1e"
BORDER      = "#3a3d42"
BORDER_HI   = "#4a4d52"
TEXT        = "#e6e6e6"
TEXT_DIM    = "#9aa0a6"
TEXT_HINT   = "#6d7278"
ACCENT      = "#4da3ff"
ACCENT_HI   = "#6cb4ff"
ACCENT_DIM  = "#2a6bb8"
SUCCESS     = "#4ec9a0"
WARNING     = "#e6b45a"
ERROR       = "#f07178"
GRID        = "#3a3d42"

# Rollenfarben fuer Board-Viewer (dark-tauglich)
ROLE_WINDING    = "#ff5b5b"   # rot
ROLE_RETURN     = "#4da3ff"   # blau
ROLE_CONNECTION = "#9aa0a6"   # grau


QSS = f"""
* {{
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
    color: {TEXT};
}}

QMainWindow, QDialog, QWidget {{
    background-color: {BG_WINDOW};
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG_PANEL};
    top: -1px;
}}
QTabBar::tab {{
    background: {BG_WINDOW};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 8px 18px;
    margin-right: 2px;
    color: {TEXT_DIM};
    min-width: 140px;
}}
QTabBar::tab:selected {{
    background: {BG_PANEL};
    color: {TEXT};
    border-top: 3px solid {ACCENT};
    padding-top: 6px;
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {BG_ELEVATED};
    color: {TEXT};
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    background: {BG_PANEL};
    padding-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_DIM};
    font-weight: 600;
}}

QPushButton {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 14px;
    min-height: 22px;
    color: {TEXT};
}}
QPushButton:hover   {{ background: {BG_PANEL}; border-color: {BORDER_HI}; }}
QPushButton:pressed {{ background: {BG_WINDOW}; }}
QPushButton:disabled {{ color: {TEXT_HINT}; background: {BG_PANEL}; }}

QPushButton[accent="true"] {{
    background: {ACCENT}; color: #0b1320;
    border-color: {ACCENT}; font-weight: 600;
}}
QPushButton[accent="true"]:hover   {{ background: {ACCENT_HI}; }}
QPushButton[accent="true"]:pressed {{ background: {ACCENT_DIM}; }}

QPushButton[role="W"] {{ background: {ROLE_WINDING};    color: #ffffff; border-color: {ROLE_WINDING};    font-weight: 600; }}
QPushButton[role="R"] {{ background: {ROLE_RETURN};     color: #ffffff; border-color: {ROLE_RETURN};     font-weight: 600; }}
QPushButton[role="C"] {{ background: {ROLE_CONNECTION}; color: #111111; border-color: {ROLE_CONNECTION}; font-weight: 600; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #0b1320;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox QAbstractItemView {{
    background: {BG_INPUT}; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: #0b1320;
    border: 1px solid {BORDER};
}}

QTableView, QTableWidget, QTreeView, QTreeWidget, QListView, QListWidget {{
    background: {BG_PANEL};
    border: 1px solid {BORDER};
    gridline-color: {BORDER};
    selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT};
    alternate-background-color: {BG_ELEVATED};
}}
QHeaderView::section {{
    background: {BG_ELEVATED}; color: {TEXT_DIM};
    padding: 6px 8px; border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}

QStatusBar {{
    background: {BG_ELEVATED}; color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}
QStatusBar QLabel {{ color: {TEXT_DIM}; }}

QMenuBar {{
    background: {BG_ELEVATED}; color: {TEXT};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item:selected {{ background: {BG_PANEL}; }}
QMenu {{ background: {BG_PANEL}; color: {TEXT}; border: 1px solid {BORDER}; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}

QSplitter::handle            {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 4px; }}
QSplitter::handle:vertical   {{ height: 4px; }}

QToolBar {{
    background: {BG_WINDOW}; border: none;
    spacing: 4px; padding: 4px; color: {TEXT};
}}
QToolButton {{
    background: {BG_ELEVATED}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 4px;
    padding: 3px 6px;
}}
QToolButton:hover   {{ background: {BG_PANEL}; border-color: {BORDER_HI}; }}
QToolButton:checked {{ background: {ACCENT_DIM}; border-color: {ACCENT}; }}

QProgressBar {{
    border: 1px solid {BORDER}; border-radius: 4px;
    background: {BG_INPUT}; text-align: center; color: {TEXT};
}}
QProgressBar::chunk {{ background-color: {ACCENT}; }}

QScrollBar:vertical {{ background: {BG_WINDOW}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORDER_HI}; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{ background: {BG_WINDOW}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_HI}; border-radius: 4px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QCheckBox, QRadioButton {{ color: {TEXT}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER_HI};
    background: {BG_INPUT};
    border-radius: 3px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}

QLabel#sectionTitle {{
    font-size: 13pt; font-weight: 600; color: {TEXT}; padding: 6px 0;
}}
QLabel#hint     {{ color: {TEXT_HINT}; font-size: 9pt; }}
QLabel#value    {{
    font-family: "Consolas", "Courier New", monospace;
    color: {ACCENT_HI}; font-weight: 600;
}}
QLabel#kpiLabel {{ color: {TEXT_DIM}; font-size: 9pt; }}
QLabel#kpiValue {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 15pt; font-weight: 600; color: {ACCENT_HI};
}}
QLabel#kpiUnit  {{ color: {TEXT_DIM}; font-size: 10pt; }}

QFrame#kpiCard {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
"""


def _apply_matplotlib_dark() -> None:
    """Setzt globale matplotlib-rcParams passend zur Dark-Palette."""
    _mpl.rcParams.update({
        "figure.facecolor":    BG_PANEL,
        "axes.facecolor":      BG_PANEL,
        "savefig.facecolor":   BG_PANEL,
        "axes.edgecolor":      BORDER_HI,
        "axes.labelcolor":     TEXT,
        "axes.titlecolor":     TEXT,
        "xtick.color":         TEXT_DIM,
        "ytick.color":         TEXT_DIM,
        "text.color":          TEXT,
        "grid.color":          GRID,
        "grid.linestyle":      "-",
        "grid.alpha":          0.4,
        "legend.facecolor":    BG_ELEVATED,
        "legend.edgecolor":    BORDER,
        "legend.labelcolor":   TEXT,
        "axes.prop_cycle":     _cycler(color=[
            "#4da3ff", "#ff7f50", "#4ec9a0", "#c586c0",
            "#e6b45a", "#f07178", "#9cdcfe", "#dcdcaa",
        ]),
        "font.family":         "DejaVu Sans",
    })


def apply_theme(app) -> None:  # type: ignore[no-untyped-def]
    """Wendet Stylesheet + matplotlib-Dark-rcParams an."""
    app.setStyleSheet(QSS)
    _apply_matplotlib_dark()
