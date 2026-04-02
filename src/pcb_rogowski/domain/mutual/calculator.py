"""
MutualInductanceCalculator: Berechnet die gegenseitige Induktivität
M_prim zwischen dem Dual-Busbar-Primärleiter und der Rogowski-Spule.

Modell
------
Zwei linienhafte Leiter (I₁ = +I, I₂ = −I) erzeugen ein Magnetfeld.
Die Kopplung zur Rogowski-Spule wird fensterweise berechnet:

    M_m = (µ₀·h_m) / (2π) · σ_m · [ln((a₁_m + b_m) / a₁_m)
                                    − ln((a₂_m + b_m) / a₂_m)]

    M_ges = Σ M_m

mit:
    h_m      Effektive Fensterhöhe (= axiale Ausdehnung der Windung)
    b_m      Fensterbreite (radiale Ausdehnung)
    a₁_m     Minimaler Abstand des Fensters zu Leiter 1
    a₂_m     Minimaler Abstand des Fensters zu Leiter 2
    σ_m      Vorzeichen aus Wicklungssinn (+1 / −1)

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
        - Analytische Formel für rechteckige Fenster (ln-Auswertung)
        - Numerische Integration für beliebige Fensterformen (Raster)

    Args:
        conductor:  Position der zwei Primärleiter.
        method:     ``"analytical"`` (Standard) oder ``"numerical"``.
        grid_n:     Rasterpunkte pro Achse für numerische Integration.
    """

    def __init__(
        self,
        conductor: ConductorConfig,
        method: str = "analytical",
        grid_n: int = 50,
    ) -> None:
        self._cond = conductor
        self._method = method
        self._grid_n = grid_n

    def compute(
        self,
        windows: list[ViaWindow],
        h_eff_mm: float | None = None,
    ) -> MutualInductanceResult:
        """
        Berechnet M_prim aus den Via-Fenstern.

        Args:
            windows:   Liste der extrahierten Via-Fenster.
            h_eff_mm:  Effektive Fensterhöhe [mm] (= Via-Höhe / Stackup-Dicke).
                       Falls None, wird ``window.height_mm`` verwendet.

        Returns:
            MutualInductanceResult mit Gesamt-M und Einzelbeiträgen.
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
            formula="Leiter 1: (+I) bei (x₁, y₁),  Leiter 2: (−I) bei (x₂, y₂)",
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
            else:
                m_m_H = self._compute_window_analytical(
                    win, x1, y1, x2, y2, h_eff_mm,
                    warnings,
                )

            m_total_H += m_m_H
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
            formula="M_ges = Σ M_m",
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

        # Fensterbreite b_m: die Ausdehnung in der Richtung, in der die
        # Leiter-Abstände variieren.  Bei Leitern in z-Richtung (senkrecht
        # zur PCB) ist das die radiale Ausdehnung des Fensters.
        # Wir nehmen die Breite in x-Richtung als Standard.
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
