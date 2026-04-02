"""
Unit-Tests: OdbBoardLoader.

Testet den vollständigen Lade-Pfad mit dem minimalen Fixture unter
``tests/fixtures/odb_minimal/``.

Abgedeckte Szenarien:
- Normaler Ladepfad → Board-Objekt mit korrekten Lagen zurück
- Fehlerhafter Pfad → OdbFileNotFoundError
- Archiv-Datei statt Verzeichnis → OdbFormatError
- Leere Layer-Verzeichnisse → leere Feature-Listen, kein Crash
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pcb_rogowski.domain.board.models import Board, LayerType
from pcb_rogowski.infrastructure.odb.exceptions import OdbFileNotFoundError, OdbFormatError
from pcb_rogowski.infrastructure.odb.loader import OdbBoardLoader

# ---------------------------------------------------------------------------
# Fixture-Pfad
# ---------------------------------------------------------------------------

FIXTURE_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "odb_minimal"


# ===========================================================================
# OdbBoardLoader Unit-Tests
# ===========================================================================


class TestOdbBoardLoaderWithFixture:
    """Tests mit dem synthetischen minimalen ODB-Fixture."""

    loader = OdbBoardLoader()

    def test_load_returns_board_instance(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        assert isinstance(board, Board)

    def test_board_has_correct_layer_count(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        assert len(board.layers) == 4

    def test_copper_layers_exist(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        copper = board.copper_layers
        assert len(copper) == 2

    def test_copper_layers_sorted_by_index(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        copper = board.copper_layers
        assert copper[0].index < copper[1].index

    def test_top_layer_has_lines(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        top = board.get_layer("top_layer")
        assert top is not None
        assert len(top.lines) == 3

    def test_top_layer_has_pads(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        top = board.get_layer("top_layer")
        assert top is not None
        assert len(top.pads) == 1

    def test_bottom_layer_has_one_line(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        bot = board.get_layer("bottom_layer")
        assert bot is not None
        assert len(bot.lines) == 1

    def test_drill_layer_pads_are_vias(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        drill = board.get_layer("drill_plated_all")
        assert drill is not None
        assert drill.layer_type == LayerType.DRILL
        assert all(p.is_via for p in drill.pads)

    def test_silkscreen_layer_has_no_features(self) -> None:
        """top_overlay hat keine features-Datei → leere Listen erwartet."""
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        silk = board.get_layer("top_overlay")
        assert silk is not None
        assert silk.copper_feature_count == 0

    def test_outline_bounding_box_set(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        assert board.outline_mm is not None
        assert len(board.outline_mm) == 4

    def test_outline_dimensions_correct(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        assert board.outline_mm is not None
        x_min, y_min, x_max, y_max = board.outline_mm
        assert x_max - x_min == pytest.approx(20.0)
        assert y_max - y_min == pytest.approx(10.0)

    def test_source_file_is_set(self) -> None:
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        assert board.source_file != ""

    def test_no_loose_dicts_in_board(self) -> None:
        """Sicherstellen, dass keine losen dict-Objekte in den Lagen sind."""
        board = self.loader.load_from_odb(FIXTURE_ROOT)
        for layer in board.layers:
            for line in layer.lines:
                # LineFeature ist ein dataclass, kein dict
                assert hasattr(line, "feature_id")
                assert hasattr(line, "start")
                assert hasattr(line, "width_mm")
            for pad in layer.pads:
                assert hasattr(pad, "feature_id")
                assert hasattr(pad, "center")
                assert hasattr(pad, "diameter_mm")


class TestOdbBoardLoaderErrorHandling:
    """Fehlerpfad-Tests für den OdbBoardLoader."""

    loader = OdbBoardLoader()

    def test_nonexistent_path_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(OdbFileNotFoundError):
            self.loader.load_from_odb(tmp_path / "does_not_exist")

    def test_file_instead_of_directory_raises_format_error(self, tmp_path: Path) -> None:
        archive = tmp_path / "COIL.zip"
        archive.write_text("fake archive")
        with pytest.raises(OdbFormatError):
            self.loader.load_from_odb(archive)

    def test_directory_without_matrix_raises_file_not_found(self, tmp_path: Path) -> None:
        """ODB-Verzeichnis ohne matrix/matrix → OdbFileNotFoundError."""
        odb_dir = tmp_path / "odb"
        odb_dir.mkdir()
        # Kein matrix/-Unterverzeichnis angelegt
        with pytest.raises(OdbFileNotFoundError):
            self.loader.load_from_odb(odb_dir)
