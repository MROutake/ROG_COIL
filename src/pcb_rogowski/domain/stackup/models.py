"""
Domain-Modelle: Stackup und Materialeigenschaften.

Definiert die Leiterplattenstruktur (Lagenaufbau) und die
verwendeten Materialparameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CopperLayerSpec:
    """Spezifikation einer Kupferlage im Stackup."""

    name: str
    thickness_um: float   # Kupferdicke in µm (typisch: 35, 70, 105)
    index: int            # Position im Stackup (0 = Top)


@dataclass(frozen=True)
class DielectricSpec:
    """Spezifikation einer Dielektrikumslage zwischen zwei Kupferlagen."""

    name: str
    thickness_mm: float
    epsilon_r: float      # Relative Permittivität
    loss_tangent: float   # Verlustfaktor tan(δ)


@dataclass
class Stackup:
    """
    Vollständiger Lagenaufbau einer Leiterplatte.

    Copper- und Dielektrikums-Lagen werden abwechselnd gelistet.
    """

    name: str
    copper_layers: list[CopperLayerSpec] = field(default_factory=list)
    dielectrics: list[DielectricSpec] = field(default_factory=list)

    @property
    def total_thickness_mm(self) -> float:
        """Gesamtdicke der Leiterplatte in mm."""
        return sum(d.thickness_mm for d in self.dielectrics)

    @property
    def num_copper_layers(self) -> int:
        return len(self.copper_layers)


@dataclass(frozen=True)
class MaterialSet:
    """
    Satz physikalischer Materialkonstanten für Berechnungen.

    Attributes:
        rho_cu_ohm_m: Spez. Widerstand Kupfer bei 20°C [Ω·m].
        mu_0: Magnetische Feldkonstante [H/m].
        epsilon_0: Elektrische Feldkonstante [F/m].
        temperature_coefficient_cu: Temperaturkoeffizient Kupfer [1/K].
    """

    rho_cu_ohm_m: float = 1.72e-8
    mu_0: float = 1.2566370614e-6
    epsilon_0: float = 8.8541878128e-12
    temperature_coefficient_cu: float = 3.9e-3
