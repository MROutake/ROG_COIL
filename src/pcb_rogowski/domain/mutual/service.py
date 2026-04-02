"""
MutualInductanceService: Orchestriert die Berechnung der gegenseitigen
Induktivität M_prim zwischen Primärleiter und Rogowski-Spule.

Kombiniert:
    1. WindowExtractor    — extrahiert Via-Fenster aus Board/Layout
    2. Calculator         — berechnet M_m pro Fenster und M_ges
    3. Stackup-Info       — liefert h_eff (Via-Höhe)

Verwendung::

    from pcb_rogowski.domain.mutual.service import MutualInductanceService
    from pcb_rogowski.domain.mutual.calculator import ConductorConfig

    cond = ConductorConfig(x1_mm=0.0, y1_mm=0.0, x2_mm=5.0, y2_mm=0.0)
    svc  = MutualInductanceService(conductor=cond, stackup=stackup)
    result = svc.compute(layout, board)
    print(result.summary())
"""

from __future__ import annotations

import logging

from pcb_rogowski.domain.board.models import Board
from pcb_rogowski.domain.mutual.calculator import (
    ConductorConfig,
    MutualInductanceCalculator,
)
from pcb_rogowski.domain.mutual.models import MutualInductanceResult
from pcb_rogowski.domain.mutual.window_extractor import (
    WindowExtractionResult,
    WindowExtractor,
)
from pcb_rogowski.domain.stackup.models import Stackup
from pcb_rogowski.domain.trace.models import TraceLayout

logger = logging.getLogger(__name__)


class MutualInductanceService:
    """
    High-Level Service zur Berechnung von M_prim.

    Args:
        conductor:           Leiter-Konfiguration (Positionen in mm).
        stackup:             Stackup-Objekt für Via-Höhe (optional).
        winding_layer_name:  Name der Hauptlage (Standard: ``"top_layer"``).
        method:              ``"analytical"`` oder ``"numerical"``.
        grid_n:              Rasterpunkte für numerische Integration.
    """

    def __init__(
        self,
        conductor: ConductorConfig,
        stackup: Stackup | None = None,
        winding_layer_name: str = "top_layer",
        method: str = "analytical",
        grid_n: int = 50,
    ) -> None:
        self._conductor = conductor
        self._stackup = stackup
        self._winding_layer = winding_layer_name
        self._method = method
        self._grid_n = grid_n

    def compute(
        self,
        layout: TraceLayout,
        board: Board,
    ) -> MutualInductanceResult:
        """
        Berechnet M_prim aus Layout, Board und Leiterkonfiguration.

        Schritte:
            1. Via-Fenster extrahieren
            2. Effektive Fensterhöhe aus Stackup bestimmen
            3. M_prim berechnen

        Args:
            layout: Klassifiziertes TraceLayout.
            board:  Geladenes Board-Domainobjekt.

        Returns:
            MutualInductanceResult mit M_ges und Einzelbeiträgen.
        """
        # 1. Fenster extrahieren
        extractor = WindowExtractor(winding_layer_name=self._winding_layer)
        extraction = extractor.extract(layout, board)

        logger.info(extraction.summary())

        if not extraction.windows:
            logger.warning("Keine Fenster extrahiert — M_prim = 0.")
            return MutualInductanceCalculator(
                conductor=self._conductor,
                method=self._method,
            ).compute([])

        # 2. Effektive Fensterhöhe (= Via-Höhe = Stackup-Gesamtdicke)
        h_eff_mm: float | None = None
        if self._stackup is not None:
            h_eff_mm = self._stackup.total_thickness_mm
            logger.debug("h_eff aus Stackup: %.4f mm", h_eff_mm)

        # 3. M_prim berechnen
        calculator = MutualInductanceCalculator(
            conductor=self._conductor,
            method=self._method,
            grid_n=self._grid_n,
        )
        result = calculator.compute(extraction.windows, h_eff_mm=h_eff_mm)

        return result

    def compute_with_details(
        self,
        layout: TraceLayout,
        board: Board,
    ) -> tuple[MutualInductanceResult, WindowExtractionResult]:
        """
        Wie :meth:`compute`, gibt aber zusätzlich die Fenster-Extraktion zurück.
        """
        extractor = WindowExtractor(winding_layer_name=self._winding_layer)
        extraction = extractor.extract(layout, board)

        h_eff_mm: float | None = None
        if self._stackup is not None:
            h_eff_mm = self._stackup.total_thickness_mm

        calculator = MutualInductanceCalculator(
            conductor=self._conductor,
            method=self._method,
            grid_n=self._grid_n,
        )
        result = calculator.compute(extraction.windows, h_eff_mm=h_eff_mm)

        return result, extraction
