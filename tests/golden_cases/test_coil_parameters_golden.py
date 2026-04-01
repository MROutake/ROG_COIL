"""
Golden Cases: Referenzfälle für die Coil-Parameter-Berechnung.

Diese Fälle dienen als Regressions-Sicherheitsnetz.
Sollwerte sind aus analytischen Handberechnungen oder verifizierten
Quellen abgeleitet.

HINWEIS: Diese Tests werden ERST aktiv, wenn CoilParameterServiceImpl
implementiert ist (Sprint 3). Bis dahin werden sie übersprungen.
"""

from __future__ import annotations

import pytest

# Sobald CoilParameterServiceImpl existiert, hier importieren:
# from pcb_rogowski.domain.coil.service import CoilParameterServiceImpl


@pytest.mark.skip(reason="Sprint 3 – CoilParameterServiceImpl noch nicht implementiert")
class TestCoilParameterGoldenCases:
    """
    Golden Cases für die Spulen-Parameter-Berechnung.

    Jeder Testfall repräsentiert eine vollständig verifizierte Geometrie
    mit bekannten Sollwerten (±5% Toleranz).

    Quellen:
    - GC-001: Handberechnung aus Diplomarbeit, Kapitel 5.2
    - GC-002: FEM-Simulation mit ANSYS Maxwell
    - GC-003: Messung am Prototyp
    """

    def test_gc001_standard_geometry(self) -> None:
        """
        GC-001: Standard-Geometrie (N=40, w=0.15mm, d=0.3mm, h=1.6mm).

        Erwartete Werte:
        - L_total ≈ 0.850 µH ± 5%
        - R_series ≈ 8.2 Ω ± 10%
        - f_res > 20 MHz
        """
        pytest.skip("Sprint 3")

    def test_gc002_compact_geometry(self) -> None:
        """
        GC-002: Kompakte Geometrie (N=20, w=0.1mm, d=0.2mm, h=0.8mm).

        Erwartete Werte:
        - L_total ≈ 0.210 µH ± 5%
        - R_series ≈ 12.0 Ω ± 10%
        """
        pytest.skip("Sprint 3")

    def test_gc003_high_turn_count(self) -> None:
        """
        GC-003: Hohe Windungszahl (N=80).

        Erwartete Werte:
        - L_total ≈ 3.4 µH ± 5%
        """
        pytest.skip("Sprint 3")
