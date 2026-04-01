"""
UI: ViewModels für die Desktop-Oberfläche.

ViewModels trennen den UI-Zustand von der Domainlogik.
Sie halten aufbereitete Anzeigedaten und leiten UI-Aktionen
an Use Cases weiter.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CoilParametersViewModel:
    """Aufbereitete Spulen-Parameter für die Anzeige im Analysis-Tab."""

    l_track_str: str = "–"
    l_vias_str: str = "–"
    l_trace_str: str = "–"
    l_total_str: str = "–"
    r_series_str: str = "–"
    c_series_str: str = "–"
    resonance_str: str = "–"
    quality_status: str = "–"
    warnings: list[str] = field(default_factory=list)
    has_results: bool = False

    @classmethod
    def from_domain(cls, params: object) -> "CoilParametersViewModel":
        """Erstellt ein ViewModel aus einem CoilParameters-Domain-Objekt."""
        # Zirkulärer Import vermieden – Type Hint als string
        from pcb_rogowski.domain.coil.models import CoilParameters
        assert isinstance(params, CoilParameters)
        return cls(
            l_track_str=f"{params.l_track_uH:.4f} µH",
            l_vias_str=f"{params.l_vias_uH:.4f} µH",
            l_trace_str=f"{params.l_trace_uH:.4f} µH",
            l_total_str=f"{params.l_total_uH:.4f} µH",
            r_series_str=f"{params.r_series_ohm:.4f} Ω",
            c_series_str=f"{params.c_series_pF:.2f} pF",
            resonance_str=f"{params.resonance_mhz:.2f} MHz",
            quality_status=params.trace.quality_status.value,
            warnings=list(params.trace.warnings),
            has_results=True,
        )


@dataclass
class MutualInductanceViewModel:
    """Aufbereitete Gegeninduktivität für den Mutual-Tab."""

    m_total_str: str = "–"
    window_rows: list[dict[str, str]] = field(default_factory=list)
    has_results: bool = False

    @classmethod
    def from_domain(cls, result: object) -> "MutualInductanceViewModel":
        """Erstellt ein ViewModel aus einem MutualInductanceResult."""
        from pcb_rogowski.domain.mutual.models import MutualInductanceResult
        assert isinstance(result, MutualInductanceResult)
        rows = [
            {
                "window_id": w.window_id,
                "m_nH": f"{w.m_nH:+.4f} nH",
                "sigma": f"{w.sigma:+d}",
                "area_mm2": f"{w.area_mm2:.2f} mm²",
                "percentage": f"{w.percentage:.1f}%",
            }
            for w in result.window_contributions
        ]
        return cls(
            m_total_str=f"{result.m_total_nH:.4f} nH",
            window_rows=rows,
            has_results=True,
        )
