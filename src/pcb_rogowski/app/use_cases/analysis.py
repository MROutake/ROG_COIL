"""
Use Cases des Application Layers.

Jeder Use Case orchestriert einen vollständigen Anwendungsfall:
Er lädt Daten, delegiert an Domain-Services und gibt ein Ergebnis zurück.
Keine GUI-Abhängigkeiten. Keine direkten Datenbankzugriffe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol

from pcb_rogowski.app.dto.requests import (
    CoilParameterRequest,
    LoadBoardRequest,
    LoadBoardResponse,
    LayoutStatisticsDTO,
)
from pcb_rogowski.domain.board.models import Board
from pcb_rogowski.domain.coil.models import CoilParameters
from pcb_rogowski.domain.mutual.models import MutualInductanceResult
from pcb_rogowski.domain.trace.models import TraceLayout


class BoardRepository(Protocol):
    """Schnittstelle zum Laden und Speichern von Board-Projekten."""

    def load_from_odb(self, path: Path) -> Board: ...
    def save_trace_layout(self, layout: TraceLayout, path: Path) -> None: ...
    def load_trace_layout(self, path: Path) -> TraceLayout: ...


class CoilParameterService(Protocol):
    """Schnittstelle für die Spulen-Parameter-Berechnung."""

    def calculate(
        self, layout: TraceLayout, board: Board, temperature_celsius: float
    ) -> CoilParameters: ...


class MutualInductanceService(Protocol):
    """Schnittstelle für die Gegeninduktivitäts-Berechnung."""

    def calculate(
        self, layout: TraceLayout, board: Board
    ) -> MutualInductanceResult: ...


# ---------------------------------------------------------------------------
# Use Case 1: Board-Projekt laden
# ---------------------------------------------------------------------------

class LoadBoardProject:
    """
    Lädt ein ODB++-Projekt und erstellt ein Board-Domainobjekt.

    Ist der erste Schritt in jedem Analyse-Workflow.
    """

    def __init__(self, repository: BoardRepository) -> None:
        self._repo = repository

    def execute(self, request: LoadBoardRequest) -> tuple[Board, LoadBoardResponse]:
        try:
            board = self._repo.load_from_odb(request.odb_path)
            response = LoadBoardResponse(
                success=True,
                board_name=board.name,
                layer_count=len(board.copper_layers),
                feature_count=sum(la.copper_feature_count for la in board.copper_layers),
            )
            return board, response
        except Exception as exc:
            response = LoadBoardResponse(
                success=False,
                board_name="",
                layer_count=0,
                feature_count=0,
                error_message=str(exc),
            )
            raise RuntimeError(f"Board-Laden fehlgeschlagen: {exc}") from exc


# ---------------------------------------------------------------------------
# Use Case 2: Layout klassifizieren / Klassifikation speichern
# ---------------------------------------------------------------------------

class SaveTraceLayoutDefinition:
    """Speichert eine Trace-Klassifikation persistent."""

    def __init__(self, repository: BoardRepository) -> None:
        self._repo = repository

    def execute(self, layout: TraceLayout, target_path: Path) -> None:
        self._repo.save_trace_layout(layout, target_path)


# ---------------------------------------------------------------------------
# Use Case 3: Spulen-Parameter berechnen
# ---------------------------------------------------------------------------

class CalculateCoilParameters:
    """
    Berechnet alle elektrischen Parameter der Rogowski-Spule.

    Delegiert an den CoilParameterService im Domain-Layer.
    Gibt ein vollständiges CoilParameters-Objekt inkl. Trace zurück.
    """

    def __init__(
        self,
        coil_service: CoilParameterService,
        repository: BoardRepository,
    ) -> None:
        self._service = coil_service
        self._repo = repository

    def execute(self, request: CoilParameterRequest) -> CoilParameters:
        raise NotImplementedError(
            "CalculateCoilParameters.execute muss implementiert werden, "
            "sobald CoilParameterServiceImpl verfügbar ist."
        )


# ---------------------------------------------------------------------------
# Use Case 4: Gegeninduktivität berechnen
# ---------------------------------------------------------------------------

class CalculateAnalyticalMutualInductance:
    """
    Berechnet die analytische Gegeninduktivität fensterweise.

    Gibt ein MutualInductanceResult mit Einzelbeiträgen zurück.
    """

    def __init__(self, mutual_service: MutualInductanceService) -> None:
        self._service = mutual_service

    def execute(self, layout: TraceLayout, board: Board) -> MutualInductanceResult:
        return self._service.calculate(layout, board)


# ---------------------------------------------------------------------------
# Use Case 5: Vollständige Charakterisierung
# ---------------------------------------------------------------------------

class RunFullCharacterization:
    """
    Orchestriert einen vollständigen Analyse-Durchlauf:
    ODB laden → Klassifikation prüfen → L/R/C berechnen → M berechnen.
    """

    def __init__(
        self,
        load_board: LoadBoardProject,
        calc_coil: CalculateCoilParameters,
        calc_mutual: CalculateAnalyticalMutualInductance,
    ) -> None:
        self._load_board = load_board
        self._calc_coil = calc_coil
        self._calc_mutual = calc_mutual

    def execute(
        self,
        odb_path: Path,
        layout: TraceLayout,
        temperature_celsius: float = 20.0,
    ) -> tuple[CoilParameters, MutualInductanceResult]:
        request = LoadBoardRequest(odb_path=odb_path)
        board, response = self._load_board.execute(request)

        coil_request = CoilParameterRequest(
            board_name=board.name,
            temperature_celsius=temperature_celsius,
        )
        coil_params = self._calc_coil.execute(coil_request)
        mutual_result = self._calc_mutual.execute(layout, board)

        return coil_params, mutual_result
