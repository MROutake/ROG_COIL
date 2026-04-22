"""
Domain-Modelle: Trace-Klassifikation und Via-Fenster.

Definiert, wie einzelne Leiterbahn-Segmente und Via-Bereiche
für die Rogowski-Spule klassifiziert werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TraceRole(str, Enum):
    """Fachliche Rolle eines Trace-Segments in der Rogowski-Spule."""

    WINDING = "winding"       # Windungsleiter
    CONNECTION = "connection"  # Verbindungsleiter (kein Beitrag zur Induktivität)
    RETURN = "return"         # Rückleiter


@dataclass(frozen=True)
class TraceClassification:
    """
    Klassifikation eines einzelnen Leiterbahn-Segments.

    Attributes:
        feature_id: Referenz auf das LineFeature im Board-Modell.
        layer_name: Lagenname des Segments.
        role: Fachliche Rolle (winding, connection, return).
        sigma: Orientierungsvorzeichen ±1 für die Flussintegration.
        window_id: Zugehöriges Via-Fenster (optional).
    """

    feature_id: str
    layer_name: str
    role: TraceRole
    sigma: int  # +1 oder -1
    window_id: str | None = None

    def __post_init__(self) -> None:
        if self.sigma not in (-1, 1):
            raise ValueError(f"sigma muss ±1 sein, erhalten: {self.sigma}")


@dataclass(frozen=True)
class ViaWindow:
    """
    Definiert ein rechteckiges Via-Fenster für die M-Berechnung.

    Das Fenster beschreibt den Bereich, durch den der Primärleiter
    (Busbar) verläuft und für den ein Mutual-Inductance-Beitrag
    berechnet wird.

    Attributes:
        window_id: Eindeutiger Bezeichner.
        x_min_mm, y_min_mm, x_max_mm, y_max_mm: Eckpunkte in mm.
        sigma: Vorzeichen für Summation (+1 / -1).
        layer_pair: (obere Lage, untere Lage) der zugehörigen Vias.
        via_a_xy: Position des ersten Vias [x, y] in mm (optional).
        via_b_xy: Position des zweiten Vias [x, y] in mm (optional).
        dist_mm: Euklidische Distanz zwischen den beiden Vias [mm].
        h_via_mm: Via-Höhe (PCB-Gesamtdicke) [mm] (optional).
    """

    window_id: str
    x_min_mm: float
    y_min_mm: float
    x_max_mm: float
    y_max_mm: float
    sigma: int
    layer_pair: tuple[str, str] | None = None
    via_a_xy: tuple[float, float] | None = None
    via_b_xy: tuple[float, float] | None = None
    dist_mm: float | None = None
    h_via_mm: float | None = None

    @property
    def width_mm(self) -> float:
        return self.x_max_mm - self.x_min_mm

    @property
    def height_mm(self) -> float:
        return self.y_max_mm - self.y_min_mm

    @property
    def area_mm2(self) -> float:
        return self.width_mm * self.height_mm


@dataclass
class TraceLayout:
    """
    Vollständige Klassifikation eines Boards für eine Rogowski-Spule.

    Enthält alle klassifizierten Trace-Segmente und Via-Fenster.
    Wird als Eingabe für alle Berechnungsmodule verwendet.
    """

    board_name: str
    classifications: list[TraceClassification] = field(default_factory=list)
    via_windows: list[ViaWindow] = field(default_factory=list)

    @property
    def winding_traces(self) -> list[TraceClassification]:
        return [c for c in self.classifications if c.role == TraceRole.WINDING]

    @property
    def return_traces(self) -> list[TraceClassification]:
        return [c for c in self.classifications if c.role == TraceRole.RETURN]

    def get_window(self, window_id: str) -> ViaWindow | None:
        return next((w for w in self.via_windows if w.window_id == window_id), None)
