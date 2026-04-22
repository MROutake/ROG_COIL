"""
MutualInductanceCalculator: Berechnet die gegenseitige Induktivität
M_prim zwischen dem Dual-Busbar-Primärleiter und der Rogowski-Spule.

Modell
------
Zwei linienhafte Leiter (I₁ = +I, I₂ = −I) erzeugen ein Magnetfeld.
Die Kopplung zur Rogowski-Spule wird fensterweise berechnet.

Methoden
--------
1) **analytical** (vereinfacht):
    M_m = (µ₀·h_m)/(2π) · σ_m · [ln((a₁+b)/a₁) − ln((a₂+b)/a₂)]
    Setzt konzentrische Feldlinien um jeden Leiter voraus.

2) **field_integral** (exakt für Linienleiter):
    M_m = σ_m · h_m · (µ₀)/(2π) · ∫(via_a→via_b) F⊥(l) dl

    Integriert die Normalkomponente des tatsächlichen, resultierenden
    B-Feldes beider Leiter (Superposition) entlang des Pfades von
    via_a nach via_b.  Keine Annahme über die Feldgeometrie nötig.

3) **numerical** (Rasterintegration):
    Numerische 2D-Integration über die Fensterfläche.

Leiter-Konfiguration (Dual-Busbar)
-----------------------------------
Die zwei Primärleiter verlaufen parallel zur Spulenachse mit
Koordinaten (x₁, y₁) und (x₂, y₂).  Typischerweise verläuft der
eine Leiter durch das Spuleninnere, der andere außerhalb.

Referenz:
    Herleitung: Biot-Savart + Flächenintegral über rechteckige Fenster
    (siehe Diplomarbeit, Kapitel „Gegenseitige Induktivität").
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime

from pcb_rogowski.domain.common.trace import CalculationTrace, QualityStatus, TraceStep
from pcb_rogowski.domain.formulas import FORMULAS
from pcb_rogowski.domain.mutual.models import (
    MutualInductanceResult,
    WindowMutualContribution,
)
from pcb_rogowski.domain.trace.models import ViaWindow

logger = logging.getLogger(__name__)

_MU_0: float = 1.2566370614e-6  # H/m


# ---------------------------------------------------------------------------
# Konfiguration: Position der Primärleiter
# ---------------------------------------------------------------------------

@dataclass
class ConductorConfig:
    """
    Position der zwei Primärleiter im Board-Koordinatensystem [mm].

    Leiter 1 trägt Strom +I, Leiter 2 trägt Strom −I.

    Attributes:
        x1_mm, y1_mm:  Position Leiter 1 (Hin-Leiter)
        x2_mm, y2_mm:  Position Leiter 2 (Rück-Leiter)
        axis:          Orientierung der Leiter: ``"z"`` (senkrecht zur PCB)
                       oder ``"y"`` / ``"x"`` (parallel zur PCB).
                       Standard: ``"z"`` (Leiter durchstoßen die Platine).
    """

    x1_mm: float
    y1_mm: float
    x2_mm: float
    y2_mm: float
    axis: str = "z"  # Leiter parallel zur z-Achse (senkrecht zur PCB)


# ---------------------------------------------------------------------------
# Rechner
# ---------------------------------------------------------------------------

class MutualInductanceCalculator:
    """
    Berechnet M_prim für eine gegebene Fensterliste und Leiterkonfiguration.

    Unterstützt:
        - ``"field_integral"``:  Linienintegral des realen B-Feldes
          (Superposition beider Leiter) entlang des Via-Pfades.
          Genaueste Methode – keine Annahme über Feldgeometrie.
        - ``"analytical"``: Vereinfachte ln-Formel für rechteckige Fenster.
          Setzt konzentrische Feldlinien voraus.
        - ``"numerical"``: 2D-Rasterintegration über die Fensterfläche.

    Args:
        conductor:  Position der zwei Primärleiter.
        method:     ``"field_integral"`` (Standard), ``"analytical"``
                    oder ``"numerical"``.
        grid_n:     Rasterpunkte pro Achse für numerische Integration.
        n_integration: Integrationspunkte entlang des Via-Pfades
                       (nur für ``"field_integral"``).
    """

    def __init__(
        self,
        conductor: ConductorConfig,
        method: str = "field_integral",
        grid_n: int = 50,
        n_integration: int = 500,
    ) -> None:
        self._cond = conductor
        self._method = method
        self._grid_n = grid_n
        self._n_integration = n_integration

    def compute(
        self,
        windows: list[ViaWindow],
        h_eff_mm: float | None = None,
    ) -> MutualInductanceResult:
        """Gegenseitige Induktivität M_prim zwischen Dual-Busbar und Spule [H].

        Registry-Keys
        -------------
        ``M_conductor_config`` (Konfiguration), ``M_total`` (Aggregation)
        -- siehe :mod:`pcb_rogowski.domain.formulas`.

        Physik
        ------
        Biot-Savart-Feld der beiden Primärleiter (+I, -I) wird pro Via-
        Fenster m integriert::

            M_prim = Σ_m |M_m|
            M_m    = σ_m · h_m · (µ₀ / 2π) · ∫ F⊥(l) dl

        Vorzeichen ``σ_m ∈ {+1,-1}`` erfasst die Richtung des Fensters
        (abhängig von der Via-Traversal-Reihenfolge in der Spulen-
        Geometrie).

        Methoden (``self._method``):
          * ``field_integral`` -- Linienintegral des exakten B-Feldes
            entlang Via-Pfad (Standard, genauest bei Linienleitern).
          * ``analytical``     -- Konzentrische-Kreise-Näherung für
            achsparallele Rechteckfenster (Legacy, schnell).
          * ``numerical``      -- 2D-Rasterintegration über Fenster-
            fläche (Vergleichs-/Debugging-Methode).

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * Linienleiter senkrecht zur Platine (``axis='z'``). Für
          horizontale Leiter analytisches Modell nicht gültig --
          auf ``field_integral`` oder ``numerical`` wechseln.
        * Beide Leiter führen betraglich denselben Strom (+I / -I).
        * Quasi-statisch (f klein gegen Eigenresonanz der Spule).
        * Wird ``h_eff_mm`` übergeben, überschreibt er die Via-Höhe
          aus dem Fenster (nützlich, um Stackup-Lagendicke explizit
          zu steuern).

        Sanity-Zahl
        -----------
        Design 03 mit Dual-Busbar (Δx = 50 mm, Leiter 1 innen),
        40 Windungen, Board 1.6 mm:
        Typischer Wert M_prim ≈ 12 nH. Grobprüfung: halbiere die
        Busbar-Distanz → M_prim sollte ~verdoppelt werden.

        Anpassung
        ---------
        Model-Wechsel (z. B. Finite-Leiter-Länge) erfordert neues
        Vorzeichen-/Geometrie-Handling in den ``_compute_window_*``-
        Methoden. Workflow: ``docs/FORMELN-ANPASSEN.md``.
        """
        if not windows:
            return self._empty_result("Keine Via-Fenster für M-Berechnung vorhanden.")

        steps: list[TraceStep] = []
        warnings: list[str] = []
        contributions: list[WindowMutualContribution] = []

        # Leiterpositionen [m]
        x1 = self._cond.x1_mm * 1e-3
        y1 = self._cond.y1_mm * 1e-3
        x2 = self._cond.x2_mm * 1e-3
        y2 = self._cond.y2_mm * 1e-3

        steps.append(TraceStep(
            name="Primärleiter-Konfiguration",
            formula=FORMULAS["M_conductor_config"].latex,
            inputs={
                "x1_mm": self._cond.x1_mm, "y1_mm": self._cond.y1_mm,
                "x2_mm": self._cond.x2_mm, "y2_mm": self._cond.y2_mm,
                "N_windows": float(len(windows)),
            },
            output=float(len(windows)),
            unit="Fenster",
            note=f"Methode: {self._method}",
        ))

        m_total_H = 0.0

        for win in windows:
            if self._method == "numerical":
                m_m_H = self._compute_window_numerical(
                    win, x1, y1, x2, y2, h_eff_mm,
                )
            elif self._method == "field_integral":
                m_m_H = self._compute_window_field_integral(
                    win, x1, y1, x2, y2, h_eff_mm,
                    warnings,
                )
            else:
                m_m_H = self._compute_window_analytical(
                    win, x1, y1, x2, y2, h_eff_mm,
                    warnings,
                )

            m_total_H += abs(m_m_H)
            contributions.append(WindowMutualContribution(
                window_id=win.window_id,
                m_nH=m_m_H * 1e9,
                sigma=win.sigma,
                area_mm2=win.area_mm2,
            ))

        # Prozentuale Verteilung
        abs_total = abs(m_total_H) if m_total_H != 0 else 1e-30
        contributions_with_pct = [
            WindowMutualContribution(
                window_id=c.window_id,
                m_nH=c.m_nH,
                sigma=c.sigma,
                area_mm2=c.area_mm2,
                percentage=abs(c.m_nH * 1e-9) / abs_total * 100.0,
            )
            for c in contributions
        ]

        steps.append(TraceStep(
            name="M_ges – Gesamtgegeninduktivität",
            formula=FORMULAS["M_total"].latex,
            inputs={
                "N_windows": float(len(windows)),
                "M_pos_nH": sum(c.m_nH for c in contributions if c.m_nH > 0),
                "M_neg_nH": sum(c.m_nH for c in contributions if c.m_nH < 0),
            },
            output=m_total_H * 1e9,
            unit="nH",
        ))

        status = QualityStatus.WARNING if warnings else QualityStatus.OK
        trace = CalculationTrace(
            calculation_name="MutualInductanceCalculator",
            steps=tuple(steps),
            warnings=tuple(warnings),
            quality_status=status,
            source_files=(),
            config_versions={"method": self._method},
            timestamp=datetime.now().isoformat(),
        )

        return MutualInductanceResult(
            m_total_nH=m_total_H * 1e9,
            window_contributions=tuple(contributions_with_pct),
            trace=trace,
        )

    # ------------------------------------------------------------------
    # Linienintegral des realen B-Feldes (exakt für Linienleiter)
    # ------------------------------------------------------------------

    def _compute_window_field_integral(
        self,
        win: ViaWindow,
        x1: float, y1: float,
        x2: float, y2: float,
        h_eff_mm: float | None,
        warnings: list[str],
    ) -> float:
        """Beitrag eines Fensters m über das exakte B-Feld-Linienintegral [H].

        Registry-Key
        ------------
        ``M_total``  -- diese Methode liefert ``M_m``, die Summe
        ``M_prim = Σ|M_m|`` wird in :meth:`compute` aggregiert.

        Physik
        ------
        Superposition beider Linienleiter ergibt das 2D-Feld
        (µ₀·I/(2π)) · F, mit der normierten Feldstärke::

            F = (-Δy₁/ρ₁² + Δy₂/ρ₂²,  Δx₁/ρ₁² - Δx₂/ρ₂²)

        Das Fenster wird durch den geraden Pfad von Via A nach Via B
        parametrisiert, Länge ``b_m``. Fensternormale
        ``n̂ = ẑ × t̂ = (-t_y, t_x)``. Der Fluss durch das Fenster::

            Φ_m = h_m · (µ₀ I / 2π) · ∫₀^{b_m} F⊥(l) dl
            M_m = σ_m · Φ_m / I = σ_m · h_m · (µ₀/2π) · ∫ F⊥ dl

        Numerisch wird das Integral per Trapezregel mit
        ``self._n_integration`` Stützstellen berechnet.

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * Primärleiter als ideale Linienleiter (ρ → 0 ist regularisiert
          durch ``max(ρ², 1e-20)``).
        * Gerader Via-Pfad zwischen ``via_a_xy`` und ``via_b_xy``
          (keine gekrümmten Fenster).
        * Fensternormale liegt in der x-y-Ebene; Leiterachse z.
        * Fallback auf ``_compute_window_analytical``, wenn Via-
          Koordinaten fehlen (wird als Warnung protokolliert).

        Sanity-Zahl
        -----------
        Leiter 1 bei (0, 0), Leiter 2 bei (50 mm, 0), Fenster zentriert
        bei (25 mm, 10 mm), b_m = 4 mm, h_m = 1.6 mm:
        F⊥ ≈ 2·y/(x²+y²) ≈ 28 m⁻¹  →
        M_m ≈ 1·1.6e-3·(µ₀/2π)·28·4e-3 ≈ 36 pH.

        Bei 40 Windungen und symmetrischem Aufbau erwartet man
        |M_prim| in der Größenordnung einiger nH.

        Anpassung
        ---------
        Änderung des Integranden (z. B. endliche Leiterlänge via
        elliptische Integrale) hier lokal umsetzen; Registry-Latex
        ``M_total`` synchronisieren. Workflow:
        ``docs/FORMELN-ANPASSEN.md``.
        """
        # Fallback: ohne Via-Koordinaten → analytische Formel
        if win.via_a_xy is None or win.via_b_xy is None:
            warnings.append(
                f"Fenster {win.window_id}: Keine Via-Koordinaten – "
                f"Fallback auf analytische Formel."
            )
            return self._compute_window_analytical(
                win, x1, y1, x2, y2, h_eff_mm, warnings,
            )

        # Fensterhöhe [m]
        if h_eff_mm is not None:
            h_m = h_eff_mm * 1e-3
        elif win.h_via_mm is not None:
            h_m = win.h_via_mm * 1e-3
        else:
            h_m = win.height_mm * 1e-3

        # Via-Positionen [m]
        xa, ya = win.via_a_xy[0] * 1e-3, win.via_a_xy[1] * 1e-3
        xb, yb = win.via_b_xy[0] * 1e-3, win.via_b_xy[1] * 1e-3

        # Richtungsvektor und Pfadlänge
        dx = xb - xa
        dy = yb - ya
        b_m = math.hypot(dx, dy)

        if b_m <= 0:
            return 0.0

        # Einheitsvektoren
        tx = dx / b_m   # tangential (entlang Pfad)
        ty = dy / b_m
        nx = -ty         # Fensternormale: n̂ = ẑ × t̂ = (−ty, tx)
        ny = tx

        # Numerische Integration (Trapezregel, n_integration Segmente)
        n = self._n_integration
        dl = b_m / n
        integral = 0.0

        for i in range(n + 1):
            l = i * dl
            xp = xa + l * tx
            yp = ya + l * ty

            # Abstände zum Leiter 1 (+I)
            rx1 = xp - x1
            ry1 = yp - y1
            rho1_sq = rx1 * rx1 + ry1 * ry1
            rho1_sq = max(rho1_sq, 1e-20)  # Regularisierung

            # Abstände zum Leiter 2 (−I)
            rx2 = xp - x2
            ry2 = yp - y2
            rho2_sq = rx2 * rx2 + ry2 * ry2
            rho2_sq = max(rho2_sq, 1e-20)

            # Normierte Feldstärke F = B·2π/(µ₀I) beider Leiter:
            #   Leiter 1 (+I): F₁ = (−ry1, rx1) / ρ₁²
            #   Leiter 2 (−I): F₂ = (+ry2, −rx2) / ρ₂²  (umgekehrtes Vorzeichen)
            fx = -ry1 / rho1_sq + ry2 / rho2_sq
            fy = rx1 / rho1_sq - rx2 / rho2_sq

            # Normalkomponente
            f_perp = fx * nx + fy * ny

            # Trapezgewicht
            w = 0.5 if (i == 0 or i == n) else 1.0
            integral += w * f_perp * dl

        # M_m = σ · h_m · (µ₀/(2π)) · ∫ F⊥ dl
        sigma = win.sigma
        m_m_H = (_MU_0 / (2.0 * math.pi)) * h_m * sigma * integral

        return m_m_H

    # ------------------------------------------------------------------
    # Analytische Berechnung (rechteckige Fenster)
    # ------------------------------------------------------------------

    def _compute_window_analytical(
        self,
        win: ViaWindow,
        x1: float, y1: float,
        x2: float, y2: float,
        h_eff_mm: float | None,
        warnings: list[str],
    ) -> float:
        """
        Analytische Formel für ein rechteckiges Fenster [H].

        M_m = (µ₀·h_m)/(2π) · σ_m · [ln((a₁+b)/a₁) − ln((a₂+b)/a₂)]

        Die Fensterbreite b_m und die Abstände a₁, a₂ werden aus der
        Fenster-Bounding-Box und den Leiterpositionen abgeleitet.

        Konvention:
            - Der Abstand ist die kürzeste Entfernung vom Leiter zur
              NÄHEREN Kante des Fensters (= a_s,m im Modell).
            - b_m = Fensterbreite in Richtung der Abstandsvariation.
        """
        # Fensterhöhe [m]
        if h_eff_mm is not None:
            h_m = h_eff_mm * 1e-3
        else:
            h_m = win.height_mm * 1e-3

        # Fenster-BBox [m]
        x_min = win.x_min_mm * 1e-3
        x_max = win.x_max_mm * 1e-3
        y_min = win.y_min_mm * 1e-3
        y_max = win.y_max_mm * 1e-3

        # Fensterbreite b_m: Euklidische Distanz zwischen den beiden
        # Vias des Fensters (bevorzugt), oder BBox-Ausdehnung als Fallback.
        if win.dist_mm is not None and win.dist_mm > 0:
            b_m = win.dist_mm * 1e-3
        else:
            b_m = x_max - x_min
            if b_m <= 0:
                b_m = y_max - y_min  # Fallback: y-Breite

        if b_m <= 0:
            warnings.append(
                f"Fenster {win.window_id}: Breite b_m ≤ 0 — übersprungen."
            )
            return 0.0

        # Abstände zu den Leitern: kürzeste Distanz zur NÄHEREN Fensterkante
        a1 = self._min_distance_to_window_edge(x1, y1, x_min, y_min, x_max, y_max)
        a2 = self._min_distance_to_window_edge(x2, y2, x_min, y_min, x_max, y_max)

        # Sicherstellung: a > 0 (Leiter sollte nicht IM Fenster liegen)
        if a1 <= 0:
            a1 = 1e-6  # Regularisierung: 1 µm
            warnings.append(
                f"Fenster {win.window_id}: Leiter 1 liegt im/auf dem Fenster – "
                f"Abstand auf 1 µm regularisiert."
            )
        if a2 <= 0:
            a2 = 1e-6
            warnings.append(
                f"Fenster {win.window_id}: Leiter 2 liegt im/auf dem Fenster – "
                f"Abstand auf 1 µm regularisiert."
            )

        # M_m = (µ₀·h_m)/(2π) · σ_m · [ln((a₁+b)/a₁) − ln((a₂+b)/a₂)]
        sigma = win.sigma
        term1 = math.log((a1 + b_m) / a1)
        term2 = math.log((a2 + b_m) / a2)

        m_m_H = (_MU_0 * h_m / (2.0 * math.pi)) * sigma * (term1 - term2)

        return m_m_H

    # ------------------------------------------------------------------
    # Numerische Integration (beliebige Fensterform)
    # ------------------------------------------------------------------

    def _compute_window_numerical(
        self,
        win: ViaWindow,
        x1: float, y1: float,
        x2: float, y2: float,
        h_eff_mm: float | None,
    ) -> float:
        """
        Numerische Rasterintegration für ein Fenster [H].

        M_m = (µ₀)/(2π) · σ · h_m · ΣΣ [1/ρ₁(x,y) − 1/ρ₂(x,y)] · ΔA / A

        Die Integration erfolgt über ein gleichmäßiges Raster im Fenster.
        """
        if h_eff_mm is not None:
            h_m = h_eff_mm * 1e-3
        else:
            h_m = win.height_mm * 1e-3

        x_min = win.x_min_mm * 1e-3
        x_max = win.x_max_mm * 1e-3
        y_min = win.y_min_mm * 1e-3
        y_max = win.y_max_mm * 1e-3

        nx = self._grid_n
        ny = self._grid_n
        dx = (x_max - x_min) / max(nx, 1)
        dy = (y_max - y_min) / max(ny, 1)

        if dx <= 0 or dy <= 0:
            return 0.0

        integral = 0.0
        for i in range(nx):
            xp = x_min + (i + 0.5) * dx
            for j in range(ny):
                yp = y_min + (j + 0.5) * dy

                rho1 = math.hypot(xp - x1, yp - y1)
                rho2 = math.hypot(xp - x2, yp - y2)

                # Regularisierung: Mindestabstand 1 µm
                rho1 = max(rho1, 1e-6)
                rho2 = max(rho2, 1e-6)

                integral += (1.0 / rho1 - 1.0 / rho2) * dx * dy

        sigma = win.sigma
        m_m_H = (_MU_0 / (2.0 * math.pi)) * sigma * h_m * integral / max(h_m, 1e-12) * h_m

        # Korrektur: Das Integral liefert ∫∫ [1/ρ₁ - 1/ρ₂] dA
        # M_m = (µ₀/(2π)) · σ · (h_m / h_window) · ∫∫ ... dA
        # Wobei h_m = Via-Höhe, h_window = geometrische Fensterhöhe
        # Für einfache Fälle: h_m ist bereits korrekt
        h_window = (y_max - y_min) if (y_max - y_min) > 0 else (x_max - x_min)
        if h_window > 0:
            m_m_H = (_MU_0 / (2.0 * math.pi)) * sigma * (h_m / h_window) * integral
        else:
            m_m_H = 0.0

        return m_m_H

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    @staticmethod
    def _min_distance_to_window_edge(
        px: float, py: float,
        x_min: float, y_min: float,
        x_max: float, y_max: float,
    ) -> float:
        """
        Berechnet den kürzesten Abstand eines Punktes zur nächsten
        Kante eines Rechtecks.

        Falls der Punkt INNERHALB des Rechtecks liegt, gibt die Methode
        den Abstand zur nächsten Kante als negativen Wert zurück
        (→ Leiter im Fenster).

        Falls der Punkt AUSSERHALB liegt, wird der kürzeste euklidische
        Abstand zum Rechteck zurückgegeben.
        """
        # Punkt liegt innerhalb?
        inside_x = x_min <= px <= x_max
        inside_y = y_min <= py <= y_max

        if inside_x and inside_y:
            # Abstand zur nächsten Kante (negativ = im Innern)
            dx = min(px - x_min, x_max - px)
            dy = min(py - y_min, y_max - py)
            return -min(dx, dy)

        # Punkt liegt außerhalb → kürzeste Distanz zum Rechteck
        dx = max(x_min - px, 0, px - x_max)
        dy = max(y_min - py, 0, py - y_max)
        return math.hypot(dx, dy)

    @staticmethod
    def _empty_result(warning: str) -> MutualInductanceResult:
        trace = CalculationTrace(
            calculation_name="MutualInductanceCalculator",
            steps=(),
            warnings=(warning,),
            quality_status=QualityStatus.WARNING,
            source_files=(),
            config_versions={},
            timestamp=datetime.now().isoformat(),
        )
        return MutualInductanceResult(
            m_total_nH=0.0,
            window_contributions=(),
            trace=trace,
        )
