"""
pytest conftest.py – projektweite Fixtures und Konfiguration.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from pcb_rogowski.domain.board.models import Board, Layer, LayerType, LineFeature, PadFeature, Point2D
from pcb_rogowski.domain.trace.models import TraceLayout, TraceClassification, TraceRole, ViaWindow
from pcb_rogowski.domain.common.trace import CalculationTrace, TraceStep, QualityStatus


# ---------------------------------------------------------------------------
# Board-Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_board() -> Board:
    """Minimales Board mit zwei Kupferlagen und je 2 Trace-Segmenten."""
    top = Layer(name="top", layer_type=LayerType.COPPER, index=0)
    bot = Layer(name="bottom", layer_type=LayerType.COPPER, index=1)

    top.lines = [
        LineFeature("f001", Point2D(0.0, 0.0), Point2D(1.0, 0.0), width_mm=0.15, net_name="WINDING"),
        LineFeature("f002", Point2D(1.0, 0.0), Point2D(2.0, 0.0), width_mm=0.15, net_name="WINDING"),
    ]
    bot.lines = [
        LineFeature("f003", Point2D(0.0, 1.0), Point2D(1.0, 1.0), width_mm=0.15, net_name="WINDING"),
    ]

    return Board(name="test_board", layers=[top, bot])


# ---------------------------------------------------------------------------
# TraceLayout-Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_trace_layout() -> TraceLayout:
    """Minimales TraceLayout mit 2 Windungs-Traces und einem Via-Fenster."""
    classifications = [
        TraceClassification("f001", "top", TraceRole.WINDING, sigma=+1, window_id="W1"),
        TraceClassification("f002", "top", TraceRole.WINDING, sigma=+1, window_id="W1"),
        TraceClassification("f003", "bottom", TraceRole.RETURN, sigma=-1, window_id=None),
    ]
    via_windows = [
        ViaWindow("W1", x_min_mm=0.0, y_min_mm=0.0, x_max_mm=5.0, y_max_mm=3.0, sigma=+1),
    ]
    return TraceLayout(
        board_name="test_board",
        classifications=classifications,
        via_windows=via_windows,
    )


# ---------------------------------------------------------------------------
# CalculationTrace-Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def example_trace() -> CalculationTrace:
    """Beispiel-CalculationTrace für Tests."""
    steps = (
        TraceStep(
            name="Berechne L_track",
            formula="L = µ₀ * N² * A / l",
            inputs={"N": 10.0, "A_mm2": 15.0, "l_mm": 50.0},
            output=0.123,
            unit="µH",
        ),
    )
    return CalculationTrace(
        calculation_name="Test-Berechnung",
        steps=steps,
        warnings=(),
        quality_status=QualityStatus.OK,
        source_files=("test_board.odb",),
        config_versions={"geometry": "0.1", "materials": "0.1"},
        timestamp="2026-04-01T10:00:00",
        git_commit="abc1234",
    )


# ---------------------------------------------------------------------------
# Hilfsfunktionen für Fixture-Dateipfade
# ---------------------------------------------------------------------------

@pytest.fixture
def fixtures_dir() -> Path:
    """Gibt das Verzeichnis mit Test-Fixtures zurück."""
    return Path(__file__).parent / "fixtures"
