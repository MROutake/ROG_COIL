"""
WindowExtractor: Extrahiert Via-Fenster aus der klassifizierten
PCB-Rogowski-Geometrie für die M_prim-Berechnung.

Jedes Via-Fenster ist der rechteckige Bereich zwischen zwei benachbarten
WINDING-Segmenten (Fishbone-Zähnen), durch den der Primärleiter (Busbar)
hindurchtritt.  Das Fenster wird durch die Via-Paare der angrenzenden
Windungen begrenzt.

Strategie:
    1. Alle WINDING-Segmente auf der Hauptlage (top_layer) sammeln.
    2. Nach Position (entlang der Spulenachse) sortieren.
    3. Für jedes benachbarte Paar (Zahn i, Zahn i+1) ein Fenster ableiten:
       - h_m = effektive Fensterhöhe ≈ Länge der Windungszähne (= axiale
         Richtung der Rogowski-Spule)
       - b_m = Fensterbreite ≈ Abstand (Pitch) zwischen den Zähnen minus
         Spurenbreite
       - sigma aus der Klassifikation
    4. Ergebnis: Liste von ViaWindow-Objekten mit Bounding-Box und σ.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from pcb_rogowski.domain.board.models import Board, LineFeature, LayerType
from pcb_rogowski.domain.trace.models import TraceLayout, TraceRole, ViaWindow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ergebnis-Container (Zusatzinfos über das Eingangsmaterial)
# ---------------------------------------------------------------------------

@dataclass
class WindowExtractionResult:
    """Ergebnis der Fenster-Extraktion."""

    windows: list[ViaWindow]
    n_winding_segments: int
    dominant_axis: str           # "x" oder "y" – entlang welcher Achse die Zähne aufgereiht sind
    mean_tooth_length_mm: float  # mittlere Zahnlänge (= h_m)
    mean_pitch_mm: float         # mittlerer Pitch (= b_m + W)

    def summary(self) -> str:
        return (
            f"WindowExtractionResult:\n"
            f"  {len(self.windows)} Fenster aus {self.n_winding_segments} "
            f"Winding-Segmenten\n"
            f"  Dominante Achse: {self.dominant_axis}\n"
            f"  Mittlere Zahnlänge: {self.mean_tooth_length_mm:.3f} mm\n"
            f"  Mittlerer Pitch:    {self.mean_pitch_mm:.3f} mm\n"
        )


# ---------------------------------------------------------------------------
# Extraktor
# ---------------------------------------------------------------------------

class WindowExtractor:
    """
    Extrahiert ViaWindow-Objekte aus einem klassifizierten Board.

    Args:
        winding_layer_name: Name der Hauptlage für Windungssegmente.
                            Standard: ``"top_layer"``.
    """

    def __init__(self, winding_layer_name: str = "top_layer") -> None:
        self._winding_layer = winding_layer_name

    def extract(
        self,
        layout: TraceLayout,
        board: Board,
    ) -> WindowExtractionResult:
        """
        Extrahiert alle Via-Fenster aus der klassifizierten Geometrie.

        Gibt eine :class:`WindowExtractionResult` mit den ViaWindow-Objekten
        zurück.  Die Fenster werden der ``layout.via_windows``-Liste
        *nicht* automatisch hinzugefügt — der Aufrufer entscheidet.

        Args:
            layout: Klassifiziertes TraceLayout (mit WINDING-Segmenten).
            board:  Geladenes Board-Domainobjekt.

        Returns:
            WindowExtractionResult mit allen extrahierten Fenstern.
        """
        # Feature-Lookup aufbauen
        line_by_id: dict[str, LineFeature] = {}
        for la in board.layers:
            if la.layer_type == LayerType.COPPER:
                for f in la.lines:
                    line_by_id[f.feature_id] = f

        # Alle WINDING-Segmente auf der Hauptlage sammeln
        winding_entries = [
            c for c in layout.classifications
            if c.role == TraceRole.WINDING and c.layer_name == self._winding_layer
        ]
        if len(winding_entries) < 2:
            logger.warning(
                "Weniger als 2 WINDING-Segmente auf '%s' — keine Fenster erzeugbar.",
                self._winding_layer,
            )
            return WindowExtractionResult(
                windows=[], n_winding_segments=len(winding_entries),
                dominant_axis="?", mean_tooth_length_mm=0.0, mean_pitch_mm=0.0,
            )

        # Zugehörige LineFeatures sammeln
        teeth: list[tuple[LineFeature, int]] = []  # (feature, sigma)
        for c in winding_entries:
            feat = line_by_id.get(c.feature_id)
            if feat is not None:
                teeth.append((feat, c.sigma))

        if len(teeth) < 2:
            logger.warning("Weniger als 2 gematchte Winding-Features — keine Fenster.")
            return WindowExtractionResult(
                windows=[], n_winding_segments=len(teeth),
                dominant_axis="?", mean_tooth_length_mm=0.0, mean_pitch_mm=0.0,
            )

        # Dominante Achse bestimmen: Zähne sind QUER zur Spulenachse aufgereiht.
        # Ihre Mittelpunkte variieren entlang der Spulenachse.
        dominant_axis = self._detect_dominant_axis(teeth)

        # Zähne entlang der dominanten Achse sortieren
        if dominant_axis == "x":
            teeth.sort(key=lambda t: (t[0].start.x_mm + t[0].end.x_mm) / 2)
        else:
            teeth.sort(key=lambda t: (t[0].start.y_mm + t[0].end.y_mm) / 2)

        # Mittlere Zahnlänge
        tooth_lengths = [
            math.hypot(
                f.end.x_mm - f.start.x_mm,
                f.end.y_mm - f.start.y_mm,
            )
            for f, _ in teeth
        ]
        mean_tooth_len = sum(tooth_lengths) / len(tooth_lengths) if tooth_lengths else 0.0

        # Fenster zwischen benachbarten Zähnen erzeugen
        windows: list[ViaWindow] = []
        pitches: list[float] = []

        for i in range(len(teeth) - 1):
            f_a, sigma_a = teeth[i]
            f_b, sigma_b = teeth[i + 1]

            window, pitch = self._make_window(
                f"W{i + 1:03d}",
                f_a, sigma_a,
                f_b, sigma_b,
                dominant_axis,
            )
            windows.append(window)
            pitches.append(pitch)

        mean_pitch = sum(pitches) / len(pitches) if pitches else 0.0

        logger.info(
            "WindowExtractor: %d Fenster extrahiert aus %d Zähnen "
            "(Achse=%s, h_avg=%.3f mm, p_avg=%.3f mm)",
            len(windows), len(teeth), dominant_axis,
            mean_tooth_len, mean_pitch,
        )

        return WindowExtractionResult(
            windows=windows,
            n_winding_segments=len(teeth),
            dominant_axis=dominant_axis,
            mean_tooth_length_mm=mean_tooth_len,
            mean_pitch_mm=mean_pitch,
        )

    # ------------------------------------------------------------------
    # Interne Hilfsfunktionen
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_dominant_axis(
        teeth: list[tuple[LineFeature, int]],
    ) -> str:
        """
        Bestimmt, ob die Zähne entlang der X- oder Y-Achse aufgereiht sind.

        Nimmt die Varianz der Mittelpunkte: die Achse mit größerer Varianz
        ist die Spulenachse (= Aufreihungsrichtung).
        """
        mx = [(f.start.x_mm + f.end.x_mm) / 2 for f, _ in teeth]
        my = [(f.start.y_mm + f.end.y_mm) / 2 for f, _ in teeth]

        var_x = _variance(mx)
        var_y = _variance(my)

        return "x" if var_x > var_y else "y"

    @staticmethod
    def _make_window(
        window_id: str,
        f_a: LineFeature, sigma_a: int,
        f_b: LineFeature, sigma_b: int,
        axis: str,
    ) -> tuple[ViaWindow, float]:
        """
        Erzeugt ein ViaWindow zwischen zwei benachbarten Zähnen.

        Returns:
            (ViaWindow, pitch_mm) — das Fenster und der Mitte-Mitte-Abstand.
        """
        # Bounding-Box des Fensters:
        # - In Aufreihungsrichtung (axis): vom Ende von Zahn A bis zum
        #   Anfang von Zahn B (Kante-zu-Kante)
        # - Quer dazu: die Überlappung der Zahnausdehnung

        # Mittelpunkte und Grenzen der Zähne
        ax_min_a, ax_max_a, cross_min_a, cross_max_a = _tooth_bounds(f_a, axis)
        ax_min_b, ax_max_b, cross_min_b, cross_max_b = _tooth_bounds(f_b, axis)

        # Fenster in Aufreihungsrichtung: rechte Kante A → linke Kante B
        window_ax_min = ax_max_a
        window_ax_max = ax_min_b

        # Falls die Zähne sich überlappen (sollte nicht vorkommen)
        if window_ax_min > window_ax_max:
            window_ax_min, window_ax_max = window_ax_max, window_ax_min

        # Fenster quer: konservative Überlappung der Zahnausdehnung
        window_cross_min = max(cross_min_a, cross_min_b)
        window_cross_max = min(cross_max_a, cross_max_b)
        if window_cross_min > window_cross_max:
            # Keine Überlappung → nehme die Vereinigung
            window_cross_min = min(cross_min_a, cross_min_b)
            window_cross_max = max(cross_max_a, cross_max_b)

        # Mitte-Mitte-Abstand (Pitch)
        mid_a = (ax_min_a + ax_max_a) / 2
        mid_b = (ax_min_b + ax_max_b) / 2
        pitch = abs(mid_b - mid_a)

        # Sigma: Vorzeichen des ERSTEN Zahns im Paar bestimmt das Fenster-σ
        # (Konvention: der Fluss im Fenster hat das Vorzeichen des links
        # davon liegenden Windungssegments)
        sigma = sigma_a

        if axis == "x":
            window = ViaWindow(
                window_id=window_id,
                x_min_mm=window_ax_min,
                y_min_mm=window_cross_min,
                x_max_mm=window_ax_max,
                y_max_mm=window_cross_max,
                sigma=sigma,
            )
        else:
            window = ViaWindow(
                window_id=window_id,
                x_min_mm=window_cross_min,
                y_min_mm=window_ax_min,
                x_max_mm=window_cross_max,
                y_max_mm=window_ax_max,
                sigma=sigma,
            )

        return window, pitch


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _tooth_bounds(
    f: LineFeature, axis: str,
) -> tuple[float, float, float, float]:
    """
    Gibt die Bounding-Box eines Zahns als (ax_min, ax_max, cross_min, cross_max)
    zurück, wobei 'ax' die Aufreihungsrichtung und 'cross' die Querrichtung ist.
    """
    if axis == "x":
        ax_min = min(f.start.x_mm, f.end.x_mm)
        ax_max = max(f.start.x_mm, f.end.x_mm)
        cross_min = min(f.start.y_mm, f.end.y_mm)
        cross_max = max(f.start.y_mm, f.end.y_mm)
    else:
        ax_min = min(f.start.y_mm, f.end.y_mm)
        ax_max = max(f.start.y_mm, f.end.y_mm)
        cross_min = min(f.start.x_mm, f.end.x_mm)
        cross_max = max(f.start.x_mm, f.end.x_mm)
    return ax_min, ax_max, cross_min, cross_max


def _variance(values: list[float]) -> float:
    """Einfache Varianzberechnung."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)
