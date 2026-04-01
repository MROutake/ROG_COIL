"""
Domain-Modelle: Spulen-Parameter-Ergebnisobjekt.

CoilParameters kapselt alle berechneten elektrischen Parameter
einer PCB-Rogowski-Spule inkl. Rechen-Trace.
"""

from __future__ import annotations

from dataclasses import dataclass

from pcb_rogowski.domain.common.trace import CalculationTrace


@dataclass(frozen=True)
class CoilParameters:
    """
    Vollständige elektrische Parameter einer PCB-Rogowski-Spule.

    Alle Werte sind SI-normiert gespeichert, die Einheiten sind
    in den Attributnamen kodiert (z. B. _uH = Mikrohenry).

    Attributes:
        l_track_uH: Induktivitätsanteil der Spurleiter in µH.
        l_vias_uH: Induktivitätsanteil der Vias in µH.
        l_trace_uH: Gesamtinduktivität der Leiterstruktur in µH.
        l_total_uH: Gesamtinduktivität der Spule inkl. Rückleiter in µH.
        r_series_ohm: Serienwiderstand der Spule in Ω.
        c_series_pF: Serienkapazität in pF.
        resonance_mhz: Eigenresonanzfrequenz in MHz.
        trace: Rechen-Protokoll mit allen Zwischenschritten.
    """

    l_track_uH: float
    l_vias_uH: float
    l_trace_uH: float
    l_total_uH: float
    r_series_ohm: float
    c_series_pF: float
    resonance_mhz: float
    trace: CalculationTrace

    def summary(self) -> str:
        """Gibt eine kompakte Zusammenfassung der Parameter zurück."""
        return (
            f"CoilParameters:\n"
            f"  L_track  = {self.l_track_uH:.4f} µH\n"
            f"  L_vias   = {self.l_vias_uH:.4f} µH\n"
            f"  L_trace  = {self.l_trace_uH:.4f} µH\n"
            f"  L_total  = {self.l_total_uH:.4f} µH\n"
            f"  R_series = {self.r_series_ohm:.4f} Ω\n"
            f"  C_series = {self.c_series_pF:.2f} pF\n"
            f"  f_res    = {self.resonance_mhz:.2f} MHz\n"
        )
