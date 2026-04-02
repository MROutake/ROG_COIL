"""
Unit-Tests für pcb_rogowski.domain.trace.classifier.

Abgedeckte Klassen / Methoden
------------------------------
ClassificationEntry   – Validierung (role, sigma)
ClassifierConfig      – Defaults, from_yaml
ClassificationSpec    – role_counts, YAML-Roundtrip, entry_by_id
TopologyGapFiller     – Kette 3 Segmente, isoliertes Segment, leere Spec
FishboneClassifier    – Klassifikation auf einem Minimal-Board
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from pcb_rogowski.domain.board.models import Board, Layer, LayerType, LineFeature, Point2D
from pcb_rogowski.domain.trace.classifier import (
    ClassificationEntry,
    ClassificationSpec,
    ClassifierConfig,
    FishboneClassifier,
    TopologyGapFiller,
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen / Fixtures
# ---------------------------------------------------------------------------

def _pt(x: float, y: float) -> Point2D:
    return Point2D(x_mm=x, y_mm=y)


def _line(fid: str, x1: float, y1: float, x2: float, y2: float,
          layer: str = "top_layer", width: float = 0.1) -> LineFeature:
    return LineFeature(
        feature_id=fid,
        start=_pt(x1, y1),
        end=_pt(x2, y2),
        width_mm=width,
        layer_name=layer,
    )


def _entry(fid: str, role: str, sigma: int = 0, layer: str = "top_layer") -> ClassificationEntry:
    return ClassificationEntry(
        feature_id=fid,
        layer_name=layer,
        role=role,
        sigma=sigma,
    )


@pytest.fixture()
def minimal_board() -> Board:
    """
    Minimal-Board mit zwei Kupferlagen und je 3 verbundenen Segmenten.

    Layout (top_layer, horizontal Kette):
        A(0,0)──B(2,0)──C(4,0)──D(6,0)
        Segmente: seg1 [A→B], seg2 [B→C], seg3 [C→D]

    bottom_layer:
        E(0,1)──F(2,1)   (nur ein Segment, kein Anschluss an top)
    """
    top = Layer(name="top_layer", layer_type=LayerType.COPPER, index=0)
    top.lines = [
        _line("seg1", 0, 0, 2, 0, layer="top_layer"),
        _line("seg2", 2, 0, 4, 0, layer="top_layer"),
        _line("seg3", 4, 0, 6, 0, layer="top_layer"),
    ]
    bot = Layer(name="bottom_layer", layer_type=LayerType.COPPER, index=3)
    bot.lines = [
        _line("ret1", 0, 1, 2, 1, layer="bottom_layer"),
    ]
    return Board(name="TestBoard", layers=[top, bot])


# ---------------------------------------------------------------------------
# ClassificationEntry – Validierung
# ---------------------------------------------------------------------------

class TestClassificationEntry:
    def test_valid_roles(self) -> None:
        for role in ("winding", "connection", "return"):
            e = ClassificationEntry(feature_id="x", layer_name="l", role=role)
            assert e.role == role

    def test_invalid_role_raises(self) -> None:
        with pytest.raises(ValueError, match="role"):
            ClassificationEntry(feature_id="x", layer_name="l", role="unknown")

    def test_valid_sigma_values(self) -> None:
        for sigma in (-1, 0, 1):
            e = ClassificationEntry(feature_id="x", layer_name="l",
                                    role="winding", sigma=sigma)
            assert e.sigma == sigma

    def test_invalid_sigma_raises(self) -> None:
        with pytest.raises(ValueError, match="sigma"):
            ClassificationEntry(feature_id="x", layer_name="l",
                                role="winding", sigma=2)

    def test_defaults(self) -> None:
        e = ClassificationEntry(feature_id="f1", layer_name="top", role="connection")
        assert e.sigma == 0
        assert e.window_id is None
        assert e.note is None


# ---------------------------------------------------------------------------
# ClassifierConfig
# ---------------------------------------------------------------------------

class TestClassifierConfig:
    def test_defaults(self) -> None:
        cfg = ClassifierConfig()
        assert cfg.angle_tolerance_deg == 10.0
        assert cfg.min_parallel_segments == 3
        assert cfg.short_segment_threshold_mm == 1.0  # nach defaults.yaml-Update
        assert cfg.winding_layer_name == "top_layer"
        assert cfg.return_layer_name == "bottom_layer"

    def test_from_yaml(self, tmp_path: Path) -> None:
        yaml_text = """\
classifier:
  angle_tolerance_deg: 15.0
  min_parallel_segments: 5
  short_segment_threshold_mm: 2.5
  winding_layer_name: "signal_top"
  return_layer_name: "signal_bot"
"""
        p = tmp_path / "cfg.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        cfg = ClassifierConfig.from_yaml(p)
        assert cfg.angle_tolerance_deg == 15.0
        assert cfg.min_parallel_segments == 5
        assert cfg.short_segment_threshold_mm == 2.5
        assert cfg.winding_layer_name == "signal_top"
        assert cfg.return_layer_name == "signal_bot"

    def test_from_yaml_missing_section_uses_defaults(self, tmp_path: Path) -> None:
        """Eine YAML ohne 'classifier'-Schlüssel liefert Standardwerte."""
        p = tmp_path / "empty.yaml"
        p.write_text("application:\n  name: test\n", encoding="utf-8")
        cfg = ClassifierConfig.from_yaml(p)
        assert cfg.winding_layer_name == "top_layer"


# ---------------------------------------------------------------------------
# ClassificationSpec – role_counts / YAML-Roundtrip
# ---------------------------------------------------------------------------

class TestClassificationSpec:
    def _make_spec(self) -> ClassificationSpec:
        return ClassificationSpec(
            board_name="Board42",
            source_gerber="/path/to/gerber",
            entries=[
                _entry("f1", "winding",    sigma=1),
                _entry("f2", "winding",    sigma=-1),
                _entry("f3", "connection", sigma=0),
                _entry("f4", "return",     sigma=-1),
            ],
            auto_detected=True,
            notes="Testspec",
        )

    def test_role_counts(self) -> None:
        spec = self._make_spec()
        counts = spec.role_counts()
        assert counts["winding"] == 2
        assert counts["connection"] == 1
        assert counts["return"] == 1

    def test_entry_by_id(self) -> None:
        spec = self._make_spec()
        d = spec.entry_by_id()
        assert set(d.keys()) == {"f1", "f2", "f3", "f4"}
        assert d["f1"].role == "winding"

    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        spec = self._make_spec()
        p = tmp_path / "spec.yaml"
        spec.to_yaml(p)
        assert p.exists()
        loaded = ClassificationSpec.from_yaml(p)

        assert loaded.board_name == spec.board_name
        assert loaded.source_gerber == spec.source_gerber
        assert loaded.auto_detected == spec.auto_detected
        assert loaded.notes == spec.notes
        assert len(loaded.entries) == len(spec.entries)

        for orig, loaded_e in zip(spec.entries, loaded.entries):
            assert loaded_e.feature_id == orig.feature_id
            assert loaded_e.role == orig.role
            assert loaded_e.sigma == orig.sigma
            assert loaded_e.layer_name == orig.layer_name

    def test_to_yaml_creates_parent_dirs(self, tmp_path: Path) -> None:
        spec = self._make_spec()
        deep = tmp_path / "a" / "b" / "c" / "spec.yaml"
        spec.to_yaml(deep)
        assert deep.exists()

    def test_from_yaml_empty_entries(self, tmp_path: Path) -> None:
        spec = ClassificationSpec(board_name="Empty", source_gerber="")
        p = tmp_path / "empty.yaml"
        spec.to_yaml(p)
        loaded = ClassificationSpec.from_yaml(p)
        assert loaded.entries == []


# ---------------------------------------------------------------------------
# TopologyGapFiller
# ---------------------------------------------------------------------------

class TestTopologyGapFiller:
    def test_fill_chain_same_role(self, minimal_board: Board) -> None:
        """
        seg1 (winding) ── seg2 (unklassifiziert) ── seg3 (winding)
        → seg2 soll als winding gefüllt werden (beide Nachbarn = winding).
        """
        partial = ClassificationSpec(
            board_name="TestBoard",
            source_gerber="",
            entries=[
                _entry("seg1", "winding", sigma=1),
                _entry("seg3", "winding", sigma=-1),
            ],
        )
        filled = TopologyGapFiller().fill(minimal_board, partial)
        by_id = filled.entry_by_id()

        assert "seg2" in by_id
        assert by_id["seg2"].role == "winding"
        assert by_id["seg2"].note == "auto:gap-fill"

    def test_fill_chain_predecessor_wins(self, minimal_board: Board) -> None:
        """
        seg1 (winding) ── seg2 (unklassifiziert) ── seg3 (connection)
        Nachbarn uneinig → Vorgänger (seg1, winding) bestimmt die Rolle.
        """
        partial = ClassificationSpec(
            board_name="TestBoard",
            source_gerber="",
            entries=[
                _entry("seg1", "winding",    sigma=1),
                _entry("seg3", "connection", sigma=0),
            ],
        )
        filled = TopologyGapFiller().fill(minimal_board, partial)
        by_id = filled.entry_by_id()
        assert by_id["seg2"].role == "winding"

    def test_fill_preserves_existing_entries(self, minimal_board: Board) -> None:
        """Bereits klassifizierte Segmente dürfen nicht überschrieben werden."""
        partial = ClassificationSpec(
            board_name="TestBoard",
            source_gerber="",
            entries=[
                _entry("seg1", "winding",    sigma=1),
                _entry("seg2", "connection", sigma=0, layer="top_layer"),
                _entry("seg3", "winding",    sigma=-1),
            ],
        )
        filled = TopologyGapFiller().fill(minimal_board, partial)
        by_id = filled.entry_by_id()
        assert by_id["seg2"].role == "connection"  # unverändert

    def test_fill_empty_spec_no_crash(self, minimal_board: Board) -> None:
        """Leere Spec → kein Fehler, Ergebnis bleibt leer (keine Anker)."""
        empty = ClassificationSpec(board_name="TestBoard", source_gerber="")
        filled = TopologyGapFiller().fill(minimal_board, empty)
        assert filled.entries == []

    def test_fill_sigma_alternates_for_winding(self, minimal_board: Board) -> None:
        """Sigma soll bei aufeinanderfolgenden Winding-Segmenten alternieren."""
        partial = ClassificationSpec(
            board_name="TestBoard",
            source_gerber="",
            entries=[
                _entry("seg1", "winding", sigma=1),
            ],
        )
        filled = TopologyGapFiller().fill(minimal_board, partial)
        by_id = filled.entry_by_id()
        if "seg2" in by_id and by_id["seg2"].role == "winding":
            assert by_id["seg2"].sigma == -1

    def test_fill_return_layer_segment(self, minimal_board: Board) -> None:
        """
        ret1 ist auf bottom_layer und noch unklassifiziert.
        Nach Gap-Fill gibt es keine Anker auf bottom_layer → bleibt ungefüllt.
        """
        partial = ClassificationSpec(
            board_name="TestBoard",
            source_gerber="",
            entries=[
                _entry("seg1", "winding", sigma=1),
                _entry("seg2", "winding", sigma=-1),
                _entry("seg3", "winding", sigma=1),
            ],
        )
        filled = TopologyGapFiller().fill(minimal_board, partial)
        by_id = filled.entry_by_id()
        # ret1 ist nicht mit top_layer verbunden → kein Gap-Fill möglich
        assert "ret1" not in by_id


# ---------------------------------------------------------------------------
# FishboneClassifier
# ---------------------------------------------------------------------------

class TestFishboneClassifier:
    @pytest.fixture()
    def cfg_low_threshold(self) -> ClassifierConfig:
        return ClassifierConfig(
            short_segment_threshold_mm=1.0,
            winding_layer_name="top_layer",
            return_layer_name="bottom_layer",
        )

    def _make_board(self) -> Board:
        """
        Kleines Test-Board:
          top_layer:
            - long1: 3 mm → winding
            - short1: 0.5 mm → connection
          bottom_layer:
            - ret1: 3 mm → return
        """
        top = Layer(name="top_layer", layer_type=LayerType.COPPER, index=0)
        top.lines = [
            _line("long1",  0,  0, 3, 0, layer="top_layer"),   # 3 mm
            _line("short1", 0,  0, 0.5, 0, layer="top_layer"), # 0.5 mm
        ]
        bot = Layer(name="bottom_layer", layer_type=LayerType.COPPER, index=3)
        bot.lines = [
            _line("ret1", 0, 1, 3, 1, layer="bottom_layer"),   # 3 mm
        ]
        return Board(name="FishTest", layers=[top, bot])

    def test_classify_returns_spec(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        assert isinstance(spec, ClassificationSpec)
        assert spec.board_name == "FishTest"
        assert spec.auto_detected is True

    def test_winding_long_segment(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        by_id = spec.entry_by_id()
        assert by_id["long1"].role == "winding"
        assert by_id["long1"].sigma in (-1, 1)

    def test_connection_short_segment(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        by_id = spec.entry_by_id()
        assert by_id["short1"].role == "connection"
        assert by_id["short1"].sigma == 0

    def test_return_bottom_layer(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        by_id = spec.entry_by_id()
        assert by_id["ret1"].role == "return"
        assert by_id["ret1"].sigma == -1

    def test_all_lines_classified(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        total = sum(len(la.lines) for la in board.copper_layers)
        assert len(spec.entries) == total

    def test_sigma_direction_up(self, cfg_low_threshold: ClassifierConfig) -> None:
        """Segment nach oben (dy > 0) → sigma = +1."""
        top = Layer(name="top_layer", layer_type=LayerType.COPPER, index=0)
        top.lines = [_line("up", 0, 0, 0, 3, layer="top_layer")]  # dy = 3
        board = Board(name="B", layers=[top])
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        assert spec.entry_by_id()["up"].sigma == 1

    def test_sigma_direction_down(self, cfg_low_threshold: ClassifierConfig) -> None:
        """Segment nach unten (dy < 0) → sigma = -1."""
        top = Layer(name="top_layer", layer_type=LayerType.COPPER, index=0)
        top.lines = [_line("down", 0, 3, 0, 0, layer="top_layer")]  # dy = -3
        board = Board(name="B", layers=[top])
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        assert spec.entry_by_id()["down"].sigma == -1

    def test_note_is_auto_fishbone(self, cfg_low_threshold: ClassifierConfig) -> None:
        board = self._make_board()
        spec = FishboneClassifier(cfg_low_threshold).classify(board)
        for e in spec.entries:
            assert e.note == "auto:fishbone"
