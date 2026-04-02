#!/usr/bin/env python
"""
define_windows.py  –  Interaktives Tool zum Definieren von Via-Fenstern.

Workflow:
  1. Board laden und alle Vias anzeigen (nummeriert).
  2. Benutzer klickt zwei Vias an → definiert ein Fenster-Rechteck.
     - Länge = Abstand der beiden Via-Mittelpunkte
     - Höhe  = Via-Höhe aus Stackup (= PCB-Gesamtdicke)
  3. Fenster werden fortlaufend gesammelt und visuell angezeigt.
  4. Am Ende: YAML-Export nach  configs/windows_<design>.yaml

Bedienung:
  - Linksklick auf Via:  markiert Via als Start- oder Endpunkt eines Fensters
  - Taste 'u':           letztes Fenster rückgängig machen (undo)
  - Taste 's':           Fenster als YAML speichern
  - Taste 'q':           Beenden
  - Taste '+'/'-':       σ umschalten (+1 / -1) für das nächste Fenster

Verwendung:
    python scripts/define_windows.py --design 3
    python scripts/define_windows.py --gerber data_samples/gerber/Desgin_01
"""

from __future__ import annotations

import argparse
import io
import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# Windows: stdout auf UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.collections import LineCollection
from matplotlib.widgets import Button
import numpy as np
import yaml

from pcb_rogowski.domain.board.models import Board, Layer, LayerType
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader

# ---------------------------------------------------------------------------
# Stackup-Laden (für Via-Höhe)
# ---------------------------------------------------------------------------

_STACKUP_YAML = _ROOT / "configs" / "stackup_design03.yaml"


def _load_via_height_mm() -> float:
    """Lädt die PCB-Gesamtdicke aus dem Stackup-YAML."""
    try:
        with open(_STACKUP_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return float(data["stackup"]["total_thickness_mm"])
    except Exception:
        print("  [WARNUNG] Stackup nicht geladen – Fallback h_via = 1.12 mm")
        return 1.12268


# ---------------------------------------------------------------------------
# Farben und Konstanten
# ---------------------------------------------------------------------------

_BG_COLOR       = "#1a1a2e"
_PLOT_BG        = "#0d1117"
_VIA_COLOR      = "#00ff88"
_VIA_SELECTED   = "#ff4444"
_WINDOW_COLOR   = "#44aaff"
_WINDOW_NEG     = "#ff8800"
_TRACE_COLOR    = "#334455"
_TEXT_COLOR      = "#ffffff"


# ---------------------------------------------------------------------------
# Via-Sammlung
# ---------------------------------------------------------------------------

def _collect_vias(board: Board) -> list[dict]:
    """
    Sammelt alle Vias aus dem Board und gibt sie als Liste von Dicts zurück.
    Duplikate (gleiche Position) werden zusammengefasst.
    """
    seen: set[tuple[float, float]] = set()
    vias: list[dict] = []

    for layer in board.layers:
        for pad in layer.pads:
            if not pad.is_via:
                continue
            key = (round(pad.center.x_mm, 4), round(pad.center.y_mm, 4))
            if key in seen:
                continue
            seen.add(key)
            vias.append({
                "idx": len(vias),
                "x": pad.center.x_mm,
                "y": pad.center.y_mm,
                "d": pad.diameter_mm,
                "feature_id": pad.feature_id,
                "layer": layer.name,
            })

    # Nach Position sortieren (links→rechts, dann unten→oben)
    vias.sort(key=lambda v: (round(v["x"], 1), round(v["y"], 1)))
    for i, v in enumerate(vias):
        v["idx"] = i

    return vias


# ---------------------------------------------------------------------------
# Fenster-Datenstruktur
# ---------------------------------------------------------------------------

class WindowDef:
    """Ein manuell definiertes Fenster zwischen zwei Vias."""

    def __init__(self, via_a: dict, via_b: dict, sigma: int, h_via_mm: float, wid: str):
        self.via_a = via_a
        self.via_b = via_b
        self.sigma = sigma
        self.h_via_mm = h_via_mm
        self.window_id = wid

        # Bounding-Box (2D-Projektion auf die PCB-Ebene)
        self.x_min = min(via_a["x"], via_b["x"])
        self.x_max = max(via_a["x"], via_b["x"])
        self.y_min = min(via_a["y"], via_b["y"])
        self.y_max = max(via_a["y"], via_b["y"])

        # Abstand
        self.dist_mm = math.hypot(via_b["x"] - via_a["x"],
                                   via_b["y"] - via_a["y"])

    def to_dict(self) -> dict:
        return {
            "window_id": self.window_id,
            "x_min_mm": round(self.x_min, 4),
            "y_min_mm": round(self.y_min, 4),
            "x_max_mm": round(self.x_max, 4),
            "y_max_mm": round(self.y_max, 4),
            "sigma": self.sigma,
            "h_via_mm": round(self.h_via_mm, 5),
            "dist_mm": round(self.dist_mm, 4),
            "via_a_idx": self.via_a["idx"],
            "via_b_idx": self.via_b["idx"],
            "via_a_xy": [round(self.via_a["x"], 4), round(self.via_a["y"], 4)],
            "via_b_xy": [round(self.via_b["x"], 4), round(self.via_b["y"], 4)],
        }


# ---------------------------------------------------------------------------
# Interaktiver Viewer
# ---------------------------------------------------------------------------

class WindowDefiner:
    """
    Interaktives Matplotlib-Tool zum Definieren von Via-Fenstern.

    Anklicken von zwei Vias definiert ein Fenster (Rechteck).
    """

    def __init__(self, board: Board, vias: list[dict], h_via_mm: float,
                 design_name: str) -> None:
        self.board = board
        self.vias = vias
        self.h_via_mm = h_via_mm
        self.design_name = design_name

        self.windows: list[WindowDef] = []
        self.current_sigma = +1
        self._selected_via: dict | None = None  # erster Via eines Paares
        self._selected_artist = None

        self._via_artists: list = []        # Kreis-Patches der Vias
        self._via_labels: list = []         # Text-Labels der Vias
        self._window_patches: list = []     # Rechteck-Patches der Fenster
        self._window_labels: list = []      # Fenster-Beschriftungen

        self._pick_radius = 0.8  # mm – Klick-Radius für Via-Auswahl

        self._build_figure()

    def _build_figure(self) -> None:
        plt.style.use("dark_background")

        self.fig = plt.figure(figsize=(18, 10), facecolor=_BG_COLOR)
        self.fig.canvas.manager.set_window_title(
            f"Fenster-Definition – {self.design_name}"
        )

        # Haupt-Plot
        self.ax = self.fig.add_axes((0.03, 0.08, 0.70, 0.88))
        self.ax.set_facecolor(_PLOT_BG)
        self.ax.set_aspect("equal")
        self.ax.set_xlabel("x [mm]", color="white")
        self.ax.set_ylabel("y [mm]", color="white")
        self.ax.tick_params(colors="white")

        # Leiterbahnen dezent im Hintergrund
        self._draw_traces()

        # Vias zeichnen (klickbar)
        self._draw_vias()

        # Board-Outline
        if self.board.outline_mm:
            x0, y0, x1, y1 = self.board.outline_mm
            rect = mpatches.FancyBboxPatch(
                (x0, y0), x1 - x0, y1 - y0,
                boxstyle="square,pad=0", linewidth=1.5,
                edgecolor="#555", facecolor="none", zorder=1,
            )
            self.ax.add_patch(rect)

        self._autoscale()

        # Info-Panel rechts
        self._build_info_panel()

        # Status-Zeile unten
        self.status_text = self.fig.text(
            0.03, 0.02, self._status_msg(),
            color="#aaa", fontsize=9, fontfamily="monospace",
            transform=self.fig.transFigure,
        )

        # Koordinaten
        self.coord_text = self.fig.text(
            0.50, 0.02, "", color="#666", fontsize=8,
            transform=self.fig.transFigure,
        )

        # Buttons
        self._build_buttons()

        # Events
        self.fig.canvas.mpl_connect("button_press_event", self._on_click)
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.fig.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

    def _draw_traces(self) -> None:
        """Zeichnet alle Kupfer-Leiterbahnen dezent im Hintergrund."""
        for layer in self.board.layers:
            if layer.layer_type != LayerType.COPPER or not layer.lines:
                continue
            segments = [
                [(f.start.x_mm, f.start.y_mm), (f.end.x_mm, f.end.y_mm)]
                for f in layer.lines
            ]
            lw = max(layer.lines[0].width_mm * 1.0, 0.2)
            coll = LineCollection(segments, colors=_TRACE_COLOR,
                                  linewidths=lw, alpha=0.4, zorder=2)
            self.ax.add_collection(coll)

    def _draw_vias(self) -> None:
        """Zeichnet alle Vias als klickbare Kreise mit Index-Nummer."""
        for v in self.vias:
            r = max(v["d"] / 2, 0.08)
            circle = mpatches.Circle(
                (v["x"], v["y"]), r,
                facecolor=_VIA_COLOR, edgecolor="white",
                linewidth=0.5, alpha=0.8, zorder=5,
            )
            self.ax.add_patch(circle)
            self._via_artists.append(circle)

            # Nummer des Vias
            txt = self.ax.text(
                v["x"], v["y"] + r + 0.08, str(v["idx"]),
                color=_VIA_COLOR, fontsize=5, ha="center", va="bottom",
                zorder=6, fontweight="bold",
            )
            self._via_labels.append(txt)

    def _autoscale(self) -> None:
        if self.board.outline_mm:
            x0, y0, x1, y1 = self.board.outline_mm
            m = max(x1 - x0, y1 - y0) * 0.05
            self.ax.set_xlim(x0 - m, x1 + m)
            self.ax.set_ylim(y0 - m, y1 + m)
        else:
            self.ax.autoscale_view()

    # ------------------------------------------------------------------
    # Info-Panel
    # ------------------------------------------------------------------

    def _build_info_panel(self) -> None:
        self.info_ax = self.fig.add_axes((0.75, 0.08, 0.24, 0.88),
                                          facecolor="#16213e")
        self.info_ax.set_xlim(0, 1)
        self.info_ax.set_ylim(0, 1)
        self.info_ax.axis("off")
        self._update_info_panel()

    def _update_info_panel(self) -> None:
        self.info_ax.clear()
        self.info_ax.set_xlim(0, 1)
        self.info_ax.set_ylim(0, 1)
        self.info_ax.axis("off")

        y = 0.96
        dy = 0.028

        self.info_ax.text(0.05, y, "Fenster-Definition", color="white",
                          fontsize=11, fontweight="bold")
        y -= dy * 1.5

        self.info_ax.text(0.05, y, f"Design: {self.design_name}", color="#aaa",
                          fontsize=8)
        y -= dy
        self.info_ax.text(0.05, y, f"Vias: {len(self.vias)}  |  "
                          f"h_via: {self.h_via_mm:.3f} mm", color="#aaa",
                          fontsize=8)
        y -= dy
        self.info_ax.text(0.05, y, f"σ aktuell: {'+1' if self.current_sigma == 1 else '-1'}",
                          color=_WINDOW_COLOR if self.current_sigma == 1 else _WINDOW_NEG,
                          fontsize=9, fontweight="bold")
        y -= dy * 1.5

        # Tastenbelegung
        self.info_ax.text(0.05, y, "Tasten:", color="white", fontsize=9,
                          fontweight="bold")
        y -= dy
        keys = [
            ("Klick Via",  "Fenster-Punkt setzen"),
            ("+  /  -",    "σ umschalten"),
            ("u",          "Undo (letztes Fenster)"),
            ("s",          "Speichern (YAML)"),
            ("q",          "Beenden"),
        ]
        for k, desc in keys:
            self.info_ax.text(0.07, y, f"{k:12s}  {desc}",
                              color="#8899aa", fontsize=7, fontfamily="monospace")
            y -= dy

        y -= dy
        self.info_ax.text(0.05, y, f"Definierte Fenster: {len(self.windows)}",
                          color="white", fontsize=9, fontweight="bold")
        y -= dy

        for i, w in enumerate(self.windows):
            sigma_str = f"σ={'+1' if w.sigma == 1 else '-1'}"
            color = _WINDOW_COLOR if w.sigma == 1 else _WINDOW_NEG
            txt = (f"W{i}: Via {w.via_a['idx']}→{w.via_b['idx']}  "
                   f"d={w.dist_mm:.2f}mm  {sigma_str}")
            self.info_ax.text(0.07, y, txt, color=color, fontsize=6.5,
                              fontfamily="monospace")
            y -= dy
            if y < 0.02:
                self.info_ax.text(0.07, y, "...", color="#666", fontsize=7)
                break

        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def _build_buttons(self) -> None:
        # Sigma-Toggle
        ax_sigma = self.fig.add_axes((0.75, 0.02, 0.08, 0.04))
        self.btn_sigma = Button(ax_sigma, "σ: +1", color="#2c3e50",
                                 hovercolor="#3d5a80")
        self.btn_sigma.label.set_color("white")
        self.btn_sigma.label.set_fontsize(9)
        self.btn_sigma.on_clicked(self._toggle_sigma)

        # Save
        ax_save = self.fig.add_axes((0.84, 0.02, 0.06, 0.04))
        self.btn_save = Button(ax_save, "Speichern", color="#1a6b3c",
                                hovercolor="#27ae60")
        self.btn_save.label.set_color("white")
        self.btn_save.label.set_fontsize(9)
        self.btn_save.on_clicked(lambda _: self._save_yaml())

        # Undo
        ax_undo = self.fig.add_axes((0.91, 0.02, 0.06, 0.04))
        self.btn_undo = Button(ax_undo, "Undo", color="#6b1a1a",
                                hovercolor="#c0392b")
        self.btn_undo.label.set_color("white")
        self.btn_undo.label.set_fontsize(9)
        self.btn_undo.on_clicked(lambda _: self._undo())

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_click(self, event) -> None:
        """Klick auf einen Via → markieren oder Fenster erstellen."""
        if event.inaxes is not self.ax or event.button != 1:
            return
        if event.xdata is None:
            return

        # Nächsten Via finden
        click_x, click_y = event.xdata, event.ydata
        best_via = None
        best_dist = float("inf")
        for v in self.vias:
            d = math.hypot(v["x"] - click_x, v["y"] - click_y)
            if d < best_dist:
                best_dist = d
                best_via = v

        # Zu weit weg?
        if best_via is None or best_dist > self._pick_radius:
            return

        if self._selected_via is None:
            # Erster Via → markieren
            self._selected_via = best_via
            self._via_artists[best_via["idx"]].set_facecolor(_VIA_SELECTED)
            self._via_artists[best_via["idx"]].set_edgecolor(_VIA_SELECTED)
            self.status_text.set_text(
                f"Via {best_via['idx']} ausgewählt  "
                f"({best_via['x']:.3f}, {best_via['y']:.3f}) – "
                f"klicke zweiten Via für Fenster"
            )
        else:
            # Zweiter Via → Fenster definieren
            if best_via["idx"] == self._selected_via["idx"]:
                return  # gleicher Via

            wid = f"W{len(self.windows)}"
            wdef = WindowDef(
                self._selected_via, best_via,
                sigma=self.current_sigma,
                h_via_mm=self.h_via_mm,
                wid=wid,
            )
            self.windows.append(wdef)

            # Fenster-Rechteck zeichnen
            self._draw_window(wdef)

            # Ersten Via zurücksetzen
            self._via_artists[self._selected_via["idx"]].set_facecolor(_VIA_COLOR)
            self._via_artists[self._selected_via["idx"]].set_edgecolor("white")
            self._selected_via = None

            self.status_text.set_text(self._status_msg())
            self._update_info_panel()

            print(f"  [+] Fenster {wid}: Via {wdef.via_a['idx']} → "
                  f"Via {wdef.via_b['idx']}  "
                  f"d={wdef.dist_mm:.3f} mm  σ={wdef.sigma:+d}")

        self.fig.canvas.draw_idle()

    def _on_key(self, event) -> None:
        if event.key in ("+", "="):
            self.current_sigma = +1
            self._update_sigma_display()
        elif event.key == "-":
            self.current_sigma = -1
            self._update_sigma_display()
        elif event.key == "u":
            self._undo()
        elif event.key == "s":
            self._save_yaml()
        elif event.key == "q":
            plt.close(self.fig)

    def _on_mouse_move(self, event) -> None:
        if event.inaxes is self.ax and event.xdata is not None:
            # Nächsten Via finden
            best_via = None
            best_dist = float("inf")
            for v in self.vias:
                d = math.hypot(v["x"] - event.xdata, v["y"] - event.ydata)
                if d < best_dist:
                    best_dist = d
                    best_via = v

            if best_via and best_dist < self._pick_radius:
                self.coord_text.set_text(
                    f"Via {best_via['idx']}  "
                    f"({best_via['x']:.3f}, {best_via['y']:.3f})  "
                    f"d={best_via['d']:.3f} mm"
                )
            else:
                self.coord_text.set_text(
                    f"x={event.xdata:.3f}  y={event.ydata:.3f} mm"
                )
            self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Zeichnen & UI-Helfer
    # ------------------------------------------------------------------

    def _draw_window(self, w: WindowDef) -> None:
        """Zeichnet ein Fenster-Rechteck auf den Plot."""
        color = _WINDOW_COLOR if w.sigma == 1 else _WINDOW_NEG
        rect = mpatches.Rectangle(
            (w.x_min, w.y_min),
            w.x_max - w.x_min,
            w.y_max - w.y_min,
            linewidth=2, edgecolor=color, facecolor=color,
            alpha=0.2, zorder=4,
        )
        self.ax.add_patch(rect)
        self._window_patches.append(rect)

        # Beschriftung
        cx = (w.x_min + w.x_max) / 2
        cy = (w.y_min + w.y_max) / 2
        sigma_str = f"σ={'+1' if w.sigma == 1 else '-1'}"
        txt = self.ax.text(
            cx, cy, f"{w.window_id}\n{sigma_str}",
            color=color, fontsize=7, ha="center", va="center",
            fontweight="bold", zorder=7,
        )
        self._window_labels.append(txt)

    def _toggle_sigma(self, _event=None) -> None:
        self.current_sigma *= -1
        self._update_sigma_display()

    def _update_sigma_display(self) -> None:
        s = "+1" if self.current_sigma == 1 else "-1"
        self.btn_sigma.label.set_text(f"σ: {s}")
        color = _WINDOW_COLOR if self.current_sigma == 1 else _WINDOW_NEG
        self.btn_sigma.label.set_color(color)
        self.status_text.set_text(self._status_msg())
        self._update_info_panel()
        self.fig.canvas.draw_idle()

    def _undo(self) -> None:
        if not self.windows:
            return
        removed = self.windows.pop()
        # Letzten Patch und Label entfernen
        if self._window_patches:
            p = self._window_patches.pop()
            p.remove()
        if self._window_labels:
            t = self._window_labels.pop()
            t.remove()
        # Selektion zurücksetzen
        if self._selected_via is not None:
            self._via_artists[self._selected_via["idx"]].set_facecolor(_VIA_COLOR)
            self._via_artists[self._selected_via["idx"]].set_edgecolor("white")
            self._selected_via = None

        self.status_text.set_text(
            f"Fenster {removed.window_id} entfernt.  "
            f"Verbleibend: {len(self.windows)}"
        )
        self._update_info_panel()
        self.fig.canvas.draw_idle()
        print(f"  [-] Fenster {removed.window_id} entfernt.")

    def _status_msg(self) -> str:
        sigma_str = f"σ={'+1' if self.current_sigma == 1 else '-1'}"
        return (f"{len(self.windows)} Fenster definiert  |  "
                f"Nächstes Fenster: {sigma_str}  |  "
                f"Klicke zwei Vias um ein Fenster zu definieren")

    # ------------------------------------------------------------------
    # YAML-Export
    # ------------------------------------------------------------------

    def _save_yaml(self) -> None:
        if not self.windows:
            print("  [!] Keine Fenster definiert – nichts zu speichern.")
            return

        out_dir = _ROOT / "configs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"windows_{self.design_name}.yaml"

        data = {
            "design": self.design_name,
            "h_via_mm": round(self.h_via_mm, 5),
            "n_windows": len(self.windows),
            "note": "Manuell definierte Via-Fenster für M-Berechnung",
            "windows": [w.to_dict() for w in self.windows],
        }

        with open(out_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                      sort_keys=False)

        print(f"\n  [✓] {len(self.windows)} Fenster gespeichert: {out_path}")
        self.status_text.set_text(f"Gespeichert: {out_path.name}")
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Laden bestehender YAML
    # ------------------------------------------------------------------

    def load_existing(self) -> None:
        """Lädt eine vorhandene Fenster-YAML und stellt die Fenster wieder her."""
        yaml_path = _ROOT / "configs" / f"windows_{self.design_name}.yaml"
        if not yaml_path.exists():
            return

        print(f"  [i] Lade bestehende Fenster: {yaml_path}")
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for wd in data.get("windows", []):
            via_a_idx = wd.get("via_a_idx")
            via_b_idx = wd.get("via_b_idx")
            if via_a_idx is None or via_b_idx is None:
                continue
            if via_a_idx >= len(self.vias) or via_b_idx >= len(self.vias):
                print(f"    [!] Via-Index außerhalb des Bereichs: "
                      f"{via_a_idx}, {via_b_idx} (max {len(self.vias)-1})")
                continue

            wid = wd.get("window_id", f"W{len(self.windows)}")
            wdef = WindowDef(
                self.vias[via_a_idx],
                self.vias[via_b_idx],
                sigma=wd.get("sigma", +1),
                h_via_mm=self.h_via_mm,
                wid=wid,
            )
            self.windows.append(wdef)
            self._draw_window(wdef)

        if self.windows:
            print(f"  [i] {len(self.windows)} Fenster geladen.")
            self._update_info_panel()
            self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------

    def show(self) -> None:
        plt.show()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _design_dir(design_key: str) -> Path:
    """Gibt den Pfad zum Gerber-Verzeichnis eines Designs zurück."""
    gerber_root = _ROOT / "data_samples" / "gerber"
    # Versuche beide Schreibweisen
    for name in [f"Desgin_0{design_key}", f"Design_0{design_key}",
                 f"Desgin_{design_key}", f"Design_{design_key}"]:
        p = gerber_root / name
        if p.is_dir():
            return p
    raise FileNotFoundError(
        f"Kein Gerber-Verzeichnis für Design {design_key} gefunden in {gerber_root}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Interaktives Tool zum Definieren von Via-Fenstern für die "
                    "M-Berechnung (Rogowski-Spule).",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--design", "-d", type=str,
                       help="Design-Nummer (1, 2 oder 3)")
    group.add_argument("--gerber", "-g", type=Path,
                       help="Pfad zum Gerber-Verzeichnis")
    p.add_argument("--dpi", type=int, default=100,
                   help="Bildschirm-DPI (Standard: 100)")
    p.add_argument("--pick-radius", type=float, default=None,
                   help="Klick-Radius für Via-Auswahl [mm] (auto wenn nicht gesetzt)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    # Gerber-Verzeichnis
    if args.design:
        gerber_dir = _design_dir(args.design)
        design_name = f"Design_{args.design}"
    else:
        gerber_dir = args.gerber.resolve()
        design_name = gerber_dir.name

    print(f"Lade Board: {gerber_dir}")
    board = GerberBoardLoader().load_from_gerber(gerber_dir)

    n_lines = sum(len(la.lines) for la in board.layers)
    n_pads = sum(len(la.pads) for la in board.layers)
    print(f"  → {board.name}  |  {n_lines} Linien  |  {n_pads} Pads")

    # Vias sammeln
    vias = _collect_vias(board)
    print(f"  → {len(vias)} eindeutige Vias gefunden")

    if not vias:
        print("  [FEHLER] Keine Vias im Board gefunden!")
        sys.exit(1)

    # Via-Höhe laden
    h_via_mm = _load_via_height_mm()
    print(f"  → h_via = {h_via_mm:.5f} mm (PCB-Gesamtdicke)")

    # Pick-Radius: automatisch aus Via-Abständen berechnen
    if args.pick_radius is not None:
        pick_r = args.pick_radius
    else:
        # Mittlerer Via-Durchmesser * 2 als Klickradius
        avg_d = sum(v["d"] for v in vias) / len(vias)
        pick_r = max(avg_d * 2.0, 0.3)
    print(f"  → Klick-Radius: {pick_r:.3f} mm")

    # Viewer starten
    plt.rcParams["figure.dpi"] = args.dpi
    definer = WindowDefiner(board, vias, h_via_mm, design_name)
    definer._pick_radius = pick_r

    # Bestehende Fenster laden
    definer.load_existing()

    print("\n  Bedienung:")
    print("    Klick auf Via  →  Start-/Endpunkt für Fenster")
    print("    +/-            →  σ umschalten")
    print("    u              →  Undo")
    print("    s              →  Speichern (YAML)")
    print("    q              →  Beenden")
    print()

    definer.show()


if __name__ == "__main__":
    main()
