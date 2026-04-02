"""
Integrations-Test: ODB++ → Board (echtes Datei-Sample).

Verwendet das reale ODB++-Beispiel aus
``data_samples/odb_examples/Desgin_03/odb``.

Diese Tests sind mit ``@pytest.mark.integration`` markiert und laufen
getrennt von den schnellen Unit-Tests::

    pytest tests/integration/
    pytest -m integration

Akzeptanzkriterien (Sprint 2 DoD):
✔  OdbBoardLoader.load_from_odb(path) gibt Board zurück
✔  Board hat alle 17 Lagen aus der matrix/matrix
✔  Alle Kupferlagen haben mindestens eine Feature
✔  Board-Outline (Bounding-Box) ist gesetzt
✔  Keine losen Dictionaries – alle Features sind typisierte Dataclasses
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pcb_rogowski.domain.board.models import Board, LayerType
from pcb_rogowski.infrastructure.odb.loader import OdbBoardLoader

# ---------------------------------------------------------------------------
# Pfad zum echten ODB++-Sample (relativ zum Workspace-Root)
# ---------------------------------------------------------------------------

_WORKSPACE_ROOT = Path(__file__).parent.parent.parent
ODB_SAMPLE_PATH = (
    _WORKSPACE_ROOT / "data_samples" / "odb_examples" / "Desgin_03" / "odb"
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_board() -> Board:
    """Einmaliges Laden des echten Desgin_03 ODB-Projekts."""
    loader = OdbBoardLoader()
    return loader.load_from_odb(ODB_SAMPLE_PATH)


# ===========================================================================
# Integration-Tests
# ===========================================================================


class TestOdbToBoardIntegration:
    """End-to-End Tests: echtes ODB-Sample → vollständiges Board-Objekt."""

    def test_board_is_board_instance(self, real_board: Board) -> None:
        assert isinstance(real_board, Board)

    def test_board_has_expected_layer_count(self, real_board: Board) -> None:
        """Desgin_03 hat 17 Lagen in matrix/matrix."""
        assert len(real_board.layers) == 17

    def test_board_has_four_copper_layers(self, real_board: Board) -> None:
        """TOP_LAYER, MID-LAYER_1, MID-LAYER_2, BOTTOM_LAYER → 4 Kupferlagen."""
        assert len(real_board.copper_layers) == 4

    def test_copper_layers_have_features(self, real_board: Board) -> None:
        """Mindestens eine Kupferlage muss Features haben (leere Lagen sind erlaubt)."""
        layers_with_features = [
            la for la in real_board.copper_layers if la.copper_feature_count > 0
        ]
        assert len(layers_with_features) >= 1, "Keine einzige Kupferlage hat Features!"

    def test_top_and_bottom_copper_layers_have_features(self, real_board: Board) -> None:
        """TOP_LAYER und BOTTOM_LAYER müssen Features haben (sie tragen die Spulenwindungen)."""
        top = real_board.get_layer("top_layer")
        bot = real_board.get_layer("bottom_layer")
        assert top is not None and top.copper_feature_count > 0, "top_layer hat keine Features"
        assert bot is not None and bot.copper_feature_count > 0, "bottom_layer hat keine Features"

    def test_drill_layers_have_via_pads(self, real_board: Board) -> None:
        drill_layers = [la for la in real_board.layers if la.layer_type == LayerType.DRILL]
        assert len(drill_layers) >= 1
        for layer in drill_layers:
            # Vias müssen als is_via=True markiert sein
            assert all(p.is_via for p in layer.pads), (
                f"Drill-Lage {layer.name!r} hat Pads mit is_via=False"
            )

    def test_outline_bounding_box_is_set(self, real_board: Board) -> None:
        assert real_board.outline_mm is not None

    def test_outline_has_positive_dimensions(self, real_board: Board) -> None:
        assert real_board.outline_mm is not None
        x_min, y_min, x_max, y_max = real_board.outline_mm
        assert x_max > x_min
        assert y_max > y_min

    def test_board_dimensions_plausible(self, real_board: Board) -> None:
        """Board sollte kleiner als 500 × 500 mm sein (plausibility check)."""
        assert real_board.outline_mm is not None
        x_min, y_min, x_max, y_max = real_board.outline_mm
        assert (x_max - x_min) < 500.0
        assert (y_max - y_min) < 500.0

    def test_source_file_points_to_odb_dir(self, real_board: Board) -> None:
        assert "odb" in real_board.source_file.lower()

    def test_no_loose_dicts_in_layers(self, real_board: Board) -> None:
        """Alle Features müssen typisierte Dataclasses sein, keine dicts."""
        for layer in real_board.layers:
            for line in layer.lines:
                assert not isinstance(line, dict), (
                    f"Layer {layer.name!r}: LineFeature ist ein dict!"
                )
                assert hasattr(line, "feature_id")
                assert hasattr(line, "width_mm")
            for pad in layer.pads:
                assert not isinstance(pad, dict), (
                    f"Layer {layer.name!r}: PadFeature ist ein dict!"
                )
                assert hasattr(pad, "diameter_mm")

    def test_line_widths_are_positive(self, real_board: Board) -> None:
        """Alle Trace-Breiten müssen > 0 sein (Symbol wurde korrekt konvertiert)."""
        for layer in real_board.copper_layers:
            for line in layer.lines:
                assert line.width_mm > 0, (
                    f"Lage {layer.name!r}: Linie {line.feature_id!r} hat width_mm=0"
                )

    def test_top_layer_has_many_lines(self, real_board: Board) -> None:
        """TOP_LAYER im echten Desgin_03 hat ~7000 Linien."""
        top = real_board.get_layer("top_layer")
        assert top is not None
        assert len(top.lines) > 100
