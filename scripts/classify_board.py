#!/usr/bin/env python
"""
classify_board.py – Interaktiver manueller Klassifikations-Editor für PCB Rogowski-Spulen.

Workflow
--------
1. Erster Aufruf (noch keine YAML vorhanden)::

      python scripts/classify_board.py data_samples/gerber/Desgin_03

   Alle Segmente erscheinen als „unklassifiziert" (dunkelgrau).
   Segmente per Klick auswählen, Rolle per W / C / R zuweisen, mit Ctrl+S speichern.
   Die YAML wird unter ``<gerber_dir>/classification_draft.yaml`` gespeichert.

2. Folgeaufruf (YAML vorhanden)::

      python scripts/classify_board.py data_samples/gerber/Desgin_03

   Bereits manuell zugewiesene Segmente werden geladen.
   Noch nicht zugewiesene Segmente werden per Topologie-Gap-Filling belegt:

   * Gleiche Nachbarn beiderseits  → deren gemeinsame Rolle
   * Unterschiedliche Nachbarn     → Rolle des nächsten Vorgängers

   Die gespeicherte YAML enthält alle Einträge (manuell + Gap-Fill).

Steuerung
---------
  Linksklick              Segment auswählen / abwählen
  Shift+Klick             Segment zur Auswahl hinzufügen / entfernen
  W                       Ausgewählte Segmente → WINDING
  C                       Ausgewählte Segmente → CONNECTION
  R                       Ausgewählte Segmente → RETURN
  + / =                   Sigma → +1
  -                       Sigma → −1
  V                       Ansichtsmodus wechseln (Rolle / Sigma)
  Strg+S                  Klassifikation speichern
  Strg+Z                  Rückgängig
  Escape                  Auswahl aufheben

Verwendung
----------
    python scripts/classify_board.py data_samples/gerber/Desgin_03
    python scripts/classify_board.py data_samples/gerber/Desgin_03 \\
        --classification pfad/zu/anderer.yaml
    python scripts/classify_board.py data_samples/gerber/Desgin_03 \\
        --output meine_klassifikation.yaml
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QGroupBox, QCheckBox, QPushButton, QLabel, QRadioButton,
    QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence, QFont

from pcb_rogowski.domain.board.models import Board, LineFeature
from pcb_rogowski.domain.trace.classifier import (
    ClassificationEntry,
    ClassificationSpec,
    TopologyGapFiller,
)
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader

# ---------------------------------------------------------------------------
# Farbdefinitionen
# ---------------------------------------------------------------------------

_ROLE_COLORS: dict[str, str] = {
    "winding":    "#00e676",   # grün
    "connection": "#546e7a",   # grau-blau
    "return":     "#ef5350",   # rot
}
_SIGMA_COLORS: dict[int, str] = {
    1:  "#42a5f5",   # blau
    -1: "#ff7043",   # orange
    0:  "#546e7a",   # grau
}
_UNCLASSIFIED_COLOR = "#222831"
_HOVER_COLOR        = "#ffd740"
_SELECTED_COLOR     = "#ffff00"
_BACKGROUND         = "#0d1117"
_PANEL_BG           = "#161b22"

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _seg_length(f: LineFeature) -> float:
    return math.hypot(f.end.x_mm - f.start.x_mm, f.end.y_mm - f.start.y_mm)


def _seg_angle_deg(f: LineFeature) -> float:
    return math.degrees(math.atan2(
        f.end.y_mm - f.start.y_mm, f.end.x_mm - f.start.x_mm
    )) % 180.0


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Interner Matplotlib-Canvas
# ---------------------------------------------------------------------------

class _MplCanvas(FigureCanvasQTAgg):
    """Matplotlib-Figure eingebettet als Qt-Widget."""
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(14, 9), facecolor=_BACKGROUND)
        self.ax  = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(600, 400)


# ---------------------------------------------------------------------------
# Editor (QMainWindow)
# ---------------------------------------------------------------------------

class ClassificationEditor(QMainWindow):
    """
    Interaktiver Klassifikations-Editor.

    Zeigt Board-Segmente eingefärbt nach Rolle / Sigma und erlaubt
    Klick-Auswahl (inkl. Shift+Klick Mehrfachauswahl) mit anschließender
    Rollenzuweisung.  Verwendet PyQt6 + Matplotlib-Qt-Backend für stabiles
    Zoom/Pan ohne Klick-Konflikte, OS-native Tastenkürzel und Undo.
    """

    _VIEW_ROLE  = "role"
    _VIEW_SIGMA = "sigma"

    def __init__(
        self,
        board: Board,
        spec: ClassificationSpec,
        output_path: Path,
    ) -> None:
        super().__init__()
        self.board = board
        self.spec = spec
        self.output_path = output_path

        self._view_mode: str = self._VIEW_ROLE
        self._selection: set[str] = set()       # feature_ids der ausgewählten Segmente
        self._hover_id: Optional[str] = None
        self._select_mode: bool = False         # False = Navigieren, True = Auswählen
        self._modified: bool = False
        self._undo_stack: list[dict[str, ClassificationEntry]] = []

        # Schnellzugriff feature_id → entry
        self._entry_by_id: dict[str, ClassificationEntry] = {
            e.feature_id: e for e in spec.entries
        }

        # Layer-Sichtbarkeit
        self._layer_visible: dict[str, bool] = {
            la.name: True for la in board.copper_layers
        }

        # Vorberechnete numpy-Arrays für schnelles Picking
        self._precompute_arrays()

        # UI aufbauen
        self._init_ui()
        self._bind_shortcuts()

        # Initiales Rendering
        self._redraw_segments()
        self._update_title()
        self._update_stats_label()
        self._update_info_label()

    # ------------------------------------------------------------------
    # Vorberechnungen
    # ------------------------------------------------------------------

    def _precompute_arrays(self) -> None:
        """Segment-Koordinaten als flaches (N,4)-Array für vektorisiertes Picking."""
        all_features: list[LineFeature] = [
            f for la in self.board.copper_layers for f in la.lines
        ]
        self._all_features = all_features
        n = len(all_features)

        self._segments = np.zeros((n, 4), dtype=np.float64)  # x1,y1,x2,y2
        for i, f in enumerate(all_features):
            self._segments[i] = (
                f.start.x_mm, f.start.y_mm, f.end.x_mm, f.end.y_mm
            )
        self._feature_ids: list[str]   = [f.feature_id for f in all_features]
        self._feature_layers: list[str] = [f.layer_name  for f in all_features]
        self._id_to_idx: dict[str, int] = {
            fid: i for i, fid in enumerate(self._feature_ids)
        }

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.setWindowTitle(f"Klassifikations-Editor – {self.board.name}")
        self.resize(1400, 860)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # --- Matplotlib-Canvas ---
        self._canvas  = _MplCanvas(self)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)

        canvas_container = QWidget()
        cl = QVBoxLayout(canvas_container)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(2)
        cl.addWidget(self._toolbar)
        cl.addWidget(self._canvas, stretch=1)

        # --- Rechtes Panel ---
        right_panel = self._build_control_panel()

        # --- Splitter ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(canvas_container)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1060, 330])

        main_layout.addWidget(splitter, stretch=1)

        # --- Statuszeile ---
        self._status_label = QLabel(
            "Modus wählen: 'Navigieren' für Zoom/Pan,  'Auswählen' für Klick-Selektion."
        )
        self._status_label.setStyleSheet(
            "color:#888; font-size:11px; padding:2px 4px; border-top:1px solid #333;"
        )
        main_layout.addWidget(self._status_label)

        # --- Achsen-Setup ---
        ax = self._canvas.ax
        ax.set_facecolor(_BACKGROUND)
        ax.set_aspect("equal")
        ax.set_xlabel("x [mm]", color="#aaa", fontsize=9)
        ax.set_ylabel("y [mm]", color="#aaa", fontsize=9)
        ax.tick_params(colors="#aaa", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

        # Board-Outline
        if self.board.outline_mm:
            x0, y0, x1, y1 = self.board.outline_mm
            rect = mpatches.FancyBboxPatch(
                (x0, y0), x1 - x0, y1 - y0,
                boxstyle="square,pad=0",
                linewidth=1.5, edgecolor="#444", facecolor="none", zorder=5,
            )
            ax.add_patch(rect)
            m = max(x1 - x0, y1 - y0) * 0.05
            ax.set_xlim(x0 - m, x1 + m)
            ax.set_ylim(y0 - m, y1 + m)
        else:
            ax.autoscale_view()

        # Legende
        role_handles = [
            mpatches.Patch(color=_ROLE_COLORS["winding"],   label="Winding"),
            mpatches.Patch(color=_ROLE_COLORS["connection"], label="Connection"),
            mpatches.Patch(color=_ROLE_COLORS["return"],     label="Return"),
            mpatches.Patch(color=_SELECTED_COLOR,            label="Ausgewählt"),
            mpatches.Patch(color=_HOVER_COLOR,               label="Hover"),
        ]
        sigma_handles = [
            mpatches.Patch(color=_SIGMA_COLORS[1],  label="σ = +1"),
            mpatches.Patch(color=_SIGMA_COLORS[-1], label="σ = −1"),
        ]
        leg1 = ax.legend(
            handles=role_handles, loc="upper left",
            fontsize=7.5, title="Rolle", title_fontsize=8,
            facecolor=_PANEL_BG, edgecolor="#444", labelcolor="white",
        )
        ax.add_artist(leg1)
        ax.legend(
            handles=sigma_handles, loc="upper right",
            fontsize=7.5, title="Sigma", title_fontsize=8,
            facecolor=_PANEL_BG, edgecolor="#444", labelcolor="white",
        )

        # Hover-Linie (immer vorhanden, Daten werden in _on_motion gesetzt)
        self._hover_line, = ax.plot(
            [], [], color=_HOVER_COLOR, linewidth=2.5, alpha=0.85, zorder=9
        )

        # Collections-Container
        self._collections:     dict[str, LineCollection] = {}
        self._sel_collections: list[LineCollection]      = []

        # Canvas-Events
        self._canvas.mpl_connect("button_press_event",   self._on_click)
        self._canvas.mpl_connect("motion_notify_event",  self._on_motion)

    def _build_control_panel(self) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setMinimumWidth(270)
        area.setMaximumWidth(370)
        area.setStyleSheet("QScrollArea { border: none; }")

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # --- Ansicht ---
        grp_view = QGroupBox("Ansicht")
        vl = QVBoxLayout(grp_view)
        self._rb_view_role  = QRadioButton("Rolle")
        self._rb_view_sigma = QRadioButton("Sigma (Windungen)")
        self._rb_view_role.setChecked(True)
        self._rb_view_role.toggled.connect(
            lambda c: c and self._set_view(self._VIEW_ROLE)
        )
        self._rb_view_sigma.toggled.connect(
            lambda c: c and self._set_view(self._VIEW_SIGMA)
        )
        vl.addWidget(self._rb_view_role)
        vl.addWidget(self._rb_view_sigma)
        layout.addWidget(grp_view)

        # --- Layer-Sichtbarkeit ---
        grp_layer = QGroupBox("Layer-Sichtbarkeit")
        ll = QVBoxLayout(grp_layer)
        self._layer_checks: dict[str, QCheckBox] = {}
        for la in self.board.copper_layers:
            cb = QCheckBox(la.name)
            cb.setChecked(True)
            cb.toggled.connect(
                lambda checked, n=la.name: self._toggle_layer(n, checked)
            )
            ll.addWidget(cb)
            self._layer_checks[la.name] = cb
        layout.addWidget(grp_layer)

        # --- Modus ---
        grp_mode = QGroupBox("Modus")
        ml = QVBoxLayout(grp_mode)
        self._rb_navigate = QRadioButton("🔍  Navigieren  (Zoom / Pan)")
        self._rb_select   = QRadioButton("☞  Auswählen  (Klick / Shift+Klick)")
        self._rb_navigate.setChecked(True)
        self._rb_navigate.toggled.connect(
            lambda c: c and self._set_mode_navigate()
        )
        self._rb_select.toggled.connect(
            lambda c: c and self._set_mode_select()
        )
        ml.addWidget(self._rb_navigate)
        ml.addWidget(self._rb_select)
        layout.addWidget(grp_mode)

        # --- Rolle zuweisen ---
        grp_role = QGroupBox("Rolle zuweisen  [W / C / R]")
        rl = QVBoxLayout(grp_role)
        btn_w = QPushButton("[W]  Winding")
        btn_c = QPushButton("[C]  Connection")
        btn_r = QPushButton("[R]  Return")
        btn_w.setStyleSheet(
            f"background:{_ROLE_COLORS['winding']};color:#000;font-weight:bold;"
        )
        btn_c.setStyleSheet(
            f"background:{_ROLE_COLORS['connection']};color:#fff;font-weight:bold;"
        )
        btn_r.setStyleSheet(
            f"background:{_ROLE_COLORS['return']};color:#fff;font-weight:bold;"
        )
        btn_w.clicked.connect(lambda: self._set_role("winding"))
        btn_c.clicked.connect(lambda: self._set_role("connection"))
        btn_r.clicked.connect(lambda: self._set_role("return"))
        rl.addWidget(btn_w)
        rl.addWidget(btn_c)
        rl.addWidget(btn_r)
        layout.addWidget(grp_role)

        # --- Sigma ---
        grp_sig = QGroupBox("Sigma  [+ / -]")
        sl = QHBoxLayout(grp_sig)
        btn_sp = QPushButton("σ = +1")
        btn_sn = QPushButton("σ = −1")
        btn_sp.setStyleSheet(
            f"background:{_SIGMA_COLORS[1]};color:#000;font-weight:bold;"
        )
        btn_sn.setStyleSheet(
            f"background:{_SIGMA_COLORS[-1]};color:#000;font-weight:bold;"
        )
        btn_sp.clicked.connect(lambda: self._set_sigma(1))
        btn_sn.clicked.connect(lambda: self._set_sigma(-1))
        sl.addWidget(btn_sp)
        sl.addWidget(btn_sn)
        layout.addWidget(grp_sig)

        # --- Aktionen ---
        grp_act = QGroupBox("Aktionen")
        al = QVBoxLayout(grp_act)
        btn_clear = QPushButton("Auswahl aufheben  [Esc]")
        btn_undo  = QPushButton("↩  Rückgängig  [Ctrl+Z]")
        btn_clear.clicked.connect(self._clear_selection)
        btn_undo.clicked.connect(self._undo)
        al.addWidget(btn_clear)
        al.addWidget(btn_undo)
        layout.addWidget(grp_act)

        # --- Info Ausgewählt ---
        grp_info = QGroupBox("Ausgewähltes Segment")
        il = QVBoxLayout(grp_info)
        self._info_label = QLabel("Kein Segment ausgewählt")
        self._info_label.setFont(QFont("Courier New", 8))
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color:#ccc;")
        il.addWidget(self._info_label)
        layout.addWidget(grp_info)

        # --- Statistik ---
        grp_stats = QGroupBox("Statistik")
        stl = QVBoxLayout(grp_stats)
        self._stats_label = QLabel()
        self._stats_label.setFont(QFont("Courier New", 8))
        self._stats_label.setStyleSheet("color:#ccc;")
        stl.addWidget(self._stats_label)
        layout.addWidget(grp_stats)

        # --- Speichern ---
        btn_save = QPushButton("💾  Speichern  [Ctrl+S]")
        btn_save.setStyleSheet(
            "background:#1565c0;color:white;font-weight:bold;"
            "font-size:13px;padding:8px;"
        )
        btn_save.clicked.connect(self._save)
        layout.addWidget(btn_save)

        # --- Ausgabepfad ---
        path_lbl = QLabel(f"→ {self.output_path}")
        path_lbl.setStyleSheet("color:#555;font-size:9px;")
        path_lbl.setWordWrap(True)
        layout.addWidget(path_lbl)

        layout.addStretch()
        area.setWidget(w)
        return area

    def _bind_shortcuts(self) -> None:
        pairs = [
            ("Ctrl+S",  self._save),
            ("Ctrl+Z",  self._undo),
            ("Escape",  self._clear_selection),
            ("W",       lambda: self._set_role("winding")),
            ("C",       lambda: self._set_role("connection")),
            ("R",       lambda: self._set_role("return")),
            ("+",       lambda: self._set_sigma(1)),
            ("=",       lambda: self._set_sigma(1)),
            ("-",       lambda: self._set_sigma(-1)),
            ("V",       self._toggle_view),
        ]
        for seq, fn in pairs:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

    # ------------------------------------------------------------------
    # Modus-Umschaltung
    # ------------------------------------------------------------------

    def _set_mode_navigate(self) -> None:
        self._select_mode = False
        self._toolbar.setEnabled(True)
        self._hover_line.set_data([], [])
        self._canvas.draw_idle()
        self._status_label.setText(
            "Navigationsmodus: Zoom/Pan aktiv.  → 'Auswählen' wechseln für Segment-Selektion."
        )

    def _set_mode_select(self) -> None:
        self._select_mode = True
        # Aktives Zoom/Pan-Werkzeug deaktivieren
        try:
            from matplotlib.backend_bases import _Mode
            if self._toolbar.mode == _Mode.ZOOM:
                self._toolbar.zoom()
            elif self._toolbar.mode == _Mode.PAN:
                self._toolbar.pan()
        except Exception:
            pass
        self._toolbar.setEnabled(False)
        self._status_label.setText(
            "Auswahlmodus: Klick = auswählen,  Shift+Klick = zur Auswahl hinzufügen.  "
            "W/C/R = Rolle zuweisen."
        )

    # ------------------------------------------------------------------
    # Segment-Rendering
    # ------------------------------------------------------------------

    def _redraw_segments(self) -> None:
        """Baut alle LineCollections neu auf (Layer-Sichtbarkeit + Mehrfachauswahl)."""
        ax = self._canvas.ax

        # Alte Collections entfernen
        for coll in list(self._collections.values()):
            try:
                coll.remove()
            except ValueError:
                pass
        self._collections.clear()
        for coll in self._sel_collections:
            try:
                coll.remove()
            except ValueError:
                pass
        self._sel_collections.clear()

        # Segmente nach Farbe und Layer-Sichtbarkeit gruppieren
        color_segs: dict[str, list] = defaultdict(list)
        for i, fid in enumerate(self._feature_ids):
            if not self._layer_visible.get(self._feature_layers[i], True):
                continue
            seg = [
                (self._segments[i, 0], self._segments[i, 1]),
                (self._segments[i, 2], self._segments[i, 3]),
            ]
            if fid not in self._entry_by_id:
                color_segs[_UNCLASSIFIED_COLOR].append(seg)
                continue
            entry = self._entry_by_id[fid]
            if self._view_mode == self._VIEW_ROLE:
                color = _ROLE_COLORS.get(entry.role, _UNCLASSIFIED_COLOR)
            else:
                if entry.role == "winding":
                    color = _SIGMA_COLORS.get(entry.sigma, "#888")
                elif entry.role == "return":
                    color = _ROLE_COLORS["return"]
                else:
                    color = _SIGMA_COLORS[0]
            color_segs[color].append(seg)

        lw_map = {
            _ROLE_COLORS["winding"]:    0.7,
            _ROLE_COLORS["connection"]: 0.4,
            _ROLE_COLORS["return"]:     0.5,
            _SIGMA_COLORS[1]:           0.7,
            _SIGMA_COLORS[-1]:          0.7,
            _SIGMA_COLORS[0]:           0.4,
            _UNCLASSIFIED_COLOR:        0.3,
        }
        for color, segs in color_segs.items():
            lw = lw_map.get(color, 0.5)
            alpha = 0.4 if color == _UNCLASSIFIED_COLOR else 0.85
            coll = LineCollection(
                segs, colors=color, linewidths=lw,
                alpha=alpha, capstyle="round", zorder=2,
            )
            ax.add_collection(coll)
            self._collections[color] = coll

        # Ausgewählte Segmente hervorheben
        if self._selection:
            sel_segs = []
            for fid in self._selection:
                idx = self._id_to_idx.get(fid)
                if idx is not None:
                    sel_segs.append([
                        (self._segments[idx, 0], self._segments[idx, 1]),
                        (self._segments[idx, 2], self._segments[idx, 3]),
                    ])
            if sel_segs:
                coll = LineCollection(
                    sel_segs, colors=_SELECTED_COLOR, linewidths=2.0,
                    alpha=1.0, zorder=10, capstyle="round",
                )
                ax.add_collection(coll)
                self._sel_collections.append(coll)

        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Anzeige-Updates
    # ------------------------------------------------------------------

    def _update_title(self) -> None:
        counts = self._role_counts()
        prefix = "[●] " if self._modified else ""
        self.setWindowTitle(
            f"{prefix}Klassifikations-Editor – {self.board.name}  |  "
            f"Winding: {counts.get('winding', 0)}  "
            f"Connection: {counts.get('connection', 0)}  "
            f"Return: {counts.get('return', 0)}"
        )

    def _update_stats_label(self) -> None:
        counts = self._role_counts()
        sigma_p = sum(
            1 for e in self._entry_by_id.values()
            if e.role == "winding" and e.sigma == 1
        )
        sigma_n = sum(
            1 for e in self._entry_by_id.values()
            if e.role == "winding" and e.sigma == -1
        )
        n_unclassified = len(self._all_features) - len(self._entry_by_id)
        self._stats_label.setText(
            f"Winding:    {counts.get('winding', 0):>5}\n"
            f"  σ = +1:   {sigma_p:>5}\n"
            f"  σ = −1:   {sigma_n:>5}\n"
            f"Connection: {counts.get('connection', 0):>5}\n"
            f"Return:     {counts.get('return', 0):>5}\n"
            f"Unklassif.: {n_unclassified:>5}\n"
            f"─────────────────────\n"
            f"Gesamt:     {len(self._all_features):>5}"
        )

    def _update_info_label(self) -> None:
        if not self._selection:
            self._info_label.setText("Kein Segment ausgewählt")
            return

        if len(self._selection) > 1:
            roles: dict[str, int] = defaultdict(int)
            for fid in self._selection:
                e = self._entry_by_id.get(fid)
                if e:
                    roles[e.role] += 1
            summary = "\n".join(f"  {r}: {n}" for r, n in sorted(roles.items()))
            self._info_label.setText(
                f"{len(self._selection)} Segmente ausgewählt:\n{summary}"
            )
            return

        fid   = next(iter(self._selection))
        entry = self._entry_by_id.get(fid)
        idx   = self._id_to_idx.get(fid)
        if entry is None or idx is None:
            self._info_label.setText("Kein Eintrag")
            return

        f      = self._all_features[idx]
        length = _seg_length(f)
        angle  = _seg_angle_deg(f)
        self._info_label.setText(
            f"ID:     {entry.feature_id[:20]}\n"
            f"Layer:  {entry.layer_name}\n"
            f"Rolle:  {entry.role}\n"
            f"Sigma:  {entry.sigma:+d}\n"
            f"Länge:  {length:.4f} mm\n"
            f"Breite: {f.width_mm:.4f} mm\n"
            f"Winkel: {angle:.1f}°\n"
            f"Note:   {entry.note or '—'}"
        )

    def _update_selection_status(self) -> None:
        n = len(self._selection)
        if n == 0:
            self._status_label.setText(
                "Auswahlmodus  |  Kein Segment ausgewählt  |  "
                "Shift+Klick = Mehrfachauswahl  |  W/C/R = Rolle zuweisen"
            )
        else:
            self._status_label.setText(
                f"Auswahlmodus  |  {n} Segment(e) ausgewählt  |  "
                "W/C/R = Rolle  |  +/- = Sigma  |  Ctrl+Z = Rückgängig"
            )

    # ------------------------------------------------------------------
    # Picking – Lot-Abstand (geometrisch korrekt für schräge Segmente)
    # ------------------------------------------------------------------

    def _find_nearest_segment(self, x: float, y: float) -> Optional[str]:
        """Perpendicular foot-point distance – korrekt für lange/schräge Segmente."""
        s = self._segments  # (N, 4): x1,y1,x2,y2
        if len(s) == 0:
            return None

        dx = s[:, 2] - s[:, 0]
        dy = s[:, 3] - s[:, 1]
        l2 = np.maximum(dx * dx + dy * dy, 1e-12)

        t  = np.clip(((x - s[:, 0]) * dx + (y - s[:, 1]) * dy) / l2, 0.0, 1.0)
        px = s[:, 0] + t * dx
        py = s[:, 1] + t * dy
        dist = np.hypot(x - px, y - py)

        # Unsichtbare Layer ignorieren
        for i, layer in enumerate(self._feature_layers):
            if not self._layer_visible.get(layer, True):
                dist[i] = np.inf

        idx  = int(np.argmin(dist))
        xlim = self._canvas.ax.get_xlim()
        ylim = self._canvas.ax.get_ylim()
        tol  = 0.015 * max(xlim[1] - xlim[0], ylim[1] - ylim[0])

        return self._feature_ids[idx] if dist[idx] <= tol else None

    # ------------------------------------------------------------------
    # Event-Handler
    # ------------------------------------------------------------------

    def _on_click(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes is not self._canvas.ax or event.button != 1:
            return
        if not self._select_mode:
            return

        fid   = self._find_nearest_segment(event.xdata, event.ydata)
        shift = (event.key == "shift") if event.key else False

        if fid is None:
            if not shift:
                self._selection.clear()
        elif shift:
            # Toggle: Segment hinzufügen oder entfernen
            if fid in self._selection:
                self._selection.discard(fid)
            else:
                self._selection.add(fid)
        else:
            # Zweiter Klick auf dasselbe → Auswahl aufheben
            self._selection = set() if self._selection == {fid} else {fid}

        self._redraw_segments()
        self._update_info_label()
        self._update_selection_status()

    def _on_motion(self, event) -> None:  # type: ignore[no-untyped-def]
        ax = self._canvas.ax
        if event.inaxes is not ax or event.xdata is None:
            self._hover_line.set_data([], [])
            self._canvas.draw_idle()
            return

        coord = f"x = {event.xdata:8.3f} mm   y = {event.ydata:8.3f} mm"

        if self._select_mode:
            fid = self._find_nearest_segment(event.xdata, event.ydata)
            if fid != self._hover_id:
                self._hover_id = fid
                if fid is not None and fid not in self._selection:
                    idx = self._id_to_idx[fid]
                    self._hover_line.set_data(
                        [self._segments[idx, 0], self._segments[idx, 2]],
                        [self._segments[idx, 1], self._segments[idx, 3]],
                    )
                else:
                    self._hover_line.set_data([], [])
            self._status_label.setText(
                f"Auswahlmodus  |  {coord}  |  "
                f"{len(self._selection)} ausgewählt  |  Shift+Klick = Mehrfachauswahl"
            )
        else:
            self._hover_line.set_data([], [])
            self._status_label.setText(f"Navigationsmodus  |  {coord}")

        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Ansicht / Layer
    # ------------------------------------------------------------------

    def _set_view(self, mode: str) -> None:
        self._view_mode = mode
        self._redraw_segments()

    def _toggle_view(self) -> None:
        new = self._VIEW_SIGMA if self._view_mode == self._VIEW_ROLE else self._VIEW_ROLE
        self._view_mode = new
        if new == self._VIEW_ROLE:
            self._rb_view_role.setChecked(True)
        else:
            self._rb_view_sigma.setChecked(True)
        self._redraw_segments()

    def _toggle_layer(self, name: str, visible: bool) -> None:
        self._layer_visible[name] = visible
        self._redraw_segments()

    # ------------------------------------------------------------------
    # Modifikationen
    # ------------------------------------------------------------------

    def _set_role(self, role: str) -> None:
        if not self._selection:
            self._status_label.setText("⚠ Kein Segment ausgewählt.")
            return
        self._push_undo()
        for fid in list(self._selection):
            entry = self._entry_by_id.get(fid)
            if entry is None:
                # Noch nicht klassifiziertes Segment → Eintrag anlegen
                idx = self._id_to_idx.get(fid)
                if idx is None:
                    continue
                f = self._all_features[idx]
                entry = ClassificationEntry(
                    feature_id=fid,
                    layer_name=f.layer_name,
                    role=role,
                    sigma=0,
                    window_id=None,
                    note=None,
                )
            sigma = entry.sigma
            if role == "connection":
                sigma = 0
            elif role == "return":
                sigma = -1
            elif role == "winding" and sigma == 0:
                sigma = 1
            self._entry_by_id[fid] = ClassificationEntry(
                feature_id=entry.feature_id,
                layer_name=entry.layer_name,
                role=role,
                sigma=sigma,
                window_id=entry.window_id,
                note=f"manuell:{role}",
            )
        self._sync_spec()
        self._modified = True
        self._redraw_segments()
        self._update_info_label()
        self._update_stats_label()
        self._update_title()
        self._update_selection_status()

    def _set_sigma(self, sigma: int) -> None:
        if not self._selection:
            return
        self._push_undo()
        for fid in list(self._selection):
            entry = self._entry_by_id.get(fid)
            if entry is None:
                # Noch nicht klassifiziertes Segment → Standard-Winding-Eintrag anlegen
                idx = self._id_to_idx.get(fid)
                if idx is None:
                    continue
                f = self._all_features[idx]
                entry = ClassificationEntry(
                    feature_id=fid,
                    layer_name=f.layer_name,
                    role="winding",
                    sigma=sigma,
                    window_id=None,
                    note=None,
                )
            self._entry_by_id[fid] = ClassificationEntry(
                feature_id=entry.feature_id,
                layer_name=entry.layer_name,
                role=entry.role,
                sigma=sigma,
                window_id=entry.window_id,
                note=f"manuell:σ{sigma:+d}",
            )
        self._sync_spec()
        self._modified = True
        self._redraw_segments()
        self._update_info_label()
        self._update_stats_label()
        self._update_title()

    def _clear_selection(self) -> None:
        self._selection.clear()
        self._hover_id = None
        self._hover_line.set_data([], [])
        self._redraw_segments()
        self._update_info_label()
        self._update_selection_status()

    def _push_undo(self) -> None:
        self._undo_stack.append(dict(self._entry_by_id))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _undo(self) -> None:
        if not self._undo_stack:
            self._status_label.setText("⚠ Nichts zum Rückgängigmachen.")
            return
        self._entry_by_id = self._undo_stack.pop()
        self._sync_spec()
        self._modified = True
        self._selection.clear()
        self._redraw_segments()
        self._update_info_label()
        self._update_stats_label()
        self._update_title()
        self._status_label.setText("↩ Rückgängig gemacht.")

    def _sync_spec(self) -> None:
        existing_ids = {e.feature_id for e in self.spec.entries}
        for i, e in enumerate(self.spec.entries):
            if e.feature_id in self._entry_by_id:
                self.spec.entries[i] = self._entry_by_id[e.feature_id]
        # Neu angelegte Einträge (bisher unklassifizierte Segmente) anhängen
        for fid, e in self._entry_by_id.items():
            if fid not in existing_ids:
                self.spec.entries.append(e)
                existing_ids.add(fid)

    def _save(self) -> None:
        self.spec.entries = list(self._entry_by_id.values())
        self.spec.auto_detected = False
        self.spec.to_yaml(self.output_path)
        self._modified = False
        self._update_title()
        self._status_label.setText(f"✓ Gespeichert: {self.output_path}")
        print(f"✓ Klassifikation gespeichert: {self.output_path}")

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _role_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self._entry_by_id.values():
            counts[e.role] = counts.get(e.role, 0) + 1
        return counts

    def show(self) -> None:  # type: ignore[override]
        super().show()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Interaktiver manueller Klassifikations-Editor für PCB Rogowski-Spulen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("gerber_dir", type=Path, help="Pfad zum Gerber-Verzeichnis.")
    p.add_argument(
        "--classification", "-i", type=Path, default=None,
        help=(
            "Vorhandene Klassifikations-YAML laden. "
            "Standard: <gerber_dir>/classification_draft.yaml"
        ),
    )
    p.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Ausgabepfad für YAML (Standard: wie --classification).",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()

    gerber_dir  = args.gerber_dir.resolve()
    yaml_path   = (
        args.classification.resolve()
        if args.classification
        else gerber_dir / "classification_draft.yaml"
    )
    output_path = args.output.resolve() if args.output else yaml_path

    # Board laden
    print(f"Lade Board: {gerber_dir}")
    try:
        board = GerberBoardLoader().load_from_gerber(gerber_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[FEHLER] {exc}", file=sys.stderr)
        return 1

    x0, y0, x1, y1 = board.outline_mm or (0, 0, 0, 0)
    n_total = sum(len(la.lines) for la in board.copper_layers)
    print(
        f"  → {board.name}  |  "
        f"{len(board.copper_layers)} Kupferlagen  |  "
        f"{n_total:,} Segmente  |  "
        f"{x1-x0:.1f} × {y1-y0:.1f} mm"
    )

    # Bestehende Klassifikation laden oder leere Spec anlegen
    if yaml_path.exists():
        print(f"Lade Klassifikation: {yaml_path}")
        spec    = ClassificationSpec.from_yaml(yaml_path)
        n_loaded = len(spec.entries)
        print(f"  → {n_loaded} Einträge geladen  |  auto={spec.auto_detected}")
    else:
        print("Keine Klassifikation gefunden – starte mit leerer Spec.")
        spec    = ClassificationSpec(
            board_name=board.name,
            source_gerber=str(gerber_dir),
            entries=[],
            auto_detected=False,
            notes="Manuelle Klassifikation.",
        )
        n_loaded = 0

    # Gap-Filling: nicht zugewiesene Segmente per Topologie belegen
    n_unclassified = n_total - n_loaded
    if n_unclassified > 0 and n_loaded > 0:
        print(f"Gap-Filling: {n_unclassified} noch nicht zugewiesene Segmente …")
        spec     = TopologyGapFiller().fill(board, spec)
        n_filled = len(spec.entries) - n_loaded
        print(f"  → {n_filled} Segmente per Topologie zugewiesen.")
    elif n_unclassified > 0:
        print(
            f"  → {n_unclassified} Segmente noch unklassifiziert "
            "(manuelle Zuweisung nötig, danach wird Gap-Fill aktiv)."
        )

    counts            = spec.role_counts()
    n_still_unclassed = n_total - len(spec.entries)
    print(
        f"  → {counts.get('winding', 0)} Winding  |  "
        f"{counts.get('connection', 0)} Connection  |  "
        f"{counts.get('return', 0)} Return  |  "
        f"{n_still_unclassed} Unklassifiziert"
    )

    print(f"\nEditor öffnet sich  |  Ausgabe: {output_path}")
    print(
        "Tastenkürzel: W/C/R = Rolle, +/- = Sigma, V = Ansicht, "
        "Ctrl+S = Speichern, Ctrl+Z = Rückgängig, Esc = Auswahl aufheben"
    )

    app = QApplication.instance() or QApplication(sys.argv)
    editor = ClassificationEditor(board, spec, output_path)
    editor.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
