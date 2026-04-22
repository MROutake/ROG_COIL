"""
Interaktiver Klassifikations-/Via-Fenster-Canvas (PyQt6 + Matplotlib).

Portiert die bewaehrten Bedienmuster aus
``scripts/classify_board.py`` und ``scripts/define_windows.py``
in ein wiederverwendbares Qt-Widget.

Features
--------
* Zwei Sub-Modi:
    - ``leiter``: Leiterbahn-Segmente klicken (Lot-Picking, Shift+Klick
      Multi-Select, Hover-Highlight, Rolle/Sigma-View).
    - ``vias``: Vias nummeriert anzeigen, zwei Klicks definieren ein
      rechteckiges Fenster.
* Interaktionsmodus ``navigate`` (Zoom/Pan) vs ``select`` (Klick-
  Selektion) – Umschaltung erforderlich, damit Pan/Zoom nicht mit der
  Auswahl kollidieren.
* Layer-Sichtbarkeit pro Kupferlage.
* Qt-Signale zur lose gekoppelten Einbettung in Tabs.
"""

from __future__ import annotations

import math
from typing import Iterable

import matplotlib
import matplotlib.patches as mpatches
import numpy as np

matplotlib.use("QtAgg", force=False)

from matplotlib.backends.backend_qtagg import (  # noqa: E402
    FigureCanvasQTAgg as FigureCanvas,
)
from matplotlib.backends.backend_qt import (  # noqa: E402
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget  # noqa: E402

from pcb_rogowski.domain.board.models import Board, LayerType, LineFeature
from pcb_rogowski.domain.trace.models import ViaWindow


# ---------------------------------------------------------------------------
# Farb-Palette (1:1 aus scripts/classify_board.py)
# ---------------------------------------------------------------------------

_ROLE_COLORS: dict[str, str] = {
    "winding":    "#00e676",
    "connection": "#546e7a",
    "return":     "#ef5350",
}
_SIGMA_COLORS: dict[int, str] = {
    1:  "#42a5f5",
    -1: "#ff7043",
    0:  "#546e7a",
}
_UNCLASSIFIED    = "#8a5cf6"   # violett -- deutlich sichtbar gegen Rolle-Farben
_HOVER           = "#ffd740"
_SELECTED        = "#ffff00"
_BACKGROUND      = "#0d1117"
_VIA_IDLE        = "#1e1f22"
_VIA_EDGE        = "#e6e6e6"
_VIA_SELECTED    = "#ff4444"
_WINDOW_POS      = "#44aaff"
_WINDOW_NEG      = "#ff8800"
_OUTLINE         = "#2a2f36"


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

class ClassifyCanvas(QWidget):
    """
    Interaktiver Canvas fuer Klassifikation + Via-Fenster.

    Qt-Signale
    ----------
    ``segment_clicked(str, bool)``:
        feature_id, shift_held.  Vom Tab zu verarbeiten (toggle / replace).
    ``via_clicked(str, float, float, bool)``:
        via_id, x_mm, y_mm, shift_held.
    ``hover_changed(str)``:
        feature_id des aktuell gehoverten Segments (`""` wenn keines).
    """

    segment_clicked = pyqtSignal(str, bool)
    via_clicked     = pyqtSignal(str, float, float, bool)
    hover_changed   = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # State ---------------------------------------------------------
        self._board: Board | None = None
        self._all_features: list[LineFeature] = []
        self._segments = np.zeros((0, 4), dtype=np.float64)
        self._feature_ids: list[str] = []
        self._feature_layers: list[str] = []
        self._id_to_idx: dict[str, int] = {}
        self._vias: list[dict] = []      # dicts: id, x, y, d, layer

        self._roles: dict[str, str] = {}   # fid -> role
        self._sigmas: dict[str, int] = {}  # fid -> sigma
        self._selected_ids: set[str] = set()
        self._selected_via_ids: list[str] = []  # geordnet (A, B)
        self._hover_id: str = ""

        self._windows: list[ViaWindow] = []
        self._layer_visible: dict[str, bool] = {}

        self._mode: str = "leiter"          # 'leiter' | 'vias'
        self._interact_mode: str = "navigate"  # 'navigate' | 'select'
        self._view_mode: str = "role"       # 'role' | 'sigma'
        self._show_windows: bool = True
        self._show_via_labels: bool = True

        # Figure --------------------------------------------------------
        self._fig = Figure(figsize=(9, 7), facecolor=_BACKGROUND)
        self._canvas = FigureCanvas(self._fig)
        self._toolbar = NavigationToolbar(self._canvas, self)
        self._ax = self._fig.add_subplot(111)
        self._ax.set_facecolor(_BACKGROUND)
        self._ax.set_aspect("equal")
        self._ax.set_xlabel("x [mm]", color="#aaa")
        self._ax.set_ylabel("y [mm]", color="#aaa")
        self._ax.tick_params(colors="#aaa", labelsize=8)
        for s in self._ax.spines.values():
            s.set_color(_OUTLINE)

        self._hover_line, = self._ax.plot(
            [], [], color=_HOVER, linewidth=2.5, alpha=0.9, zorder=9)

        self._collections: dict[str, LineCollection] = {}
        self._sel_overlay: LineCollection | None = None
        self._via_patches: list = []
        self._via_labels: list = []
        self._window_patches: list = []
        self._window_labels: list = []

        self._canvas.mpl_connect("button_press_event",  self._on_click)
        self._canvas.mpl_connect("motion_notify_event", self._on_motion)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._toolbar)
        lay.addWidget(self._canvas, stretch=1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ==================================================================
    # Public API
    # ==================================================================
    def set_board(self, board: Board | None) -> None:
        self._board = board
        self._selected_ids.clear()
        self._selected_via_ids.clear()
        self._hover_id = ""
        if board is None:
            self._all_features = []
            self._segments = np.zeros((0, 4), dtype=np.float64)
            self._feature_ids = []
            self._feature_layers = []
            self._id_to_idx = {}
            self._vias = []
            self._layer_visible = {}
        else:
            self._precompute()
            self._layer_visible = {la.name: True for la in board.copper_layers}
        self._redraw_all()

    def set_roles(self, roles: dict[str, str], sigmas: dict[str, int]) -> None:
        self._roles = dict(roles)
        self._sigmas = dict(sigmas)
        self._redraw_segments()

    def set_windows(self, windows: list[ViaWindow]) -> None:
        self._windows = list(windows)
        self._redraw_windows()

    def set_selection(
        self,
        feature_ids: Iterable[str],
        via_ids: Iterable[str],
    ) -> None:
        self._selected_ids = set(feature_ids)
        self._selected_via_ids = list(via_ids)
        self._redraw_selection()
        self._redraw_vias()

    def set_mode(self, mode: str) -> None:
        if mode not in ("leiter", "vias"):
            return
        self._mode = mode
        # Auswahl der jeweils anderen Kategorie zuruecksetzen
        if mode == "leiter":
            self._selected_via_ids.clear()
        else:
            self._selected_ids.clear()
        self._redraw_vias()
        self._redraw_selection()

    def set_interact_mode(self, mode: str) -> None:
        """``navigate`` = Pan/Zoom, ``select`` = Klick-Selektion."""
        if mode not in ("navigate", "select"):
            return
        self._interact_mode = mode
        # Pan/Zoom der Toolbar deaktivieren, wenn in Select
        if mode == "select":
            try:
                if self._toolbar.mode == "pan/zoom":
                    self._toolbar.pan()
                elif self._toolbar.mode == "zoom rect":
                    self._toolbar.zoom()
            except Exception:
                pass

    def set_view(self, mode: str) -> None:
        if mode not in ("role", "sigma"):
            return
        self._view_mode = mode
        self._redraw_segments()

    def set_layer_visible(self, name: str, visible: bool) -> None:
        if name in self._layer_visible:
            self._layer_visible[name] = visible
            self._redraw_segments()
            self._redraw_vias()

    def set_show_windows(self, visible: bool) -> None:
        self._show_windows = visible
        self._redraw_windows()

    def set_show_via_labels(self, visible: bool) -> None:
        self._show_via_labels = visible
        self._redraw_vias()

    def reset_view(self) -> None:
        if self._board is None or self._board.outline_mm is None:
            return
        x0, y0, x1, y1 = self._board.outline_mm
        pad = max((x1 - x0), (y1 - y0)) * 0.05
        self._ax.set_xlim(x0 - pad, x1 + pad)
        self._ax.set_ylim(y0 - pad, y1 + pad)
        self._canvas.draw_idle()

    # ==================================================================
    # Vorberechnungen
    # ==================================================================
    def _precompute(self) -> None:
        assert self._board is not None
        features: list[LineFeature] = []
        for la in self._board.copper_layers:
            features.extend(la.lines)
        self._all_features = features
        n = len(features)
        self._segments = np.zeros((n, 4), dtype=np.float64)
        self._feature_ids = []
        self._feature_layers = []
        for i, f in enumerate(features):
            self._segments[i] = (f.start.x_mm, f.start.y_mm,
                                 f.end.x_mm,   f.end.y_mm)
            self._feature_ids.append(f.feature_id)
            self._feature_layers.append(f.layer_name)
        self._id_to_idx = {fid: i for i, fid in enumerate(self._feature_ids)}

        # Vias (duplikatfrei) -- alle Layer durchsuchen (nicht nur Cu),
        # denn Vias liegen je nach Gerber-Import auch auf Drill-/Other-Lagen.
        seen: set[tuple[float, float]] = set()
        vias: list[dict] = []
        for la in self._board.layers:
            for pad in la.pads:
                if not pad.is_via:
                    continue
                key = (round(pad.center.x_mm, 3), round(pad.center.y_mm, 3))
                if key in seen:
                    continue
                seen.add(key)
                vias.append({
                    "id":    pad.feature_id,
                    "x":     pad.center.x_mm,
                    "y":     pad.center.y_mm,
                    "d":     pad.diameter_mm,
                    "layer": la.name,
                })
        vias.sort(key=lambda v: (round(v["x"], 1), round(v["y"], 1)))
        for i, v in enumerate(vias):
            v["idx"] = i
        self._vias = vias

    # ==================================================================
    # Rendering
    # ==================================================================
    def _redraw_all(self) -> None:
        self._ax.clear()
        self._ax.set_facecolor(_BACKGROUND)
        self._ax.set_aspect("equal")
        self._ax.set_xlabel("x [mm]", color="#aaa")
        self._ax.set_ylabel("y [mm]", color="#aaa")
        self._ax.tick_params(colors="#aaa", labelsize=8)
        for s in self._ax.spines.values():
            s.set_color(_OUTLINE)
        self._ax.grid(True, alpha=0.15)

        self._collections.clear()
        self._via_patches.clear()
        self._via_labels.clear()
        self._window_patches.clear()
        self._window_labels.clear()
        self._sel_overlay = None

        if self._board is None:
            self._ax.text(0.5, 0.5, "kein Design geladen",
                          color="#888", ha="center", va="center",
                          transform=self._ax.transAxes)
            self._canvas.draw_idle()
            return

        # Outline
        if self._board.outline_mm:
            x0, y0, x1, y1 = self._board.outline_mm
            self._ax.add_patch(mpatches.Rectangle(
                (x0, y0), x1 - x0, y1 - y0,
                fill=False, edgecolor=_OUTLINE, linewidth=0.8, zorder=0))
            pad = max((x1 - x0), (y1 - y0)) * 0.05
            self._ax.set_xlim(x0 - pad, x1 + pad)
            self._ax.set_ylim(y0 - pad, y1 + pad)

        # Hover-Linie
        self._hover_line, = self._ax.plot(
            [], [], color=_HOVER, linewidth=2.5, alpha=0.9, zorder=9)

        self._redraw_segments()
        self._redraw_vias()
        self._redraw_windows()
        self._redraw_selection()

    def _redraw_segments(self) -> None:
        # Existierende Collections entfernen
        for col in self._collections.values():
            try:
                col.remove()
            except Exception:
                pass
        self._collections.clear()

        if self._board is None:
            self._canvas.draw_idle()
            return

        # Gruppierung nach Farbe/Layer
        idx_by_color: dict[str, list[int]] = {}
        for i, fid in enumerate(self._feature_ids):
            layer = self._feature_layers[i]
            if not self._layer_visible.get(layer, True):
                continue
            col = self._color_for(fid)
            idx_by_color.setdefault(col, []).append(i)

        for col, idxs in idx_by_color.items():
            segs = self._segments[idxs].reshape(-1, 2, 2).tolist()
            is_unclassified = (col == _UNCLASSIFIED)
            lc = LineCollection(
                segs, colors=col,
                linewidths=1.0 if is_unclassified else 1.8,
                linestyles="dashed" if is_unclassified else "solid",
                alpha=0.75 if is_unclassified else 1.0,
                capstyle="round", zorder=2 if is_unclassified else 3)
            self._ax.add_collection(lc)
            self._collections[col] = lc

        self._redraw_selection()
        self._canvas.draw_idle()

    def _color_for(self, fid: str) -> str:
        if self._view_mode == "sigma":
            s = self._sigmas.get(fid, 0)
            return _SIGMA_COLORS.get(s, _UNCLASSIFIED)
        role = self._roles.get(fid)
        if role is None:
            return _UNCLASSIFIED
        return _ROLE_COLORS.get(role, _UNCLASSIFIED)

    def _redraw_selection(self) -> None:
        if self._sel_overlay is not None:
            try:
                self._sel_overlay.remove()
            except Exception:
                pass
            self._sel_overlay = None
        if not self._selected_ids or self._board is None:
            self._canvas.draw_idle()
            return
        idxs = [self._id_to_idx[f] for f in self._selected_ids
                if f in self._id_to_idx]
        if not idxs:
            self._canvas.draw_idle()
            return
        segs = self._segments[idxs].reshape(-1, 2, 2).tolist()
        self._sel_overlay = LineCollection(
            segs, colors=_SELECTED, linewidths=3.5,
            capstyle="round", zorder=8, alpha=0.95)
        self._ax.add_collection(self._sel_overlay)
        self._canvas.draw_idle()

    def _redraw_vias(self) -> None:
        # Alte Artists raeumen
        for p in self._via_patches:
            try: p.remove()
            except Exception: pass
        for t in self._via_labels:
            try: t.remove()
            except Exception: pass
        self._via_patches.clear()
        self._via_labels.clear()

        if self._board is None or not self._vias:
            self._canvas.draw_idle()
            return

        # Vias werden als Marker (pixelgroess) gezeichnet, damit sie auch
        # bei weit herausgezoomter Ansicht sichtbar bleiben.
        show_labels = self._show_via_labels and self._mode == "vias"
        for v in self._vias:
            is_sel = v["id"] in self._selected_via_ids
            # Markergroesse in Punkten (nicht in mm -- zoom-unabhaengig)
            base_size = max(v["d"] * 2.2, 6.0)  # min 6 pt
            size = base_size * (1.6 if is_sel else 1.0)
            face = _VIA_SELECTED if is_sel else _VIA_IDLE
            artist, = self._ax.plot(
                v["x"], v["y"], marker="o",
                markerfacecolor=face,
                markeredgecolor=_VIA_EDGE,
                markeredgewidth=2.0 if is_sel else 1.2,
                markersize=size,
                linestyle="None",
                zorder=7 if is_sel else 6,
            )
            self._via_patches.append(artist)
            if show_labels:
                lbl = self._ax.text(
                    v["x"], v["y"], str(v["idx"]),
                    color="#ffffff", fontsize=7,
                    ha="center", va="center", zorder=8,
                    fontweight="bold")
                self._via_labels.append(lbl)

        self._canvas.draw_idle()

    def _redraw_windows(self) -> None:
        for p in self._window_patches:
            try: p.remove()
            except Exception: pass
        for t in self._window_labels:
            try: t.remove()
            except Exception: pass
        self._window_patches.clear()
        self._window_labels.clear()

        if not self._show_windows or self._board is None:
            self._canvas.draw_idle()
            return

        for w in self._windows:
            col = _WINDOW_POS if w.sigma > 0 else _WINDOW_NEG
            rect = mpatches.Rectangle(
                (w.x_min_mm, w.y_min_mm),
                w.x_max_mm - w.x_min_mm,
                w.y_max_mm - w.y_min_mm,
                linewidth=2, edgecolor=col, facecolor=col,
                alpha=0.22, zorder=3)
            self._ax.add_patch(rect)
            self._window_patches.append(rect)
            cx = (w.x_min_mm + w.x_max_mm) / 2
            cy = (w.y_min_mm + w.y_max_mm) / 2
            lbl = self._ax.text(
                cx, cy,
                f"{w.window_id}\nσ={'+1' if w.sigma > 0 else '-1'}",
                color=col, fontsize=7, ha="center", va="center",
                fontweight="bold", zorder=7)
            self._window_labels.append(lbl)
        self._canvas.draw_idle()

    # ==================================================================
    # Picking
    # ==================================================================
    def _find_nearest_segment(self, x: float, y: float,
                              max_dist: float) -> str | None:
        """Lot-Abstand Punkt-Segment.  ``max_dist`` in Datenkoordinaten."""
        if self._segments.shape[0] == 0:
            return None
        p = np.array([x, y])
        best_i = -1
        best_d = max_dist
        # Vektorisiert: fuer alle Segmente gleichzeitig
        a = self._segments[:, :2]
        b = self._segments[:, 2:]
        ab = b - a
        ap = p - a
        ab_len2 = np.einsum("ij,ij->i", ab, ab)
        ab_len2 = np.where(ab_len2 < 1e-12, 1e-12, ab_len2)
        t = np.einsum("ij,ij->i", ap, ab) / ab_len2
        t = np.clip(t, 0.0, 1.0)
        foot = a + ab * t[:, None]
        d = np.linalg.norm(p - foot, axis=1)

        # Nur sichtbare Layer zulassen
        for i, fid in enumerate(self._feature_ids):
            if not self._layer_visible.get(self._feature_layers[i], True):
                continue
            if d[i] < best_d:
                best_d = d[i]
                best_i = i
        return self._feature_ids[best_i] if best_i >= 0 else None

    def _find_nearest_via(self, x: float, y: float,
                          max_dist: float) -> str | None:
        best = None
        best_d = max_dist
        for v in self._vias:
            if not self._layer_visible.get(v["layer"], True):
                continue
            d = math.hypot(v["x"] - x, v["y"] - y)
            if d < best_d:
                best_d = d
                best = v["id"]
        return best

    def _pick_tolerance(self) -> float:
        """Klick-Toleranz in Datenkoordinaten (mm)."""
        try:
            x0, x1 = self._ax.get_xlim()
            w = self._ax.bbox.width
            # ~6 Pixel
            return 6.0 * (x1 - x0) / max(w, 1.0)
        except Exception:
            return 0.5

    # ==================================================================
    # Events
    # ==================================================================
    def _on_click(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes is not self._ax:
            return
        if self._interact_mode != "select":
            return
        if event.xdata is None or event.ydata is None:
            return
        if event.button != 1:
            return
        shift = bool(event.key and "shift" in event.key)
        tol = self._pick_tolerance()

        if self._mode == "vias":
            via = self._find_nearest_via(event.xdata, event.ydata, tol * 3)
            if via is not None:
                self.via_clicked.emit(via, event.xdata, event.ydata, shift)
            return

        # leiter
        fid = self._find_nearest_segment(event.xdata, event.ydata, tol)
        if fid is not None:
            self.segment_clicked.emit(fid, shift)

    def _on_motion(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes is not self._ax:
            if self._hover_id:
                self._hover_id = ""
                self._hover_line.set_data([], [])
                self.hover_changed.emit("")
                self._canvas.draw_idle()
            return
        if (event.xdata is None or event.ydata is None or
                self._interact_mode != "select" or self._mode != "leiter"):
            if self._hover_id:
                self._hover_id = ""
                self._hover_line.set_data([], [])
                self.hover_changed.emit("")
                self._canvas.draw_idle()
            return
        tol = self._pick_tolerance()
        fid = self._find_nearest_segment(event.xdata, event.ydata, tol * 1.5)
        if fid == self._hover_id:
            return
        self._hover_id = fid or ""
        if fid is None:
            self._hover_line.set_data([], [])
        else:
            i = self._id_to_idx[fid]
            x1, y1, x2, y2 = self._segments[i]
            self._hover_line.set_data([x1, x2], [y1, y2])
        self.hover_changed.emit(self._hover_id)
        self._canvas.draw_idle()

    # ==================================================================
    # Helfer fuer Tab (Via-Abfrage)
    # ==================================================================
    def via_position(self, via_id: str) -> tuple[float, float] | None:
        for v in self._vias:
            if v["id"] == via_id:
                return v["x"], v["y"]
        return None

    def via_count(self) -> int:
        return len(self._vias)

    def copper_layer_names(self) -> list[str]:
        return list(self._layer_visible.keys())
