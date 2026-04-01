"""
DTOs (Data Transfer Objects) für den App-Layer.

DTOs transportieren Daten zwischen UI, Use Cases und Domain-Services,
ohne dass dabei Domain-Objekte direkt exponiert werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LoadBoardRequest:
    """Anfrage zum Laden eines Board-Projekts."""

    odb_path: Path
    project_name: str = ""


@dataclass(frozen=True)
class LoadBoardResponse:
    """Antwort nach dem Laden eines Board-Projekts."""

    success: bool
    board_name: str
    layer_count: int
    feature_count: int
    error_message: str = ""


@dataclass(frozen=True)
class CoilParameterRequest:
    """Anfrage für die Spulen-Parameter-Berechnung."""

    board_name: str
    config_path: Path | None = None
    temperature_celsius: float = 20.0


@dataclass
class LayoutStatisticsDTO:
    """Zusammenfassung der Layout-Statistiken für die GUI."""

    total_winding_length_mm: float = 0.0
    total_return_length_mm: float = 0.0
    num_turns: int = 0
    num_via_windows: int = 0
    mean_trace_width_mm: float = 0.0
    warnings: list[str] = field(default_factory=list)
