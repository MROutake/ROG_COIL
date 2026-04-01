"""
Unit-Tests: TraceClassification und ViaWindow.
"""

from __future__ import annotations

import pytest

from pcb_rogowski.domain.trace.models import (
    TraceClassification,
    TraceLayout,
    TraceRole,
    ViaWindow,
)


class TestTraceClassification:
    def test_valid_sigma_plus_one(self) -> None:
        tc = TraceClassification("f001", "top", TraceRole.WINDING, sigma=+1)
        assert tc.sigma == 1

    def test_valid_sigma_minus_one(self) -> None:
        tc = TraceClassification("f002", "bottom", TraceRole.RETURN, sigma=-1)
        assert tc.sigma == -1

    def test_invalid_sigma_raises(self) -> None:
        with pytest.raises(ValueError, match="sigma"):
            TraceClassification("f003", "top", TraceRole.WINDING, sigma=0)

    def test_sigma_two_raises(self) -> None:
        with pytest.raises(ValueError):
            TraceClassification("f004", "top", TraceRole.WINDING, sigma=2)


class TestViaWindow:
    def test_width(self) -> None:
        w = ViaWindow("W1", 0.0, 0.0, 5.0, 3.0, sigma=+1)
        assert w.width_mm == pytest.approx(5.0)

    def test_height(self) -> None:
        w = ViaWindow("W1", 0.0, 0.0, 5.0, 3.0, sigma=+1)
        assert w.height_mm == pytest.approx(3.0)

    def test_area(self) -> None:
        w = ViaWindow("W1", 0.0, 0.0, 5.0, 3.0, sigma=+1)
        assert w.area_mm2 == pytest.approx(15.0)


class TestTraceLayout:
    def test_winding_traces(self, minimal_trace_layout: TraceLayout) -> None:
        winding = minimal_trace_layout.winding_traces
        assert len(winding) == 2
        assert all(t.role == TraceRole.WINDING for t in winding)

    def test_return_traces(self, minimal_trace_layout: TraceLayout) -> None:
        returns = minimal_trace_layout.return_traces
        assert len(returns) == 1
        assert returns[0].role == TraceRole.RETURN

    def test_get_window_found(self, minimal_trace_layout: TraceLayout) -> None:
        w = minimal_trace_layout.get_window("W1")
        assert w is not None
        assert w.window_id == "W1"

    def test_get_window_not_found(self, minimal_trace_layout: TraceLayout) -> None:
        w = minimal_trace_layout.get_window("NONEXISTENT")
        assert w is None
