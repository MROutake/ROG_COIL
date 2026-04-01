"""
Domain-Modelle: Board, Layer und PCB-Features.

Dieses Modul definiert die internen Datenstrukturen für den ODB++-Import.
Keine GUI-, Infrastruktur- oder Konfigurationsabhängigkeiten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FeatureType(str, Enum):
    """Typ eines PCB-Features."""

    LINE = "line"
    PAD = "pad"
    ARC = "arc"
    TEXT = "text"


class LayerType(str, Enum):
    """Klassifikation einer PCB-Lage."""

    COPPER = "copper"
    DRILL = "drill"
    SILKSCREEN = "silkscreen"
    SOLDERMASK = "soldermask"
    OUTLINE = "outline"
    OTHER = "other"


@dataclass(frozen=True)
class Point2D:
    """2D-Punkt in Board-Einheiten (mm)."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class LineFeature:
    """Leiterbahn-Segment auf einer Kupferlage."""

    feature_id: str
    start: Point2D
    end: Point2D
    width_mm: float
    net_name: str | None = None
    layer_name: str = ""


@dataclass(frozen=True)
class PadFeature:
    """Pad- oder Via-Landezone auf einer Kupferlage."""

    feature_id: str
    center: Point2D
    diameter_mm: float
    net_name: str | None = None
    is_via: bool = False
    layer_name: str = ""


@dataclass
class Layer:
    """Repräsentiert eine einzelne PCB-Lage."""

    name: str
    layer_type: LayerType
    index: int  # Stackup-Position, 0 = oberste Kupferlage
    lines: list[LineFeature] = field(default_factory=list)
    pads: list[PadFeature] = field(default_factory=list)

    @property
    def copper_feature_count(self) -> int:
        """Gesamtzahl aller Kupfer-Features auf dieser Lage."""
        return len(self.lines) + len(self.pads)


@dataclass
class Board:
    """
    Vollständiges PCB-Modell nach ODB++-Import.

    Enthält alle Lagen mit deren Features. Wird durch den ODB-Loader
    befüllt und dient als Read-Only-Basis für alle Domainberechnungen.
    """

    name: str
    layers: list[Layer] = field(default_factory=list)
    outline_mm: tuple[float, float, float, float] | None = None  # (x_min, y_min, x_max, y_max)
    source_file: str = ""

    def get_layer(self, name: str) -> Layer | None:
        """Sucht eine Lage anhand ihres Namens."""
        return next((la for la in self.layers if la.name == name), None)

    @property
    def copper_layers(self) -> list[Layer]:
        """Gibt alle Kupferlagen zurück, sortiert nach Stackup-Index."""
        return sorted(
            [la for la in self.layers if la.layer_type == LayerType.COPPER],
            key=lambda la: la.index,
        )
