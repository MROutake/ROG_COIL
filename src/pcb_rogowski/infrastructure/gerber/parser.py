"""
Gerber / Excellon → Domain-Modell Parser.

Wandelt gerbonara-Objekte in die internen Domain-Modelle um:
    - Line   → LineFeature
    - Flash  → PadFeature  (Pads und Vias)
    - Region → mehrere LineFeature-Segmente (Altium exportiert Kupferflächen
               als geschlossene Regions)

Einheiten: gerbonara liefert alle Koordinaten in mm, wenn die Quelldatei
eine Metric-Gerber-Datei ist (Altium-Standard).
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from gerbonara.graphic_objects import Arc, Flash, Line, Region

from pcb_rogowski.domain.board.models import LineFeature, PadFeature, Point2D

if TYPE_CHECKING:
    from gerbonara import GerberFile

logger = logging.getLogger(__name__)

# Mindestbreite für Linien ohne Apertur (Fallback, in mm)
_FALLBACK_WIDTH_MM: float = 0.05


def _aperture_diameter(aperture) -> float:  # type: ignore[no-untyped-def]
    """Liest den Durchmesser aus einer gerbonara-Aperture (robust)."""
    for attr in ("diameter", "width", "size"):
        val = getattr(aperture, attr, None)
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    return _FALLBACK_WIDTH_MM


def _stable_id(prefix: str, layer: str, *coords: float) -> str:
    """
    Erzeugt eine deterministische Feature-ID aus Geometrie + Lagenname.

    Gleiche Koordinaten + gleiche Lage → immer dieselbe ID.
    Dadurch bleiben gespeicherte Klassifikations-YAMLs auch nach
    erneutem Laden des Boards gültig.
    """
    raw = f"{prefix}|{layer}|{'|'.join(f'{c:.6f}' for c in coords)}"
    return f"{prefix}_{hashlib.md5(raw.encode()).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Öffentliche Parse-Funktionen
# ---------------------------------------------------------------------------

def parse_lines(gerber_file: "GerberFile", layer_name: str) -> list[LineFeature]:
    """
    Extrahiert alle LineFeature-Objekte aus einer GerberFile.

    Berücksichtigt:
    - Standalone ``Line`` Objekte (klassische Leiterbahnen)
    - Segments aus ``Region.outline_objects()`` (Altium-Kupferflächen)
    - ``Arc`` Objekte werden als Sehnen-Linie angenähert
    """
    features: list[LineFeature] = []

    for obj in gerber_file.objects:
        if isinstance(obj, Line):
            w = _aperture_diameter(obj.aperture) if obj.aperture else _FALLBACK_WIDTH_MM
            x1, y1, x2, y2 = float(obj.x1), float(obj.y1), float(obj.x2), float(obj.y2)
            features.append(
                LineFeature(
                    feature_id=_stable_id("ln", layer_name, x1, y1, x2, y2, w),
                    start=Point2D(x_mm=x1, y_mm=y1),
                    end=Point2D(x_mm=x2, y_mm=y2),
                    width_mm=w,
                    layer_name=layer_name,
                )
            )

        elif isinstance(obj, Arc):
            # Arc: Mittelpunkt-Sehne als Annäherung (genug für Visualisierung)
            x1, y1, x2, y2 = float(obj.x1), float(obj.y1), float(obj.x2), float(obj.y2)
            features.append(
                LineFeature(
                    feature_id=_stable_id("arc", layer_name, x1, y1, x2, y2),
                    start=Point2D(x_mm=x1, y_mm=y1),
                    end=Point2D(x_mm=x2, y_mm=y2),
                    width_mm=_FALLBACK_WIDTH_MM,
                    layer_name=layer_name,
                )
            )

        elif isinstance(obj, Region):
            # Region: Umriss-Segmente extrahieren
            try:
                for seg in obj.outline_objects():
                    if isinstance(seg, Line):
                        sx1, sy1, sx2, sy2 = float(seg.x1), float(seg.y1), float(seg.x2), float(seg.y2)
                        features.append(
                            LineFeature(
                                feature_id=_stable_id("reg", layer_name, sx1, sy1, sx2, sy2),
                                start=Point2D(x_mm=sx1, y_mm=sy1),
                                end=Point2D(x_mm=sx2, y_mm=sy2),
                                width_mm=_FALLBACK_WIDTH_MM,
                                layer_name=layer_name,
                            )
                        )
                    elif isinstance(seg, Arc):
                        sx1, sy1, sx2, sy2 = float(seg.x1), float(seg.y1), float(seg.x2), float(seg.y2)
                        features.append(
                            LineFeature(
                                feature_id=_stable_id("rarc", layer_name, sx1, sy1, sx2, sy2),
                                start=Point2D(x_mm=sx1, y_mm=sy1),
                                end=Point2D(x_mm=sx2, y_mm=sy2),
                                width_mm=_FALLBACK_WIDTH_MM,
                                layer_name=layer_name,
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Region outline_objects() fehlgeschlagen: %s", exc)

    logger.debug("parse_lines(%s): %d LineFeatures", layer_name, len(features))
    return features


def parse_pads(gerber_file: "GerberFile", layer_name: str, *, is_via: bool = False) -> list[PadFeature]:
    """
    Extrahiert alle PadFeature-Objekte (Flashes / Bohrungen) aus einer GerberFile.
    """
    features: list[PadFeature] = []

    for obj in gerber_file.objects:
        if isinstance(obj, Flash):
            d = _aperture_diameter(obj.aperture) if obj.aperture else _FALLBACK_WIDTH_MM
            cx, cy = float(obj.x), float(obj.y)
            features.append(
                PadFeature(
                    feature_id=_stable_id("pad", layer_name, cx, cy, d),
                    center=Point2D(x_mm=cx, y_mm=cy),
                    diameter_mm=d,
                    is_via=is_via,
                    layer_name=layer_name,
                )
            )

    logger.debug("parse_pads(%s): %d PadFeatures", layer_name, len(features))
    return features
