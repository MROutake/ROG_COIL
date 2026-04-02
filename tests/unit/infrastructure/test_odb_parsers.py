"""
Unit-Tests: ODB++ Parser-Module.

Tests für:
- MatrixParser      (matrix/matrix → LayerMeta)
- FeaturesParser    (features → LineFeature / PadFeature)
- ProfileParser     (profile → bounding box)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pcb_rogowski.domain.board.models import LayerType
from pcb_rogowski.infrastructure.odb._features_parser import FeaturesParser
from pcb_rogowski.infrastructure.odb._matrix_parser import MatrixParser
from pcb_rogowski.infrastructure.odb._profile_parser import ProfileParser
from pcb_rogowski.infrastructure.odb.exceptions import (
    OdbFileNotFoundError,
    OdbFormatError,
    OdbParseError,
)

# ---------------------------------------------------------------------------
# Fixture-Pfade
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "odb_minimal"


# ===========================================================================
# MatrixParser
# ===========================================================================


class TestMatrixParser:
    """Tests für den matrix/matrix Parser."""

    parser = MatrixParser()

    def test_parse_returns_correct_layer_count(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        assert len(layers) == 4

    def test_signal_layer_mapped_to_copper(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        top = next(la for la in layers if la.name == "top_layer")
        assert top.layer_type == LayerType.COPPER

    def test_drill_layer_mapped_to_drill(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        drill = next(la for la in layers if la.odb_type == "DRILL")
        assert drill.layer_type == LayerType.DRILL

    def test_silkscreen_layer_mapped_correctly(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        silk = next(la for la in layers if la.name == "top_overlay")
        assert silk.layer_type == LayerType.SILKSCREEN

    def test_layers_sorted_by_row(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        rows = [la.row for la in layers]
        assert rows == sorted(rows)

    def test_names_are_lowercase(self) -> None:
        layers = self.parser.parse(FIXTURE_ROOT / "matrix" / "matrix")
        for la in layers:
            assert la.name == la.name.lower(), f"Name nicht lowercase: {la.name!r}"

    def test_missing_file_raises_odb_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(OdbFileNotFoundError):
            self.parser.parse(tmp_path / "nonexistent" / "matrix")

    def test_missing_name_raises_format_error(self, tmp_path: Path) -> None:
        bad_matrix = tmp_path / "matrix"
        bad_matrix.write_text("LAYER {\n    ROW=1\n    TYPE=SIGNAL\n}\n")
        with pytest.raises(OdbFormatError):
            self.parser.parse(bad_matrix)

    def test_non_integer_row_raises_format_error(self, tmp_path: Path) -> None:
        bad_matrix = tmp_path / "matrix"
        bad_matrix.write_text("LAYER {\n    ROW=X\n    TYPE=SIGNAL\n    NAME=test\n}\n")
        with pytest.raises(OdbFormatError):
            self.parser.parse(bad_matrix)

    def test_empty_matrix_returns_empty_list(self, tmp_path: Path) -> None:
        empty = tmp_path / "matrix"
        empty.write_text("# no layers\n")
        result = self.parser.parse(empty)
        assert result == []


# ===========================================================================
# FeaturesParser
# ===========================================================================


class TestFeaturesParser:
    """Tests für den features-Datei Parser."""

    parser = FeaturesParser()
    top_features = FIXTURE_ROOT / "steps" / "pcb" / "layers" / "top_layer" / "features"
    bot_features = FIXTURE_ROOT / "steps" / "pcb" / "layers" / "bottom_layer" / "features"
    drill_features = (
        FIXTURE_ROOT / "steps" / "pcb" / "layers" / "drill_plated_all" / "features"
    )

    def test_line_count_top_layer(self) -> None:
        lines, pads = self.parser.parse(self.top_features, layer_name="top_layer")
        assert len(lines) == 3

    def test_pad_count_top_layer(self) -> None:
        lines, pads = self.parser.parse(self.top_features, layer_name="top_layer")
        assert len(pads) == 1

    def test_line_width_converted_from_mils(self) -> None:
        """$0 r196.8504 mils → 196.8504 × 0.0254 ≈ 5.00 mm"""
        lines, _ = self.parser.parse(self.top_features, layer_name="top_layer")
        expected_mm = 196.8504 * 0.0254
        for line in lines:
            assert abs(line.width_mm - expected_mm) < 1e-4

    def test_pad_diameter_converted_from_mils(self) -> None:
        """$1 r393.7008 mils → 393.7008 × 0.0254 ≈ 10.00 mm"""
        _, pads = self.parser.parse(self.top_features, layer_name="top_layer")
        expected_mm = 393.7008 * 0.0254
        assert abs(pads[0].diameter_mm - expected_mm) < 1e-4

    def test_line_layer_name_assigned(self) -> None:
        lines, _ = self.parser.parse(self.top_features, layer_name="top_layer")
        for line in lines:
            assert line.layer_name == "top_layer"

    def test_pad_layer_name_assigned(self) -> None:
        _, pads = self.parser.parse(self.top_features, layer_name="top_layer")
        assert pads[0].layer_name == "top_layer"

    def test_pads_on_drill_layer_are_vias(self) -> None:
        _, pads = self.parser.parse(
            self.drill_features, layer_name="drill_plated_all", is_drill_layer=True
        )
        assert len(pads) == 1
        assert pads[0].is_via is True

    def test_pads_on_copper_layer_are_not_vias(self) -> None:
        _, pads = self.parser.parse(self.top_features, layer_name="top_layer")
        assert pads[0].is_via is False

    def test_bottom_layer_has_one_line(self) -> None:
        lines, pads = self.parser.parse(self.bot_features, layer_name="bottom_layer")
        assert len(lines) == 1
        assert len(pads) == 0

    def test_empty_features_file(self, tmp_path: Path) -> None:
        """Leere Datei → leere Listen, kein Crash."""
        empty = tmp_path / "features"
        empty.write_text("UNITS=MM\n")
        lines, pads = self.parser.parse(empty, layer_name="dummy")
        assert lines == []
        assert pads == []

    def test_missing_file_raises_odb_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(OdbFileNotFoundError):
            self.parser.parse(tmp_path / "nonexistent", layer_name="dummy")

    def test_malformed_line_feature_raises_parse_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "features"
        bad.write_text("UNITS=MM\nL 1.0\n")  # too few fields
        with pytest.raises(OdbParseError):
            self.parser.parse(bad, layer_name="dummy")

    def test_coordinates_preserved(self) -> None:
        lines, _ = self.parser.parse(self.top_features, layer_name="top_layer")
        first = lines[0]
        assert first.start.x_mm == pytest.approx(0.0)
        assert first.start.y_mm == pytest.approx(5.0)
        assert first.end.x_mm == pytest.approx(5.0)
        assert first.end.y_mm == pytest.approx(5.0)


# ===========================================================================
# ProfileParser
# ===========================================================================


class TestProfileParser:
    """Tests für den profile-Datei Parser."""

    parser = ProfileParser()
    profile = FIXTURE_ROOT / "steps" / "pcb" / "profile"

    def test_returns_bounding_box_tuple(self) -> None:
        bbox = self.parser.parse(self.profile)
        assert bbox is not None
        assert len(bbox) == 4

    def test_x_min_is_zero(self) -> None:
        bbox = self.parser.parse(self.profile)
        assert bbox is not None
        assert bbox[0] == pytest.approx(0.0)

    def test_y_min_is_zero(self) -> None:
        bbox = self.parser.parse(self.profile)
        assert bbox is not None
        assert bbox[1] == pytest.approx(0.0)

    def test_x_max_is_correct(self) -> None:
        bbox = self.parser.parse(self.profile)
        assert bbox is not None
        assert bbox[2] == pytest.approx(20.0)

    def test_y_max_is_correct(self) -> None:
        bbox = self.parser.parse(self.profile)
        assert bbox is not None
        assert bbox[3] == pytest.approx(10.0)

    def test_empty_profile_returns_none(self, tmp_path: Path) -> None:
        empty = tmp_path / "profile"
        empty.write_text("UNITS=MM\n")
        result = self.parser.parse(empty)
        assert result is None

    def test_missing_file_raises_odb_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(OdbFileNotFoundError):
            self.parser.parse(tmp_path / "profile_missing")
