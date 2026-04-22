"""
Globaler GUI-Zustand: Liste aller Designs + Cache der Analyseergebnisse.

``ProjectState`` sendet Qt-Signale, sobald sich ein Design aendert,
damit sich Tabs unabhaengig neu rendern.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from pcb_rogowski.app.use_cases.analyze_design import AnalysisResult, DesignInputs
from pcb_rogowski.infrastructure.persistence import project_io


class ProjectState(QObject):
    """Zentrale State-Haltung (Single Source of Truth fuer alle Tabs)."""

    # Signale ----------------------------------------------------------------
    designs_changed = pyqtSignal()               # Liste geaendert (add/remove/update)
    selection_changed = pyqtSignal(int)          # aktueller Index
    analysis_updated = pyqtSignal(int)           # Analyseergebnis fuer Design i neu

    def __init__(self) -> None:
        super().__init__()
        self._designs: list[DesignInputs] = []
        self._results: dict[int, AnalysisResult] = {}
        # In-Memory-Buffer, damit Bearbeitungen in Tab 2 ueber
        # Tab-/Design-Wechsel hinweg erhalten bleiben (bis zum Speichern/Exit).
        self._specs: dict[int, object] = {}
        self._windows: dict[int, object] = {}
        self._current: int = -1
        self._project_path: Path | None = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def designs(self) -> list[DesignInputs]:
        return list(self._designs)

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def current_design(self) -> DesignInputs | None:
        if 0 <= self._current < len(self._designs):
            return self._designs[self._current]
        return None

    @property
    def project_path(self) -> Path | None:
        return self._project_path

    def result_of(self, index: int) -> Optional[AnalysisResult]:
        return self._results.get(index)

    def current_result(self) -> AnalysisResult | None:
        return self._results.get(self._current)

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def add_design(self, design: DesignInputs) -> int:
        self._designs.append(design)
        self.designs_changed.emit()
        return len(self._designs) - 1

    def remove_design(self, index: int) -> None:
        if 0 <= index < len(self._designs):
            del self._designs[index]
            self._results.pop(index, None)
            # Ergebnis-Keys re-indexieren
            self._results = {
                (k if k < index else k - 1): v
                for k, v in self._results.items()
                if k != index
            }
            if self._current >= len(self._designs):
                self._current = len(self._designs) - 1
            self.designs_changed.emit()
            self.selection_changed.emit(self._current)

    def update_design(self, index: int, design: DesignInputs) -> None:
        if 0 <= index < len(self._designs):
            self._designs[index] = design
            # Cache verwerfen, da sich Pfade geaendert haben koennten
            self._results.pop(index, None)
            self.designs_changed.emit()

    def set_current(self, index: int) -> None:
        if self._current != index:
            self._current = index
            self.selection_changed.emit(index)

    def store_result(self, index: int, result: AnalysisResult) -> None:
        self._results[index] = result
        self.analysis_updated.emit(index)

    # ---- In-Memory-Buffer fuer Klassifikation + Fenster ----------------
    def get_spec(self, index: int) -> object | None:
        return self._specs.get(index)

    def set_spec(self, index: int, spec: object | None) -> None:
        if spec is None:
            self._specs.pop(index, None)
        else:
            self._specs[index] = spec

    def get_windows(self, index: int) -> object | None:
        """Liefert gepuffertes ``(list[ViaWindow], h_via_mm)``-Paar."""
        return self._windows.get(index)

    def set_windows(self, index: int, payload: object | None) -> None:
        if payload is None:
            self._windows.pop(index, None)
        else:
            self._windows[index] = payload

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load(self, path: Path) -> None:
        self._designs = project_io.load_project(path)
        self._results.clear()
        self._current = 0 if self._designs else -1
        self._project_path = Path(path)
        self.designs_changed.emit()
        self.selection_changed.emit(self._current)

    def save(self, path: Path) -> None:
        project_io.save_project(path, self._designs)
        self._project_path = Path(path)
