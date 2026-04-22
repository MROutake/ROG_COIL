"""
Visualisierungen fuer Tab 3 (Analyse).

Dieses Modul buendelt die Matplotlib-Canvases, die in :class:`pcb_rogowski.
ui.desktop.tabs.analysis_tab.AnalysisTab` angezeigt werden:

* :class:`SchematicCanvas`        -- symbolisches L-R-C+M Ersatzschaltbild.
* :class:`WindowGeometryCanvas`   -- massstaeblich skaliertes Windungsfenster
  (Hoehe = :math:`h_{via}`, Breite = Via-zu-Via-Abstand :math:`\\ell`).
* :class:`BFieldCanvas`           -- 2D-Schnitt des Magnetfeldes eines
  antiparallelen Linienleiterpaares; optional wird die **tatsaechliche
  Leiterbahngeometrie** (role-coloriert) und das Fenster-Overlay
  eingeblendet.
* :class:`TransferFunctionCanvas` -- Bode-Diagramm fuer zwei physikalisch
  unterschiedliche Uebertragungsfunktionen des Ersatzschaltbildes:

  * :math:`H(j\\omega) = V_{out}/I_{prim} = j\\omega M /
    (1 - \\omega^2 L C + j\\omega R C)` (Rogowski-Ausgangsspannung),
  * :math:`Z(j\\omega) = (R + j\\omega L) /
    (1 - \\omega^2 L C + j\\omega R C)` (Klemmenimpedanz).

Konvention: Alle Laengen werden in Millimetern uebergeben, elektrische
Groessen in SI-Einheiten (H, F, Ohm, T). Die Umrechnung zu Anzeige-
einheiten (uH, pF, nH) geschieht ausschliesslich in den Canvases.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Arc, Circle, Rectangle

from pcb_rogowski.domain.coil.transfer_function import (
    EquivalentCircuit, impedance_tf, voltage_from_primary_tf,
)
from pcb_rogowski.domain.mutual.calculator import ConductorConfig
from pcb_rogowski.domain.trace.models import ViaWindow
from pcb_rogowski.ui.desktop.shared.mpl_canvas import MplCanvas
from pcb_rogowski.ui.desktop.shared.theme import (
    ACCENT, ACCENT_HI, BG_PANEL, BORDER_HI, ROLE_RETURN, ROLE_WINDING,
    TEXT, TEXT_DIM, WARNING,
)

if TYPE_CHECKING:
    from pcb_rogowski.domain.board.models import Board
    from pcb_rogowski.domain.trace.classifier import ClassificationSpec


# ---------------------------------------------------------------------------
# Rollenfarben (konsistent mit ClassifyCanvas in Tab 2)
# ---------------------------------------------------------------------------

_ROLE_COLORS: dict[str, str] = {
    "winding":    "#00e676",
    "connection": "#546e7a",
    "return":     "#ef5350",
}
_UNCLASSIFIED: str = "#8a5cf6"


# ===================================================================
#  Ersatzschaltbild
# ===================================================================

class SchematicCanvas(MplCanvas):
    """Zeichnet das LRC+M Ersatzschaltbild der Rogowski-Spule.

    Topologie (nach TikZ-Vorlage der Arbeit): vertikal L_C + U_ind links,
    horizontal R_C oben, C_C parallel am Port rechts (U_Coil).
    Primaerleiter laeuft quer unter der Masche, Kopplung M gestrichelt.
    """

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, show_toolbar=False, figsize=(8, 5))

    def draw(self, ec: EquivalentCircuit | None) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_axis_off()
        ax.set_xlim(-1.5, 10.5)
        ax.set_ylim(-0.5, 7.5)
        ax.set_aspect("equal")
        ax.set_facecolor(BG_PANEL)
        if ec is None:
            ax.text(4.5, 3.5, "– kein Ergebnis –",
                    ha="center", va="center", color=TEXT_DIM, fontsize=12)
            self.canvas.draw_idle()
            return

        wc = TEXT
        wlw = 1.8

        # --- Knotenkoordinaten (entsprechen TikZ) ---------------------
        # L_C:  (0,9) -> (0,7)       wir skalieren y-4  => (0,5) -> (0,3)
        # U_ind:(0,7) -> (0,5)                          => (0,3) -> (0,1)
        # R_C:  (1,9) -> (3,9)                          => (1,5) -> (3,5)
        # C_C:  (4,8) -> (4,6)                          => (4,4) -> (4,2)
        # Top-Wire: (0,9)-(1,9), (3,9)-(6,9)            => y=5
        # Bottom-Wire: (0,5) - (6,5)                    => y=1
        # Port rechts: ocirc (6,9), (6,5)               => (6,5) und (6,1)

        # Obere Leitung (Segmente wie in TikZ)
        ax.plot([0.0, 1.0], [5.0, 5.0], color=wc, lw=wlw)
        ax.plot([3.0, 6.0], [5.0, 5.0], color=wc, lw=wlw)
        # Stichleitung zum C_C
        ax.plot([4.0, 4.0], [5.0, 4.0], color=wc, lw=wlw)
        # Knoten auf der oberen/unteren Leitung an (4, ·)
        ax.plot(4.0, 5.0, "o", color=wc, markersize=6)
        ax.plot(4.0, 1.0, "o", color=wc, markersize=6)
        # Untere Leitung
        ax.plot([0.0, 6.0], [1.0, 1.0], color=wc, lw=wlw)

        # --- L_C (vertikal, links oben) -------------------------------
        _draw_inductor_vert(ax, 0.0, 5.0, 3.0, color=ACCENT_HI, lw=2.2)
        ax.text(0.55, 4.0, rf"$L_{{C}} = {ec.L_uH:.3f}\,\mu H$",
                ha="left", va="center", color=TEXT, fontsize=11)

        # --- U_ind (ideale Spannungsquelle, vertikal, links unten) ----
        _draw_source(ax, 0.0, 3.0, 1.0, color=ACCENT, lw=2.0)
        ax.text(-0.4, 2.0,
                r"$u_{ind}=-M\,\dfrac{di}{dt}$",
                ha="right", va="center", color=TEXT, fontsize=11)

        # --- R_C (horizontal, obere Leitung) --------------------------
        _draw_resistor_h(ax, 1.0, 5.0, 3.0, color=WARNING, lw=2.2)
        ax.text(2.0, 5.6, rf"$R_{{C}} = {ec.R_ohm:.3f}\,\Omega$",
                ha="center", va="bottom", color=TEXT, fontsize=11)

        # --- C_C (vertikal, parallel zum Ausgang) ---------------------
        _draw_capacitor_v(ax, 4.0, 4.0, 1.0, color=ROLE_WINDING, lw=2.8)
        ax.text(4.25, 2.5, rf"$C_{{C}} = {ec.C_pF:.2f}\,pF$",
                ha="left", va="center", color=TEXT, fontsize=11)

        # --- Port U_Coil rechts (offene Kreise) -----------------------
        for y_port in (5.0, 1.0):
            ax.add_patch(Circle((6.0, y_port), 0.10,
                                facecolor=BG_PANEL, edgecolor=wc, lw=1.6))
        ax.annotate("", xy=(6.5, 1.4), xytext=(6.5, 4.6),
                    arrowprops=dict(arrowstyle="-|>", color=TEXT_DIM, lw=1.2))
        ax.text(6.9, 3.0, r"$U_{Coil}$",
                ha="left", va="center", color=TEXT, fontsize=12)

        # --- Primaerleiter (quer unter der Masche, Kopplung M) --------
        y_p = -0.15
        ax.plot([-1.4, 10.4], [y_p, y_p], color=ROLE_RETURN, lw=3,
                solid_capstyle="round")
        ax.annotate("", xy=(9.4, y_p + 0.02), xytext=(-0.4, y_p + 0.02),
                    arrowprops=dict(arrowstyle="-|>",
                                    color=ROLE_RETURN, lw=1.6))
        ax.text(5.0, y_p - 0.35, r"$i_{prim}(t)$",
                ha="center", va="top", color=TEXT, fontsize=11)

        # --- M-Kopplung (gestrichelt zur Quelle) ----------------------
        ax.annotate("", xy=(0.0, 1.1), xytext=(0.0, y_p + 0.1),
                    arrowprops=dict(arrowstyle="-", color=ACCENT,
                                    lw=1.3, linestyle=(0, (3, 3))))
        ax.text(-1.2, (1.0 + y_p) / 2,
                rf"$M = {ec.M_nH:.3f}\,nH$",
                ha="left", va="center", color=ACCENT_HI, fontsize=10)

        # Titel
        ax.text(3.0, 7.1,
                r"Rogowski-Ersatzschaltbild  (Induktion → L–R–C → Port)",
                ha="center", va="center", color=TEXT, fontsize=12,
                fontweight="bold")

        self.figure.tight_layout(pad=0.3)
        self.canvas.draw_idle()


# ------------------- Zeichen-Helfer: vertikal/horizontal -----------------

def _draw_inductor_vert(ax, x: float, y1: float, y2: float,
                        *, color: str, lw: float = 2.0) -> None:
    """Vertikale Spule zwischen (x, y1)->(x, y2)  (y2 > y1 oder umgekehrt)."""
    ya, yb = (y1, y2) if y2 > y1 else (y2, y1)
    n = 4
    dy = (yb - ya) / n
    for i in range(n):
        cy = ya + dy * (i + 0.5)
        ax.add_patch(Arc((x, cy), dy * 0.95, dy,
                         angle=0, theta1=-90, theta2=90,
                         color=color, lw=lw))
    # Anschluesse
    ax.plot([x, x], [yb, max(y1, y2)], color=color, lw=lw * 0.6, alpha=0)


def _draw_inductor(ax, x0: float, y0: float, x1: float,
                   *, color: str, lw: float = 2) -> None:
    """Horizontale Spule – fuer Kompatibilitaet beibehalten."""
    n = 4
    dx = (x1 - x0) / n
    for i in range(n):
        cx = x0 + dx * (i + 0.5)
        ax.add_patch(Arc((cx, y0), dx, dx * 0.95,
                         angle=0, theta1=0, theta2=180,
                         color=color, lw=lw))


def _draw_resistor_h(ax, x0: float, y0: float, x1: float,
                     *, color: str, lw: float = 2.0) -> None:
    n = 6
    xs = np.linspace(x0, x1, n + 1)
    ys = [y0]
    for i in range(1, n):
        ys.append(y0 + (0.25 if i % 2 else -0.25))
    ys.append(y0)
    ax.plot(xs, ys, color=color, lw=lw)


def _draw_resistor(ax, x0: float, y0: float, x1: float,
                   *, color: str, lw: float = 2) -> None:
    _draw_resistor_h(ax, x0, y0, x1, color=color, lw=lw)


def _draw_capacitor_v(ax, x: float, y1: float, y2: float,
                      *, color: str, lw: float = 2.8) -> None:
    """Vertikaler Kondensator zwischen y1 (oben) und y2 (unten), Platten horizontal."""
    yh = (y1 + y2) / 2
    gap = 0.12
    plate_w = 0.6
    # Drahtstuecke
    ax.plot([x, x], [y1, yh + gap], color=TEXT, lw=1.8)
    ax.plot([x, x], [yh - gap, y2], color=TEXT, lw=1.8)
    # Platten (horizontal)
    ax.plot([x - plate_w / 2, x + plate_w / 2],
            [yh + gap, yh + gap], color=color, lw=lw)
    ax.plot([x - plate_w / 2, x + plate_w / 2],
            [yh - gap, yh - gap], color=color, lw=lw)


def _draw_capacitor(ax, x0: float, y0: float, x1: float,
                    *, color: str, lw: float = 2.8) -> None:
    xm = (x0 + x1) / 2
    gap = 0.1
    ax.plot([x0, xm - gap], [y0, y0], color=TEXT, lw=1.8)
    ax.plot([xm + gap, x1], [y0, y0], color=TEXT, lw=1.8)
    ax.plot([xm - gap, xm - gap], [y0 - 0.55, y0 + 0.55], color=color, lw=lw)
    ax.plot([xm + gap, xm + gap], [y0 - 0.55, y0 + 0.55], color=color, lw=lw)


def _draw_source(ax, x: float, y1: float, y2: float,
                 *, color: str, lw: float = 2.0) -> None:
    """Europaeische Spannungsquelle (Kreis mit +/- inline) vertikal y1..y2."""
    ya, yb = (y1, y2) if y2 > y1 else (y2, y1)
    cy = (ya + yb) / 2
    r = (yb - ya) * 0.35
    # Drahtstuecke
    ax.plot([x, x], [ya, cy - r], color=TEXT, lw=1.6)
    ax.plot([x, x], [cy + r, yb], color=TEXT, lw=1.6)
    # Kreis
    ax.add_patch(Circle((x, cy), r, facecolor=BG_PANEL,
                        edgecolor=color, lw=lw))
    # Plus/Minus (europaeische Norm mit Balken)
    ax.plot([x - r * 0.5, x + r * 0.5], [cy, cy], color=color, lw=lw)
    ax.text(x, cy + r * 0.35, "+", ha="center", va="center",
            color=color, fontsize=10, fontweight="bold")
    ax.text(x, cy - r * 0.35, "−", ha="center", va="center",
            color=color, fontsize=11, fontweight="bold")


# ===================================================================
#  Windungsfenster
# ===================================================================

class WindowGeometryCanvas(MplCanvas):
    """Rechteck: Hoehe = h_via, Breite = Via-zu-Via-Abstand."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, show_toolbar=False, figsize=(5, 3.5))

    def draw(self, window: ViaWindow | None,
             h_via_mm: float | None = None) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if window is None:
            ax.set_axis_off()
            ax.text(0.5, 0.5, "– kein Fenster ausgewaehlt –",
                    ha="center", va="center", color=TEXT_DIM)
            self.canvas.draw_idle()
            return

        h = float(h_via_mm if h_via_mm is not None else (window.h_via_mm or 1.0))
        if window.via_a_xy and window.via_b_xy:
            length = float(np.hypot(
                window.via_a_xy[0] - window.via_b_xy[0],
                window.via_a_xy[1] - window.via_b_xy[1]))
        else:
            length = float(max(window.x_max_mm - window.x_min_mm,
                               window.y_max_mm - window.y_min_mm))

        ax.set_aspect("equal")
        ax.set_xlabel("Laenge l [mm]")
        ax.set_ylabel("Hoehe h_via [mm]")
        title_col = ACCENT_HI if window.sigma > 0 else ROLE_RETURN
        ax.set_title(f"Fenster {window.window_id}  (σ = {window.sigma:+d})",
                     color=title_col)

        col = ACCENT if window.sigma > 0 else ROLE_RETURN
        ax.add_patch(Rectangle((0, 0), length, h,
                               facecolor=col, alpha=0.15,
                               edgecolor=col, lw=1.8))

        via_w = max(length * 0.04, 0.1)
        ax.add_patch(Rectangle((-via_w / 2, 0), via_w, h,
                               facecolor=TEXT_DIM, edgecolor=TEXT, lw=1))
        ax.add_patch(Rectangle((length - via_w / 2, 0), via_w, h,
                               facecolor=TEXT_DIM, edgecolor=TEXT, lw=1))
        for xv in (0.0, length):
            ax.add_patch(Circle((xv, 0), via_w * 0.8,
                                facecolor=TEXT, edgecolor=TEXT))
            ax.add_patch(Circle((xv, h), via_w * 0.8,
                                facecolor=TEXT, edgecolor=TEXT))
        ax.text(0, h + h * 0.08, "via A", ha="center", color=TEXT_DIM)
        ax.text(length, h + h * 0.08, "via B", ha="center", color=TEXT_DIM)

        ax.annotate("", xy=(length, -h * 0.18), xytext=(0, -h * 0.18),
                    arrowprops=dict(arrowstyle="<->", color=TEXT_DIM))
        ax.text(length / 2, -h * 0.30, f"l = {length:.3f} mm",
                ha="center", va="top", color=TEXT)
        ax.annotate("", xy=(-length * 0.08, h), xytext=(-length * 0.08, 0),
                    arrowprops=dict(arrowstyle="<->", color=TEXT_DIM))
        ax.text(-length * 0.13, h / 2, f"h = {h:.3f} mm",
                ha="right", va="center", color=TEXT, rotation=90)

        ax.text(length / 2, h / 2,
                f"A = l·h = {length * h:.3f} mm²",
                ha="center", va="center", color=TEXT,
                fontsize=11, fontweight="bold")

        ax.set_xlim(-length * 0.25, length * 1.15)
        ax.set_ylim(-h * 0.5, h * 1.25)
        ax.set_facecolor(BG_PANEL)
        ax.grid(True, alpha=0.15)
        self.figure.tight_layout()
        self.canvas.draw_idle()


# ===================================================================
#  B-Feld in XY-Ebene (geschlossene Feldlinien aus A_z)
# ===================================================================

class BFieldCanvas(MplCanvas):
    r"""Heatmap :math:`\log_{10}|\mathbf{B}|` + geschlossene Feldlinien.

    Physikalisches Modell
    ---------------------
    In 2D (alles :math:`z`-invariant) laesst sich das Vektorpotential
    eines antiparallelen Linienleiterpaares in Form

    .. math::

        A_z(x,y) \;=\; -\frac{\mu_0 I}{2\pi}\,
            \ln\!\frac{r_1(x,y)}{r_2(x,y)}

    schreiben, wobei :math:`r_{1,2}` die Abstaende zu den beiden Leitern
    sind. Die Konturlinien von :math:`A_z` sind **exakt** die
    :math:`\mathbf{B}`-Feldlinien, weil
    :math:`\mathbf{B} = \nabla \times (A_z\,\mathbf{e}_z)` und damit
    :math:`\mathbf{B}\cdot\nabla A_z \equiv 0`. Das garantiert
    geschlossene Kurven ohne Verletzung der Quellenfreiheit.

    Overlays
    --------
    * **Leiterbahnen**: Wenn per :meth:`set_board` / :meth:`set_classification`
      ein Board gesetzt wurde, werden die Kupfer-Segmente role-coloriert
      (winding=gruen, return=rot, connection=grau, unclassified=violett)
      dargestellt -- so erkennt der Nutzer die tatsaechliche Layout-
      Geometrie (Forderung des Benutzers: "Leiterbahnen statt Fenster").
    * **Windungsfenster**: Optional als duenne Rechtecke einblendbar
      (:meth:`set_show_windows`).
    * **Primaerleiter**: Zwei Marker (Punkt ``+I``, Kreuz ``-I``).
    """

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, show_toolbar=True, figsize=(6, 5))
        self._board: Board | None = None
        self._spec: ClassificationSpec | None = None
        self._show_traces: bool = True
        self._show_windows: bool = False

    # -- Konfiguration ------------------------------------------------------

    def set_board(self, board: "Board | None") -> None:
        """Setzt das Board zur Darstellung der Leiterbahngeometrie."""
        self._board = board

    def set_classification(self, spec: "ClassificationSpec | None") -> None:
        """Setzt die Klassifikation fuer das Rollen-Coloring."""
        self._spec = spec

    def set_show_traces(self, enabled: bool) -> None:
        self._show_traces = bool(enabled)

    def set_show_windows(self, enabled: bool) -> None:
        self._show_windows = bool(enabled)

    # -- Hauptzeichnung -----------------------------------------------------

    def draw(
        self,
        conductor: ConductorConfig | None,
        windows: list[ViaWindow] | None = None,
        current_A: float = 1.0,
    ) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_aspect("equal")
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("y [mm]")
        ax.set_facecolor(BG_PANEL)
        if conductor is None:
            ax.text(0.5, 0.5, "– kein Primaerleiter definiert –",
                    ha="center", va="center", color=TEXT_DIM,
                    transform=ax.transAxes)
            self.canvas.draw_idle()
            return

        x1, y1 = conductor.x1_mm, conductor.y1_mm
        x2, y2 = conductor.x2_mm, conductor.y2_mm

        # --- Zeichenbereich bestimmen -----------------------------------
        # Primaerpaar + Fenster + (falls vorhanden) Board-Outline.
        xs = [x1, x2]
        ys = [y1, y2]
        if windows:
            for w in windows:
                xs += [w.x_min_mm, w.x_max_mm]
                ys += [w.y_min_mm, w.y_max_mm]
        if self._show_traces and self._board is not None:
            for la in self._board.copper_layers:
                for lf in la.lines:
                    xs += [lf.start.x_mm, lf.end.x_mm]
                    ys += [lf.start.y_mm, lf.end.y_mm]
        span = max(max(xs) - min(xs), max(ys) - min(ys))
        pad = span * 0.10 + 2.0
        xmin, xmax = min(xs) - pad, max(xs) + pad
        ymin, ymax = min(ys) - pad, max(ys) + pad

        # --- Skalarfeld A_z + |B| auf Gitter ----------------------------
        nx = ny = 240
        X, Y = np.meshgrid(
            np.linspace(xmin, xmax, nx),
            np.linspace(ymin, ymax, ny),
        )

        r1_sq = (X - x1) ** 2 + (Y - y1) ** 2
        r2_sq = (X - x2) ** 2 + (Y - y2) ** 2
        eps = max(span * 0.003, 0.05) ** 2
        r1_sq_c = np.maximum(r1_sq, eps)
        r2_sq_c = np.maximum(r2_sq, eps)

        # |B| fuer Heatmap (Umrechnung mm -> m, Einheit Tesla).
        mu0_over_2pi = 2e-7
        r1_m_sq = r1_sq_c * 1e-6
        r2_m_sq = r2_sq_c * 1e-6
        Bx = mu0_over_2pi * current_A * (-(Y - y1) / r1_m_sq
                                         + (Y - y2) / r2_m_sq) * 1e-3
        By = mu0_over_2pi * current_A * ((X - x1) / r1_m_sq
                                         - (X - x2) / r2_m_sq) * 1e-3
        Bmag = np.hypot(Bx, By)
        Blog = np.log10(Bmag + 1e-12)

        im = ax.pcolormesh(X, Y, Blog, cmap="magma",
                           shading="auto", alpha=0.75, zorder=1)
        cbar = self.figure.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
        cbar.set_label(r"$\log_{10}|B|$  [T]", color=TEXT)
        cbar.ax.yaxis.set_tick_params(color=TEXT_DIM)
        for t in cbar.ax.get_yticklabels():
            t.set_color(TEXT)

        # Geschlossene Feldlinien aus A_z-Isolinien.
        Az = 0.5 * np.log(r1_sq_c / r2_sq_c)
        lvl_max = float(np.nanpercentile(np.abs(Az), 96))
        if lvl_max <= 0:
            lvl_max = 1.0
        levels = np.linspace(-lvl_max, lvl_max, 23)
        ax.contour(X, Y, Az, levels=levels,
                   colors=TEXT, linewidths=0.6, alpha=0.55, zorder=2)

        # --- Leiterbahn-Overlay (role-coloriert) ------------------------
        if self._show_traces and self._board is not None:
            self._draw_traces(ax)

        # --- Leiter-Marker (Punkt = raus, Kreuz = rein) -----------------
        r_cond = max(span * 0.012, 0.25)
        ax.add_patch(Circle((x1, y1), r_cond,
                            facecolor=WARNING, edgecolor=TEXT, lw=1.2,
                            zorder=5))
        ax.add_patch(Circle((x2, y2), r_cond,
                            facecolor=ROLE_RETURN, edgecolor=TEXT, lw=1.2,
                            zorder=5))
        ax.plot(x1, y1, marker="o", color=TEXT, markersize=4, zorder=6,
                label="+I (raus)")
        ax.plot(x2, y2, marker="x", color=TEXT, markersize=8,
                markeredgewidth=2, zorder=6, label="−I (rein)")

        # --- Fenster-Rechtecke (nur wenn aktiviert) ---------------------
        if windows and self._show_windows:
            for w in windows:
                ec_col = ACCENT_HI if w.sigma > 0 else ROLE_RETURN
                ax.add_patch(Rectangle(
                    (w.x_min_mm, w.y_min_mm),
                    w.x_max_mm - w.x_min_mm,
                    w.y_max_mm - w.y_min_mm,
                    fill=False, edgecolor=ec_col, lw=1.0, alpha=0.7,
                    linestyle="--", zorder=4,
                ))

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_title(f"B-Feld bei I = {current_A:.1f} A", color=TEXT)
        ax.legend(loc="upper right", fontsize=9,
                  facecolor=BG_PANEL, edgecolor=BORDER_HI,
                  labelcolor=TEXT)
        ax.grid(True, alpha=0.15, color=BORDER_HI)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    # -- Trace-Overlay ------------------------------------------------------

    def _draw_traces(self, ax) -> None:  # type: ignore[no-untyped-def]
        """Zeichnet Kupfer-Segmente role-coloriert als LineCollection.

        Unklassifizierte Segmente werden duenn & gestrichelt (violett)
        dargestellt, klassifizierte Rollen solid mit hoher Deckkraft.
        Das Pattern ist konsistent mit
        :class:`pcb_rogowski.ui.desktop.shared.classify_canvas.ClassifyCanvas`.
        """
        assert self._board is not None
        entries = (
            {e.feature_id: e for e in self._spec.entries}
            if self._spec is not None else {}
        )

        # Nach Farbe buendeln, damit wir je Gruppe Linestyle/-width setzen.
        by_color: dict[str, list[list[tuple[float, float]]]] = {}
        for la in self._board.copper_layers:
            for lf in la.lines:
                e = entries.get(lf.feature_id)
                if e is None or e.role not in _ROLE_COLORS:
                    col = _UNCLASSIFIED
                else:
                    col = _ROLE_COLORS[e.role]
                seg = [(lf.start.x_mm, lf.start.y_mm),
                       (lf.end.x_mm,   lf.end.y_mm)]
                by_color.setdefault(col, []).append(seg)

        for col, segs in by_color.items():
            is_uncl = (col == _UNCLASSIFIED)
            lc = LineCollection(
                segs,
                colors=col,
                linewidths=0.9 if is_uncl else 1.8,
                linestyles="dashed" if is_uncl else "solid",
                alpha=0.55 if is_uncl else 0.95,
                capstyle="round",
                zorder=3,
            )
            ax.add_collection(lc)


__all__ = [
    "SchematicCanvas",
    "WindowGeometryCanvas",
    "BFieldCanvas",
    "TransferFunctionCanvas",
]


# ===================================================================
#  Uebertragungsfunktion (Bode)
# ===================================================================

class TransferFunctionCanvas(MplCanvas):
    r"""Bode-Diagramm von :math:`H(j\omega)` und :math:`Z(j\omega)`.

    Zwei physikalisch unterschiedliche Uebertragungsfunktionen des
    RLC+M-Ersatzschaltbildes koennen umgeschaltet werden:

    * ``primary`` (Standard, Rogowski-Nutzfall)

      .. math::

         H(j\omega) \;=\; \frac{V_{out}(j\omega)}{I_{prim}(j\omega)}
         \;=\; \frac{j\omega M}{1 - \omega^{2} L C + j\omega R C}

      Einheit: Ohm (V/A).  Unterhalb der Eigenresonanz steigt :math:`|H|`
      mit 20 dB/Dek., am Resonanzpunkt :math:`f_{0}=1/(2\pi\sqrt{LC})`
      liegt ein Peak, danach faellt :math:`|H|` mit -20 dB/Dek. ab.

    * ``impedance`` (Klemmenimpedanz der Spule)

      .. math::

         Z(j\omega) \;=\; \frac{R + j\omega L}
                                {1 - \omega^{2} L C + j\omega R C}

      Diese Kurve vergleicht direkt mit einer Bode100-Messung und wird
      auch im Output-Tab verwendet (Fit ↔ Modell).

    Darstellung
    -----------
    Oberer Plot: :math:`20\log_{10}|H|` in dB-Ohm ueber :math:`f` (log).
    Unterer Plot: :math:`\arg H` in Grad.  Der Resonanzpunkt
    :math:`f_{0}` wird als vertikale Linie gekennzeichnet.
    """

    _MODES = ("primary", "impedance")

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent, show_toolbar=True, figsize=(6, 5))
        self._mode: str = "primary"
        self._ec: EquivalentCircuit | None = None
        self._f_min_hz: float = 1e3
        self._f_max_hz: float = 1e9

    # -- API --------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Schaltet zwischen ``"primary"`` (H) und ``"impedance"`` (Z)."""
        if mode not in self._MODES:
            raise ValueError(f"mode must be one of {self._MODES!r}")
        self._mode = mode
        self._redraw()

    @property
    def mode(self) -> str:
        return self._mode

    def set_frequency_range(self, f_min_hz: float, f_max_hz: float) -> None:
        self._f_min_hz = float(f_min_hz)
        self._f_max_hz = float(f_max_hz)
        self._redraw()

    def draw(self, ec: EquivalentCircuit | None) -> None:
        """Speichert das Ersatzschaltbild und zeichnet mit aktuellem Modus."""
        self._ec = ec
        self._redraw()

    # -- Intern -----------------------------------------------------------

    def _redraw(self) -> None:
        self.figure.clear()
        ec = self._ec
        if ec is None or ec.L_H <= 0 or ec.C_F <= 0:
            ax = self.figure.add_subplot(111)
            ax.set_axis_off()
            ax.set_facecolor(BG_PANEL)
            ax.text(0.5, 0.5, "– kein Ergebnis –",
                    ha="center", va="center", color=TEXT_DIM,
                    transform=ax.transAxes)
            self.canvas.draw_idle()
            return

        # Frequenzachse
        f = np.logspace(np.log10(self._f_min_hz),
                        np.log10(self._f_max_hz), 1024)
        w = 2.0 * np.pi * f

        # TF auswaehlen
        if self._mode == "impedance":
            tf = impedance_tf(ec)
            ylabel_mag = r"$|Z(j\omega)|$  [dB·Ω]"
            title = "Klemmenimpedanz  Z(jω)"
        else:
            tf = voltage_from_primary_tf(ec)
            ylabel_mag = r"$|H(j\omega)|=|V_{out}/I_{prim}|$  [dB·Ω]"
            title = "Uebertragungsfunktion  V_out / I_prim"

        # Frequenzgang auswerten (numpy-Polynom robust ggue. scipy.bode).
        num = np.asarray(tf.num, dtype=float)
        den = np.asarray(tf.den, dtype=float)
        jw = 1j * w
        H = np.polyval(num, jw) / np.polyval(den, jw)
        mag_db = 20.0 * np.log10(np.abs(H) + 1e-30)
        phase_deg = np.degrees(np.unwrap(np.angle(H)))

        # Eigenresonanz
        f0 = 1.0 / (2.0 * np.pi * np.sqrt(ec.L_H * ec.C_F))

        # --- Plot ---
        ax_mag = self.figure.add_subplot(211)
        ax_mag.set_facecolor(BG_PANEL)
        ax_mag.semilogx(f, mag_db, color=ACCENT_HI, lw=1.8)
        ax_mag.axvline(f0, color=WARNING, lw=1.0, ls="--",
                       label=fr"$f_0 = {f0/1e6:.2f}$ MHz")
        ax_mag.set_ylabel(ylabel_mag, color=TEXT)
        ax_mag.set_title(title, color=TEXT)
        ax_mag.grid(True, which="both", alpha=0.2, color=BORDER_HI)
        ax_mag.legend(loc="best", fontsize=9, facecolor=BG_PANEL,
                      edgecolor=BORDER_HI, labelcolor=TEXT)
        for sp in ax_mag.spines.values():
            sp.set_color(BORDER_HI)
        ax_mag.tick_params(colors=TEXT_DIM)

        ax_ph = self.figure.add_subplot(212, sharex=ax_mag)
        ax_ph.set_facecolor(BG_PANEL)
        ax_ph.semilogx(f, phase_deg, color=ROLE_WINDING, lw=1.8)
        ax_ph.axvline(f0, color=WARNING, lw=1.0, ls="--")
        ax_ph.axhline(0, color=TEXT_DIM, lw=0.6, alpha=0.5)
        ax_ph.set_xlabel("Frequenz f [Hz]", color=TEXT)
        ax_ph.set_ylabel(r"$\arg H$  [°]", color=TEXT)
        ax_ph.grid(True, which="both", alpha=0.2, color=BORDER_HI)
        for sp in ax_ph.spines.values():
            sp.set_color(BORDER_HI)
        ax_ph.tick_params(colors=TEXT_DIM)

        self.figure.tight_layout()
        self.canvas.draw_idle()
