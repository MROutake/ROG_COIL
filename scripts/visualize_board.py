"""
Board-Visualisierung: Gerber (Altium-Export) → interaktives Matplotlib-Fenster.

Verwendung
----------
    python scripts/visualize_board.py
    python scripts/visualize_board.py --gerber data_samples/gerber/Desgin_03
    python scripts/visualize_board.py --gerber path/to/gerber --dpi 150

Features
--------
- Alle Lagen werden in unterschiedlichen Farben dargestellt
- Checkbox-Panel zum Ein-/Ausblenden einzelner Lagen
- Outline (Board-Kontur) immer sichtbar
- Zoom / Pan mit Mausrad und Maus
- Statusleiste zeigt Maus-Koordinaten in mm
- Schaltflächen: "Alles ein", "Alles aus", "Nur Kupfer"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Workspace-Root zum sys.path hinzufügen (damit pcb_rogowski gefunden wird,
# auch wenn das Paket nicht mit pip -e installiert wurde)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from matplotlib.axes import Axes
from matplotlib.widgets import CheckButtons, Button
from matplotlib.collections import LineCollection
import numpy as np

from pcb_rogowski.domain.board.models import Board, Layer, LayerType
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Farb-Palette – eine Farbe pro Lagenkategorie
_LAYER_COLORS: dict[str, str] = {
    "top_layer":      "#e63946",   # Rot
    "mid-layer_1":    "#f4a261",   # Orange
    "mid-layer_2":    "#2a9d8f",   # Grün-Teal
    "bottom_layer":   "#457b9d",   # Blau
    "drill_plated_bottom_layer-top_layer": "#a8dadc",   # Hellblau
    "drill_non-plated_bottom_layer-top_layer": "#a8dadc",
    "top_overlay":    "#6a4c93",   # Violett
    "bottom_overlay": "#c77dff",
    "top_solder":     "#b5838d",   # Rosa
    "bottom_solder":  "#e5989b",
    "top_paste":      "#ffe8a1",
    "bottom_paste":   "#fff3b0",
}
_FALLBACK_COLORS = [
    "#e63946", "#f4a261", "#2a9d8f", "#457b9d",
    "#a8dadc", "#6a4c93", "#c77dff", "#b5838d",
    "#48cae4", "#90e0ef",
]

_OUTLINE_COLOR = "#1d1d1b"
_BACKGROUND    = "#1a1a2e"
_PANEL_BG      = "#16213e"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _assign_colors(layers: list[Layer]) -> dict[str, str]:
    """Weist jeder Lage eine Farbe zu."""
    colors: dict[str, str] = {}
    fallback_idx = 0
    for layer in layers:
        if layer.name in _LAYER_COLORS:
            colors[layer.name] = _LAYER_COLORS[layer.name]
        else:
            colors[layer.name] = _FALLBACK_COLORS[fallback_idx % len(_FALLBACK_COLORS)]
            fallback_idx += 1
    return colors


def _build_line_collection(layer: Layer, color: str) -> LineCollection:
    """
    Baut eine LineCollection für alle Leiterbahnen einer Lage.
    Das ist deutlich schneller als ax.plot() pro Segment.
    """
    segments = [
        [(f.start.x_mm, f.start.y_mm), (f.end.x_mm, f.end.y_mm)]
        for f in layer.lines
    ]
    lw = max(layer.lines[0].width_mm * 1.5, 0.3) if layer.lines else 0.5
    coll = LineCollection(
        segments,
        colors=color,
        linewidths=lw,
        alpha=0.85,
        capstyle="round",
    )
    return coll


def _draw_pads(ax: Axes, layer: Layer, color: str) -> list:
    """Zeichnet alle Pads/Vias einer Lage als Kreise."""
    artists = []
    for pad in layer.pads:
        r = max(pad.diameter_mm / 2, 0.05)
        circle = mpatches.Circle(
            (pad.center.x_mm, pad.center.y_mm),
            r,
            color=color,
            alpha=0.7,
            linewidth=0,
        )
        ax.add_patch(circle)
        artists.append(circle)
    return artists


def _draw_outline(ax: Axes, board: Board) -> None:
    """Zeichnet die Board-Außenkontur."""
    if board.outline_mm is None:
        return
    x0, y0, x1, y1 = board.outline_mm
    rect = mpatches.FancyBboxPatch(
        (x0, y0),
        x1 - x0,
        y1 - y0,
        boxstyle="square,pad=0",
        linewidth=2,
        edgecolor=_OUTLINE_COLOR,
        facecolor="none",
        zorder=10,
        label="Outline",
    )
    ax.add_patch(rect)


# ---------------------------------------------------------------------------
# Haupt-Visualisierer
# ---------------------------------------------------------------------------

class BoardViewer:
    """
    Interaktiver Board-Viewer mit Lagen-Checkboxen.

    Verwendung::

        viewer = BoardViewer(board)
        viewer.show()
    """

    def __init__(self, board: Board) -> None:
        self.board = board
        self.colors = _assign_colors(board.layers)

        # Nur Lagen mit Features anzeigen (leere Lagen werden trotzdem in der
        # Checkbox-Liste aufgeführt, haben aber nichts zum Zeichnen)
        self.visible_layers: dict[str, bool] = {
            la.name: True for la in board.layers
        }

        # Artists pro Lage speichern (für späteres Ein-/Ausblenden)
        # Wert: Liste aus LineCollection + Circle-Patches
        self._artists: dict[str, list] = {}

        self._build_figure()

    # ------------------------------------------------------------------
    # Figure aufbauen
    # ------------------------------------------------------------------

    def _build_figure(self) -> None:
        plt.style.use("dark_background")

        # Layout: Hauptplot links, Checkbox-Panel rechts
        self.fig = plt.figure(
            figsize=(16, 9),
            facecolor=_BACKGROUND,
        )
        self.fig.canvas.manager.set_window_title(  # type: ignore[union-attr]
            f"PCB Board Viewer – {self.board.name}"
        )

        # Haupt-Axes (Board-Plot)
        self.ax: Axes = self.fig.add_axes((0.0, 0.05, 0.72, 0.90))
        self.ax.set_facecolor("#0d1117")
        self.ax.set_aspect("equal")
        self.ax.set_xlabel("x [mm]", color="white")
        self.ax.set_ylabel("y [mm]", color="white")
        self.ax.tick_params(colors="white")
        for spine in self.ax.spines.values():
            spine.set_edgecolor("#444")

        # Board-Titel
        self.ax.set_title(
            f"{self.board.name}  |  "
            f"{len(self.board.copper_layers)} Kupferlagen  |  "
            f"{sum(len(la.lines) for la in self.board.layers):,} Segmente",
            color="white",
            fontsize=11,
            pad=8,
        )

        # Alle Lagen zeichnen
        self._draw_all_layers()
        _draw_outline(self.ax, self.board)
        self._autoscale()

        # Koordinatenanzeige in der Statusleiste
        self.coord_text = self.fig.text(
            0.01, 0.01, "x=—  y=—  mm",
            color="#aaa", fontsize=8,
            transform=self.fig.transFigure,
        )
        self.fig.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

        # Checkbox-Panel aufbauen
        self._build_checkbox_panel()

        # Schaltflächen aufbauen
        self._build_buttons()

    def _draw_all_layers(self) -> None:
        """Zeichnet alle Lagen und speichert Artists."""
        for layer in self.board.layers:
            color = self.colors[layer.name]
            layer_artists: list = []

            if layer.lines:
                coll = _build_line_collection(layer, color)
                self.ax.add_collection(coll)
                layer_artists.append(coll)

            if layer.pads:
                pad_artists = _draw_pads(self.ax, layer, color)
                layer_artists.extend(pad_artists)

            self._artists[layer.name] = layer_artists

    def _autoscale(self) -> None:
        """Setzt Zoom auf Board-Outline bzw. auf alle Features."""
        if self.board.outline_mm:
            x0, y0, x1, y1 = self.board.outline_mm
            margin = max((x1 - x0), (y1 - y0)) * 0.05
            self.ax.set_xlim(x0 - margin, x1 + margin)
            self.ax.set_ylim(y0 - margin, y1 + margin)
        else:
            self.ax.autoscale_view()

    # ------------------------------------------------------------------
    # Checkbox-Panel
    # ------------------------------------------------------------------

    def _build_checkbox_panel(self) -> None:
        """Baut das Lagen-Checkbox-Panel rechts neben dem Plot."""
        layers = self.board.layers
        n = len(layers)

        # Dynamische Höhe: max 30 Lagen passen gut auf den Screen
        row_height = min(0.030, 0.85 / max(n, 1))
        panel_height = row_height * n + 0.04
        panel_top = 0.92
        panel_bottom = panel_top - panel_height

        ax_check = self.fig.add_axes(
            (0.74, max(panel_bottom, 0.08), 0.25, min(panel_height, 0.84)),
            facecolor=_PANEL_BG,
        )

        labels = [la.name for la in layers]
        visibility = [self.visible_layers[name] for name in labels]

        # Farb-Patches als Beschriftungs-Proxies
        label_colors = [self.colors[name] for name in labels]

        self._checkbuttons = CheckButtons(
            ax_check,
            labels,
            visibility,
            frame_props={"facecolor": label_colors, "edgecolor": "none", "alpha": 0.8},
            label_props={"color": label_colors},
        )
        for lbl in self._checkbuttons.labels:
            lbl.set_fontsize(7.5)

        # Titelzeile über dem Panel
        ax_check.set_title("Lagen", color="white", fontsize=9, pad=4)

        self._checkbuttons.on_clicked(self._on_layer_toggle)

    # ------------------------------------------------------------------
    # Schaltflächen
    # ------------------------------------------------------------------

    def _build_buttons(self) -> None:
        """Erstellt 'Alles ein', 'Alles aus', 'Nur Kupfer' Buttons."""
        btn_y = 0.025
        btn_h = 0.04
        for i, (label, callback) in enumerate([
            ("Alles ein",   self._btn_all_on),
            ("Alles aus",   self._btn_all_off),
            ("Nur Kupfer",  self._btn_only_copper),
        ]):
            ax_btn = self.fig.add_axes((0.74 + i * 0.085, btn_y, 0.08, btn_h))
            btn = Button(ax_btn, label, color="#2c3e50", hovercolor="#3d5a80")
            btn.label.set_fontsize(7.5)
            btn.label.set_color("white")
            btn.on_clicked(callback)
            # Referenz halten, damit GC sie nicht löscht
            setattr(self, f"_btn_{i}", btn)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_layer_toggle(self, label: str | None) -> None:
        """Wird aufgerufen wenn eine Checkbox geklickt wird."""
        if label is None:
            return
        self.visible_layers[label] = not self.visible_layers[label]
        visible = self.visible_layers[label]
        for artist in self._artists.get(label, []):
            artist.set_visible(visible)
        self.fig.canvas.draw_idle()

    def _on_mouse_move(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes is self.ax and event.xdata is not None:
            self.coord_text.set_text(
                f"x = {event.xdata:8.3f} mm   y = {event.ydata:8.3f} mm"
            )
            self.fig.canvas.draw_idle()

    def _btn_all_on(self, _event) -> None:  # type: ignore[no-untyped-def]
        self._set_all_layers(visible=True)

    def _btn_all_off(self, _event) -> None:  # type: ignore[no-untyped-def]
        self._set_all_layers(visible=False)

    def _btn_only_copper(self, _event) -> None:  # type: ignore[no-untyped-def]
        for layer in self.board.layers:
            is_copper = layer.layer_type == LayerType.COPPER
            self.visible_layers[layer.name] = is_copper
            for artist in self._artists.get(layer.name, []):
                artist.set_visible(is_copper)
        self._sync_checkboxes()
        self.fig.canvas.draw_idle()

    def _set_all_layers(self, *, visible: bool) -> None:
        for layer in self.board.layers:
            self.visible_layers[layer.name] = visible
            for artist in self._artists.get(layer.name, []):
                artist.set_visible(visible)
        self._sync_checkboxes()
        self.fig.canvas.draw_idle()

    def _sync_checkboxes(self) -> None:
        """Synchronisiert den visuellen Checkbox-Status mit visible_layers."""
        current = list(self._checkbuttons.get_status())
        # Callbacks vorübergehend deaktivieren
        self._checkbuttons.eventson = False
        for i, layer in enumerate(self.board.layers):
            should_be = self.visible_layers[layer.name]
            if current[i] != should_be:
                self._checkbuttons.set_active(i, should_be)
        self._checkbuttons.eventson = True

    # ------------------------------------------------------------------

    def show(self) -> None:
        """Öffnet das Fenster."""
        plt.show()


# ---------------------------------------------------------------------------
# CLI-Einstiegspunkt
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interaktiver PCB Board Viewer (Gerber / Altium-Export)",
    )
    parser.add_argument(
        "--gerber",
        type=Path,
        default=Path("data_samples/gerber/Desgin_03"),
        help="Pfad zum Gerber-Verzeichnis (Altium-Export)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=100,
        help="Bildschirm-DPI (Standard: 100)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print(f"Lade Gerber-Projekt: {args.gerber.resolve()}")
    loader = GerberBoardLoader()

    try:
        board = loader.load_from_gerber(args.gerber.resolve())
    except Exception as exc:
        print(f"  [FEHLER] {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"  -> {board.name}  |  "
        f"{len(board.layers)} Lagen  |  "
        f"{sum(len(la.lines) for la in board.layers):,} Linien  |  "
        f"{sum(len(la.pads)  for la in board.layers):,} Pads"
    )
    if board.outline_mm:
        x0, y0, x1, y1 = board.outline_mm
        print(f"  -> Board-Groesse: {x1-x0:.2f} x {y1-y0:.2f} mm")

    plt.rcParams["figure.dpi"] = args.dpi
    viewer = BoardViewer(board)
    viewer.show()


if __name__ == "__main__":
    main()
