"""
Unit-Tests: Domain-Modelle – Board, Layer, Features.
"""

from __future__ import annotations

import pytest

from pcb_rogowski.domain.board.models import (
    Board,
    Layer,
    LayerType,
    LineFeature,
    PadFeature,
    Point2D,
)


class TestPoint2D:
    def test_creation(self) -> None:
        p = Point2D(1.5, 2.5)
        assert p.x_mm == 1.5
        assert p.y_mm == 2.5

    def test_immutable(self) -> None:
        p = Point2D(0.0, 0.0)
        with pytest.raises(AttributeError):
            p.x_mm = 1.0  # type: ignore[misc]


class TestLayer:
    def test_copper_feature_count_empty(self) -> None:
        layer = Layer(name="top", layer_type=LayerType.COPPER, index=0)
        assert layer.copper_feature_count == 0

    def test_copper_feature_count_with_lines(self, minimal_board: Board) -> None:
        top = minimal_board.get_layer("top")
        assert top is not None
        assert top.copper_feature_count == 2


class TestBoard:
    def test_get_layer_found(self, minimal_board: Board) -> None:
        layer = minimal_board.get_layer("top")
        assert layer is not None
        assert layer.name == "top"

    def test_get_layer_not_found(self, minimal_board: Board) -> None:
        layer = minimal_board.get_layer("nonexistent")
        assert layer is None

    def test_copper_layers_sorted(self, minimal_board: Board) -> None:
        copper = minimal_board.copper_layers
        assert len(copper) == 2
        assert copper[0].index < copper[1].index

    def test_copper_layers_only_copper(self) -> None:
        board = Board(name="test")
        board.layers = [
            Layer("top", LayerType.COPPER, 0),
            Layer("silkscreen", LayerType.SILKSCREEN, 99),
            Layer("bottom", LayerType.COPPER, 1),
        ]
        copper = board.copper_layers
        assert all(la.layer_type == LayerType.COPPER for la in copper)
        assert len(copper) == 2
