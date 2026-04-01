"""
Unit-Tests: CalculationTrace – Serialisierung und Markdown-Export.
"""

from __future__ import annotations

from pcb_rogowski.domain.common.trace import (
    CalculationTrace,
    QualityStatus,
    TraceStep,
)


class TestTraceStep:
    def test_creation(self) -> None:
        step = TraceStep(
            name="Schritt 1",
            formula="L = µ₀·N²·A/l",
            inputs={"N": 10.0, "A_mm2": 15.0},
            output=0.5,
            unit="µH",
        )
        assert step.output == 0.5
        assert step.unit == "µH"

    def test_immutable(self) -> None:
        step = TraceStep("test", "f=ma", {"m": 1.0}, 9.81, "N/kg")
        # frozen=True – kein Setzen möglich
        try:
            step.output = 1.0  # type: ignore[misc]
            assert False, "Sollte nicht erreichbar sein"
        except (AttributeError, TypeError):
            pass  # erwartet


class TestCalculationTrace:
    def test_to_dict_contains_name(self, example_trace: CalculationTrace) -> None:
        d = example_trace.to_dict()
        assert d["calculation_name"] == "Test-Berechnung"

    def test_to_dict_contains_steps(self, example_trace: CalculationTrace) -> None:
        d = example_trace.to_dict()
        assert len(d["steps"]) == 1
        assert d["steps"][0]["name"] == "Berechne L_track"

    def test_to_json_is_valid_json(self, example_trace: CalculationTrace) -> None:
        import json
        json_str = example_trace.to_json()
        parsed = json.loads(json_str)
        assert parsed["calculation_name"] == "Test-Berechnung"

    def test_to_markdown_contains_header(self, example_trace: CalculationTrace) -> None:
        md = example_trace.to_markdown()
        assert "# Rechen-Protokoll" in md
        assert "Test-Berechnung" in md

    def test_to_markdown_contains_step(self, example_trace: CalculationTrace) -> None:
        md = example_trace.to_markdown()
        assert "Berechne L_track" in md

    def test_quality_status_ok(self, example_trace: CalculationTrace) -> None:
        assert example_trace.quality_status == QualityStatus.OK

    def test_warnings_empty(self, example_trace: CalculationTrace) -> None:
        assert len(example_trace.warnings) == 0
