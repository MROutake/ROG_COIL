"""
Infrastructure: ODB++-Loader (Stub).

Implementiert die BoardRepository-Schnittstelle für ODB++-Dateien aus Altium.
Der vollständige Parser wird in Sprint 2 implementiert.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pcb_rogowski.domain.board.models import Board, Layer, LayerType
from pcb_rogowski.domain.trace.models import TraceLayout

logger = logging.getLogger(__name__)


class OdbBoardLoader:
    """
    Lädt ein ODB++-Archiv und wandelt es in ein Board-Domainobjekt um.

    Status: Stub – Sprint 2 implementiert den vollständigen Parser.
    """

    def load_from_odb(self, path: Path) -> Board:
        """
        Parst ein ODB++-Archiv und gibt ein Board zurück.

        Args:
            path: Pfad zur ODB++-Datei oder zum entpackten Ordner.

        Returns:
            Befülltes Board-Objekt.

        Raises:
            FileNotFoundError: Wenn die Datei nicht existiert.
            ValueError: Wenn das Format nicht erkannt wird.
        """
        if not path.exists():
            raise FileNotFoundError(f"ODB++-Datei nicht gefunden: {path}")

        logger.info("Lade ODB++-Projekt: %s", path)

        # TODO Sprint 2: Vollständigen ODB++-Parser implementieren
        # Vorläufig: leeres Board zurückgeben
        board = Board(name=path.stem, source_file=str(path))
        logger.warning("ODB++-Parser ist noch nicht implementiert (Sprint 2)")
        return board

    def save_trace_layout(self, layout: TraceLayout, path: Path) -> None:
        """Speichert eine Trace-Klassifikation – delegiert an PersistenceManager."""
        from pcb_rogowski.infrastructure.persistence.manager import PersistenceManager
        PersistenceManager().save_trace_layout(layout, path)

    def load_trace_layout(self, path: Path) -> TraceLayout:
        """Lädt eine Trace-Klassifikation – delegiert an PersistenceManager."""
        from pcb_rogowski.infrastructure.persistence.manager import PersistenceManager
        return PersistenceManager().load_trace_layout(path)
