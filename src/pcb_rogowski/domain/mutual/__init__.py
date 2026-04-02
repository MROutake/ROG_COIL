"""Gegenseitige Induktivität: Fenster-Extraktion und M_prim-Berechnung."""

from pcb_rogowski.domain.mutual.calculator import (
    ConductorConfig,
    MutualInductanceCalculator,
)
from pcb_rogowski.domain.mutual.models import (
    MutualInductanceResult,
    WindowMutualContribution,
)
from pcb_rogowski.domain.mutual.service import MutualInductanceService
from pcb_rogowski.domain.mutual.window_extractor import (
    WindowExtractionResult,
    WindowExtractor,
)

__all__ = [
    "ConductorConfig",
    "MutualInductanceCalculator",
    "MutualInductanceResult",
    "MutualInductanceService",
    "WindowExtractionResult",
    "WindowExtractor",
    "WindowMutualContribution",
]
