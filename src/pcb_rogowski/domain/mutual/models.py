"""
Domain-Modelle: Mutual-Inductance-Ergebnisobjekt.

MutualInductanceResult enthält die fensterweise Gegeninduktivität
zwischen der Rogowski-Spule und dem Dual-Busbar-Leiter.
"""

from __future__ import annotations

from dataclasses import dataclass

from pcb_rogowski.domain.common.trace import CalculationTrace


@dataclass(frozen=True)
class WindowMutualContribution:
    """
    Beitrag eines einzelnen Via-Fensters zur Gesamtgegeninduktivität.

    Attributes:
        window_id: Bezeichner des Via-Fensters.
        m_nH: Gegeninduktivitätsbeitrag in nH.
        sigma: Vorzeichen des Beitrags (+1 / -1).
        area_mm2: Fensterfläche in mm².
        percentage: Prozentualer Anteil an M_ges.
    """

    window_id: str
    m_nH: float
    sigma: int
    area_mm2: float
    percentage: float = 0.0


@dataclass(frozen=True)
class MutualInductanceResult:
    """
    Gesamtergebnis der analytischen Gegeninduktivitätsberechnung.

    Attributes:
        m_total_nH: Gesamtgegeninduktivität M_ges in nH.
        window_contributions: Einzelbeiträge aller Via-Fenster.
        trace: Rechen-Protokoll.
    """

    m_total_nH: float
    window_contributions: tuple[WindowMutualContribution, ...]
    trace: CalculationTrace

    def summary(self) -> str:
        lines = [f"MutualInductanceResult: M_ges = {self.m_total_nH:.4f} nH\n"]
        for w in self.window_contributions:
            lines.append(
                f"  Fenster {w.window_id}: {w.m_nH:+.4f} nH "
                f"({w.percentage:.1f}%, σ={w.sigma:+d})"
            )
        return "\n".join(lines)
