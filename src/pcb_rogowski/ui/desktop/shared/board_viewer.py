"""
Wiederverwendbarer PCB-Viewer (matplotlib-basiert, Dark-tauglich).

Features
--------
* Per-Lage-Farbe, Via-Markierungen, optionale Fensterueberlage.
* Optionales Klick-Picking: Liefert ``feature_id`` der getroffenen Line via
  Qt-Signal ``line_picked``.
* Rollen-Highlighting mit Dark-Palette.
"""

from __future__ import annotations

from typing import Iterable

from matplotlib.patches import Rectangle
from PyQt6.QtCore import pyqtSignal

from pcb_rogowski.domain.board.models import Board, LayerType
from pcb_rogowski.domain.trace.models import ViaWindow
from pcb_rogowski.ui.desktop.shared.mpl_canvas import MplCanvas
from pcb_rogowski.ui.desktop.shared.theme import (
    BORDER,
    ROLE_CONNECTION,
    ROLE_RETURN,
    ROLE_WINDING,
    TEXT_DIM,
)


_LAYER_COLORS = {
    "top_layer":    "#ff7f50",
    "bottom_layer": "#4da3ff",
    "mid-layer_1":  "#4ec9a0",
    "mid-layer_2":  "#c586c0",
}
_DEFAULT_COLOR = "#9aa0a6"

_ROLE_COLOR = {
    "winding":    ROLE_WINDING,
    "return":     ROLE_RETURN,
    "connection": ROLE_CONNECTION,
}


class BoardViewer(MplCanvas):
    """PCB-Viewer fuer Tabs 1, 2 und 3. Emittiert ``line_picked(str)``
    und ``via_picked(str, float, float)`` (id + Position in mm)."""

    line_picked = pyqtSignal(str)  # feature_id
    via_picked = pyqtSignal(str, float, float)  # via_id, x_mm, y_mm

    def __init__(self, parent=None, *, show_toolbar: bool = True,
                 pickable: bool = False) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, show_toolbar=show_toolbar, figsize=(7, 5))
        self._pickable = pickable
        self._line_artists: dict[int, str] = {}
        self._via_artists: dict[int, tuple[str, float, float]] = {}
        if pickable:
            self.canvas.mpl_connect("pick_event", self._on_pick)

    # ------------------------------------------------------------------
    def set_pickable(self, flag: bool) -> None:
        self._pickable = flag

    def render(
        self,
        board: Board | None,
        *,
        active_layers: Iterable[str] | None = None,
        windows: list[ViaWindow] | None = None,
        highlight_roles: dict[str, str] | None = None,
        selected_ids: set[str] | None = None,
        title: str | None = None,
        show_vias: bool = True,
    ) -> None:
        """Zeichnet das Board (dark palette)."""
        self.figure.clear()
        self._line_artists.clear()
        self._via_artists.clear()
        ax = self.figure.add_subplot(111)
        ax.set_aspect("equal", adjustable="datalim")
        ax.grid(True, alpha=0.25)
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("y [mm]")

        if board is None:
            ax.set_title("– kein Design geladen –", color=TEXT_DIM)
            self.canvas.draw_idle()
            return

        active = set(active_layers) if active_layers is not None else None
        sel = selected_ids or set()

        for layer in board.layers:
            if layer.layer_type != LayerType.COPPER:
                continue
            if active is not None and layer.name not in active:
                continue
            col = _LAYER_COLORS.get(layer.name, _DEFAULT_COLOR)

            for ln in layer.lines:
                c = col
                role = None
                if highlight_roles is not None:
                    role = highlight_roles.get(ln.feature_id)
                    if role is not None:
                        c = _ROLE_COLOR.get(role, col)
                lw = max(ln.width_mm * 1.5, 0.8)
                is_sel = ln.feature_id in sel
                edge_lw = lw + 2.0 if is_sel else lw
                line_artist = ax.plot(
                    [ln.start.x_mm, ln.end.x_mm],
                    [ln.start.y_mm, ln.end.y_mm],
                    color=c,
                    linewidth=edge_lw,
                    solid_capstyle="round",
                    picker=5 if self._pickable else False,
                    zorder=3 if is_sel else 2,
                )[0]
                self._line_artists[id(line_artist)] = ln.feature_id

            if show_vias:
                for pad in layer.pads:
                    if pad.is_via:
                        is_sel_via = pad.feature_id in sel
                        via_art = ax.plot(
                            pad.center.x_mm, pad.center.y_mm, "o",
                            markerfacecolor="#ffd447" if is_sel_via else "#1e1f22",
                            markeredgecolor="#e6e6e6",
                            markeredgewidth=1.5 if is_sel_via else 1.0,
                            markersize=max(pad.diameter_mm * 2, 3) + (2 if is_sel_via else 0),
                            picker=6 if self._pickable else False,
                            zorder=5 if is_sel_via else 4,
                        )[0]
                        self._via_artists[id(via_art)] = (
                            pad.feature_id, pad.center.x_mm, pad.center.y_mm,
                        )

        # Fenster
        if windows:
            for w in windows:
                col_pos = "#e6b45a"   # + sigma
                col_neg = "#4da3ff"   # - sigma
                edge = col_pos if w.sigma > 0 else col_neg
                rect = Rectangle(
                    (w.x_min_mm, w.y_min_mm),
                    w.x_max_mm - w.x_min_mm,
                    w.y_max_mm - w.y_min_mm,
                    fill=True, alpha=0.18,
                    facecolor=edge,
                    edgecolor=edge,
                    linewidth=1.3,
                    zorder=1,
                )
                ax.add_patch(rect)
                ax.text(
                    (w.x_min_mm + w.x_max_mm) / 2,
                    (w.y_min_mm + w.y_max_mm) / 2,
                    w.window_id, ha="center", va="center",
                    fontsize=7, color="#e6e6e6",
                )

        if title:
            ax.set_title(title)
        ax.set_facecolor(BORDER)  # leicht getoenter Plot-BG
        self.canvas.draw_idle()

    # ------------------------------------------------------------------
    def _on_pick(self, event) -> None:  # type: ignore[no-untyped-def]
        art = event.artist
        fid = self._line_artists.get(id(art))
        if fid is not None:
            self.line_picked.emit(fid)
            return
        via = self._via_artists.get(id(art))
        if via is not None:
            self.via_picked.emit(via[0], via[1], via[2])
