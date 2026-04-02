"""
Infrastructure: Gerber-Loader.

Lädt ein Gerber-Verzeichnis (Altium-Export) und wandelt es in ein typisiertes
:class:`~pcb_rogowski.domain.board.models.Board`-Domainobjekt um.

Unterstützte Dateistruktur-Konventionen
---------------------------------------

**Altium – beschreibende Dateinamen** (älterer Export)::

    <gerber_dir>/
        <name>_Copper_Signal_Top.gbr     ← Oberste Kupferlage
        <name>_Copper_Signal_1.gbr       ← Inner Layer 1
        <name>_Copper_Signal_Bot.gbr     ← Unterste Kupferlage
        <name>_PTH_Drill.gbr             ← Gebohrte Vias (plattiert)
        <name>_NPTH_Drill.gbr            ← Mechanische Bohrungen
        <name>_Profile.gbr               ← Board-Außenkontur
        <name>_Soldermask_Top.gbr / _Soldermask_Bot.gbr
        <name>_Legend_Top.gbr            ← Silkscreen
        <name>_Mechanical_N.gbr

**Altium – Standard-RS-274X-Endungen** (neuerer Export)::

    <gerber_dir>/
        <name>.GTL   ← Top Copper
        <name>.G1    ← Inner Layer 1  (.G2, .G3, …)
        <name>.GBL   ← Bottom Copper
        <name>.GTS / .GBS   ← Solder Mask Top/Bot
        <name>.GTO / .GBO   ← Silk Screen Top/Bot
        <name>.GTP / .GBP   ← Paste Top/Bot
        <name>.GM  / .GM1 … ← Mechanical layers (.GM = Board-Outline)
        <name>.GBR1 / .GBR2 ← Drill (plated / non-plated)
        <name>.DRL            ← Excellon drill

Hinweis
-------
Altium exportiert Kupferflächen als ``Region``-Objekte und Leiterbahnen als
``Line``-Objekte. Beide werden als :class:`LineFeature` gespeichert.
Bohrungen (PTH/NPTH) werden als :class:`PadFeature` mit ``is_via=True``
gespeichert.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from gerbonara import GerberFile

from pcb_rogowski.domain.board.models import Board, Layer, LayerType
from pcb_rogowski.infrastructure.gerber.parser import parse_lines, parse_pads

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dateiname → Lagen-Metadaten Mapping
# ---------------------------------------------------------------------------

@dataclass
class _LayerMeta:
    """Metadaten einer erkannten Gerber-Lage."""
    name: str
    layer_type: LayerType
    stackup_index: int  # 0 = Top, höhere Zahlen = weiter unten


def _classify_file(path: Path) -> _LayerMeta | None:
    """
    Erkennt den Lagentyp einer Gerber-Datei.

    Unterstützt zwei Konventionen (Priorität: Name → Endung):

    1. **Beschreibende Dateinamen** – Altium-Export mit sprechenden Namen wie
       ``<prefix>_Copper_Signal_Top.gbr``.
    2. **Standard-RS-274X-Endungen** – Altium-Export mit kurzen Endungen wie
       ``.GTL`` (Top Copper), ``.GBL`` (Bottom Copper), ``.G1`` (Inner 1), …

    Gibt ``None`` zurück wenn die Datei übersprungen werden soll.
    """
    stem = path.stem.lower()
    ext  = path.suffix.lower()

    # ------------------------------------------------------------------
    # 1) Name-basierte Klassifikation (beschreibende Altium-Namen)
    # ------------------------------------------------------------------

    # Kupferlagen – Reihenfolge wichtig für stackup_index
    if re.search(r"copper.signal.top|signal.top", stem):
        return _LayerMeta("top_layer", LayerType.COPPER, 0)
    if m := re.search(r"copper.signal.(\d+)", stem):
        idx = int(m.group(1))
        return _LayerMeta(f"mid-layer_{idx}", LayerType.COPPER, idx)
    if re.search(r"copper.signal.bot|signal.bot", stem):
        return _LayerMeta("bottom_layer", LayerType.COPPER, 99)  # normalisiert später

    # Bohrungen – NPTH VOR PTH prüfen (da "npth" auch "pth" enthält)
    if re.search(r"npth.drill", stem):
        return _LayerMeta("drill_non-plated_bottom_layer-top_layer", LayerType.DRILL, 51)
    if re.search(r"pth.drill", stem):
        return _LayerMeta("drill_plated_bottom_layer-top_layer", LayerType.DRILL, 50)

    # Kontur
    if re.search(r"profile|outline|board", stem):
        return _LayerMeta("profile", LayerType.OUTLINE, 90)

    # Lötstopplack
    if re.search(r"soldermask.top|solder.top", stem):
        return _LayerMeta("top_solder", LayerType.SOLDERMASK, 60)
    if re.search(r"soldermask.bot|solder.bot", stem):
        return _LayerMeta("bottom_solder", LayerType.SOLDERMASK, 61)

    # Silkscreen / Bestückungsdruck
    if re.search(r"legend.top|overlay.top|silk.top", stem):
        return _LayerMeta("top_overlay", LayerType.SILKSCREEN, 70)
    if re.search(r"legend.bot|overlay.bot|silk.bot", stem):
        return _LayerMeta("bottom_overlay", LayerType.SILKSCREEN, 71)

    # Mechanische Lagen
    if re.search(r"mechanical", stem):
        idx_m = re.search(r"mechanical.(\d+)", stem)
        idx = int(idx_m.group(1)) if idx_m else 0
        return _LayerMeta(f"mechanical_{idx}", LayerType.OTHER, 80 + idx)

    # ------------------------------------------------------------------
    # 2) Endungs-basierte Klassifikation (Altium RS-274X Standardendungen)
    # ------------------------------------------------------------------

    # Kupferlagen
    if ext == ".gtl":
        return _LayerMeta("top_layer", LayerType.COPPER, 0)
    if ext == ".gbl":
        return _LayerMeta("bottom_layer", LayerType.COPPER, 99)
    if m2 := re.fullmatch(r"\.g(\d+)", ext):
        idx = int(m2.group(1))
        return _LayerMeta(f"mid-layer_{idx}", LayerType.COPPER, idx)

    # Lötstopplack
    if ext == ".gts":
        return _LayerMeta("top_solder", LayerType.SOLDERMASK, 60)
    if ext == ".gbs":
        return _LayerMeta("bottom_solder", LayerType.SOLDERMASK, 61)

    # Silkscreen
    if ext == ".gto":
        return _LayerMeta("top_overlay", LayerType.SILKSCREEN, 70)
    if ext == ".gbo":
        return _LayerMeta("bottom_overlay", LayerType.SILKSCREEN, 71)

    # Lötpaste
    if ext == ".gtp":
        return _LayerMeta("top_paste", LayerType.OTHER, 62)
    if ext == ".gbp":
        return _LayerMeta("bottom_paste", LayerType.OTHER, 63)

    # Mechanische Lagen  (.GM → Board-Outline; .GM1, .GM2, … → Mechanical N)
    if ext == ".gm":
        return _LayerMeta("profile", LayerType.OUTLINE, 90)
    if m2 := re.fullmatch(r"\.gm(\d+)", ext):
        idx = int(m2.group(1))
        return _LayerMeta(f"mechanical_{idx}", LayerType.OTHER, 80 + (idx % 20))

    # Bohrlagen (.GBR1 = PTH, .GBR2 = NPTH; .DRL / .XLN bereits abgedeckt)
    if ext == ".gbr1":
        return _LayerMeta("drill_plated_bottom_layer-top_layer", LayerType.DRILL, 50)
    if ext == ".gbr2":
        return _LayerMeta("drill_non-plated_bottom_layer-top_layer", LayerType.DRILL, 51)

    # Drill-Zeichnungen und Bohrführungen – überspringen
    if re.fullmatch(r"\.g[dg]\d*", ext):
        return None

    # Sonstige Gerber-Dateien ignorieren
    return None


def _normalize_stackup(layers: list[Layer]) -> None:
    """Setzt bottom_layer Stackup-Index auf max(copper)+1."""
    copper_idx = [la.index for la in layers if la.layer_type == LayerType.COPPER and la.index < 99]
    if copper_idx:
        bottom_idx = max(copper_idx) + 1
        for la in layers:
            if la.name == "bottom_layer":
                la.index = bottom_idx


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class GerberBoardLoader:
    """
    Lädt ein Altium-Gerber-Verzeichnis und gibt ein :class:`Board` zurück.

    Typische Verwendung::

        loader = GerberBoardLoader()
        board = loader.load_from_gerber(Path("data_samples/gerber/Desgin_03"))
    """

    # Datei-Endungen, die als Gerber-/Drill-Dateien akzeptiert werden.
    # Neben klassischen .gbr-Endungen auch Altium RS-274X Standardendungen:
    #   .GTL/.GBL (Top/Bot Copper), .G1-.G9 (Inner Layers),
    #   .GTS/.GBS (Solder Mask), .GTO/.GBO (Silk), .GTP/.GBP (Paste),
    #   .GM/.GM1-… (Mechanical), .GBR1/.GBR2 (Drill), .GD1/.GG1 (ignored)
    _GERBER_SUFFIXES: frozenset[str] = frozenset()  # Dummy – siehe _is_gerber_file()

    @staticmethod
    def _is_gerber_file(path: Path) -> bool:
        """Akzeptiert alle gängigen Gerber- und Drill-Dateiendungen."""
        s = path.suffix.lower()
        # Klassische Endungen
        if s in (".gbr", ".ger", ".drl", ".xln"):
            return True
        # Altium-Standardendungen: alles was mit .G gefolgt von Buchstaben/Ziffern beginnt
        if re.fullmatch(r"\.g[a-z0-9]+", s):
            return True
        return False

    def load_from_gerber(self, path: Path) -> Board:
        """
        Parst ein Gerber-Verzeichnis und gibt ein Board zurück.

        Args:
            path: Pfad zum Gerber-Verzeichnis (enthält *.gbr / *.drl Dateien).

        Returns:
            Vollständig befülltes :class:`~pcb_rogowski.domain.board.models.Board`.

        Raises:
            FileNotFoundError: Verzeichnis nicht gefunden.
            ValueError: Keine Gerber-Dateien im Verzeichnis gefunden.
        """
        if not path.is_dir():
            raise FileNotFoundError(f"Gerber-Verzeichnis nicht gefunden: {path}")

        gerber_files = sorted(
            f for f in path.iterdir()
            if self._is_gerber_file(f)
        )
        if not gerber_files:
            raise ValueError(f"Keine Gerber-Dateien in {path} gefunden.")

        logger.info("GerberBoardLoader: %d Dateien gefunden in %s", len(gerber_files), path)

        board_name = path.name
        layers: list[Layer] = []
        outline_mm: tuple[float, float, float, float] | None = None

        for gbr_path in gerber_files:
            meta = _classify_file(gbr_path)
            if meta is None:
                logger.debug("Überspringe: %s", gbr_path.name)
                continue

            logger.info("  → %s  (%s / %s)", gbr_path.name, meta.name, meta.layer_type.value)

            try:
                gfile = GerberFile.open(str(gbr_path))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fehler beim Öffnen von %s: %s", gbr_path.name, exc)
                continue

            # Board-Kontur aus Profile-Datei
            if meta.layer_type == LayerType.OUTLINE:
                try:
                    bb = gfile.bounding_box()
                    if bb:
                        (x0, y0), (x1, y1) = bb
                        outline_mm = (float(x0), float(y0), float(x1), float(y1))
                        logger.info("    Board-Outline: %.2f×%.2f mm", x1 - x0, y1 - y0)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Outline-Extraktion fehlgeschlagen: %s", exc)
                # Outline-Lage trotzdem als Layer hinzufügen
                lines = parse_lines(gfile, meta.name)
                layer = Layer(
                    name=meta.name,
                    layer_type=meta.layer_type,
                    index=meta.stackup_index,
                    lines=lines,
                )
                layers.append(layer)
                continue

            # Bohrlagen → nur Pads
            if meta.layer_type == LayerType.DRILL:
                pads = parse_pads(gfile, meta.name, is_via=True)
                layer = Layer(
                    name=meta.name,
                    layer_type=meta.layer_type,
                    index=meta.stackup_index,
                    pads=pads,
                )
                layers.append(layer)
                continue

            # Alle anderen Lagen → Lines + Pads
            lines = parse_lines(gfile, meta.name)
            pads = parse_pads(gfile, meta.name)
            layer = Layer(
                name=meta.name,
                layer_type=meta.layer_type,
                index=meta.stackup_index,
                lines=lines,
                pads=pads,
            )
            layers.append(layer)

        if not layers:
            raise ValueError(f"Keine auswertbaren Lagen in {path} gefunden.")

        # Stackup normalisieren (bottom_layer bekommt richtigen Index)
        _normalize_stackup(layers)

        # Lagen nach Stackup-Index sortieren
        layers.sort(key=lambda la: la.index)

        board = Board(
            name=board_name,
            layers=layers,
            outline_mm=outline_mm,
            source_file=str(path),
        )

        logger.info(
            "Board '%s' geladen: %d Lagen, %d Linien, %d Pads",
            board.name,
            len(board.layers),
            sum(len(la.lines) for la in board.layers),
            sum(len(la.pads) for la in board.layers),
        )
        return board
