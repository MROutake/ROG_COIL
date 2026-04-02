"""
GeometryParameters: Physikalische Eingangsgrößen für alle Spulenberechnungen.
GeometryExtractor:  Extrahiert diese Größen aus TraceLayout + Board + optionalem Stackup.

Alle Längengrößen sind in mm gespeichert; die Berechnungsmodule konvertieren
intern nach SI-Einheiten (m).

Stackup-Priorität für H, T, εr:
    1. Übergebenes Stackup-Objekt  (aus stackup_design03.yaml)
    2. Design-03-Fallback           (eingebettete Konstanten aus Stack Report)
    3. geometry_baseline.yaml       (nur wenn config_path angegeben)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from pcb_rogowski.domain.board.models import Board, LayerType
from pcb_rogowski.domain.stackup.models import DielectricSpec, Stackup
from pcb_rogowski.domain.trace.models import TraceLayout, TraceRole

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Design-03 Fallback-Konstanten (aus Altium Stack Report)
# ---------------------------------------------------------------------------
_D03_T_MM: float = 0.03556    # Kupferdicke 1 oz [mm]
_D03_H_MM: float = 0.32004    # Dielektrikum 1 (Top → Mid1) [mm]
_D03_EPS_R: float = 4.8       # FR-4 εr
_D03_TOTAL_MM: float = 1.12268  # Gesamtdicke [mm]


# ---------------------------------------------------------------------------
# Daten-Klasse
# ---------------------------------------------------------------------------

@dataclass
class GeometryParameters:
    """
    Alle physikalischen Eingangsgrößen für die Spulenberechnung.

    Attributes:
        W_mm:         Mittlere Breite der Windungsleiter [mm]
        H_mm:         Abstand Windungsleiter → nächste Massefläche [mm]
        T_mm:         Kupferdicke der Windungslage [mm]
        l_track_mm:   Gesamtlänge der Windungsleiter (WINDING-Segmente) [mm]
        h_via_mm:     Höhe eines einzelnen Vias (= PCB-Gesamtdicke) [mm]
        d_via_mm:     Mittlerer Via-Bohrdurchmesser [mm]
        n_vias:       Anzahl der Vias in der Spule
        l_trace_mm:   Gesamtlänge der Anschlussleitungen (CONNECTION) [mm]
        w_trace_mm:   Mittlere Breite der Anschlussleitungen [mm]
        epsilon_r:    Relative Permittivität des Dielektrikums
        N_turns:      Anzahl Windungen (≈ Anzahl WINDING-Segmente auf Hauptlage)
        p_mm:         Mittlerer Pitch (Mitte-Mitte-Abstand) benachbarter Windungen [mm]
        winding_layer: Lagenname des Windungsleiters (Info)
    """

    W_mm: float
    H_mm: float
    T_mm: float
    l_track_mm: float
    h_via_mm: float
    d_via_mm: float
    n_vias: int
    l_trace_mm: float
    w_trace_mm: float
    epsilon_r: float
    N_turns: int
    p_mm: float = 2.0
    winding_layer: str = "top_layer"

    def summary(self) -> str:
        """Gibt eine kompakte Übersicht der Geometrieparameter zurück."""
        return (
            f"GeometryParameters:\n"
            f"  W        = {self.W_mm:.4f} mm\n"
            f"  H        = {self.H_mm:.4f} mm\n"
            f"  T        = {self.T_mm:.4f} mm\n"
            f"  l_track  = {self.l_track_mm:.3f} mm\n"
            f"  h_via    = {self.h_via_mm:.4f} mm\n"
            f"  d_via    = {self.d_via_mm:.4f} mm\n"
            f"  n_vias   = {self.n_vias}\n"
            f"  l_trace  = {self.l_trace_mm:.3f} mm\n"
            f"  εr       = {self.epsilon_r:.2f}\n"
            f"  N_turns  = {self.N_turns}\n"
            f"  p        = {self.p_mm:.4f} mm\n"
        )


# ---------------------------------------------------------------------------
# Extraktor
# ---------------------------------------------------------------------------

class GeometryExtractor:
    """
    Extrahiert GeometryParameters aus TraceLayout, Board und optionalem Stackup.

    Args:
        stackup:     Stackup-Objekt (z. B. aus stackup_design03.yaml geladen).
                     Falls None: Design-03-Fallback-Werte werden verwendet.
        config_path: Pfad zu geometry_baseline.yaml (optionaler Fallback für
                     W, d_via, N_turns wenn keine Klassifikation vorliegt).
    """

    def __init__(
        self,
        stackup: Stackup | None = None,
        config_path: Path | None = None,
    ) -> None:
        self._stackup = stackup
        self._config_path = config_path

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def extract(self, layout: TraceLayout, board: Board) -> GeometryParameters:
        """
        Extrahiert alle GeometryParameters aus dem klassifizierten TraceLayout.

        Args:
            layout: Klassifiziertes TraceLayout (nach FishboneClassifier).
            board:  Vollständig geladenes Board-Domainobjekt.

        Returns:
            GeometryParameters mit allen Eingangsgrößen für die Formeln.
        """
        # Feature-Listen aus Board aufbauen (feature_id → Objekt)
        line_by_id = {f.feature_id: f for la in board.copper_layers for f in la.lines}

        # WINDING-Segmente
        winding_features = [
            line_by_id[c.feature_id]
            for c in layout.winding_traces
            if c.feature_id in line_by_id
        ]
        # CONNECTION-Segmente
        connection_features = [
            line_by_id[c.feature_id]
            for c in layout.classifications
            if c.role == TraceRole.CONNECTION and c.feature_id in line_by_id
        ]

        # Geometrische Größen aus Features
        l_track_mm = sum(_seg_length(f) for f in winding_features)
        l_trace_mm = sum(_seg_length(f) for f in connection_features)

        W_mm = (
            sum(f.width_mm for f in winding_features) / len(winding_features)
            if winding_features else self._baseline_W()
        )
        w_trace_mm = (
            sum(f.width_mm for f in connection_features) / len(connection_features)
            if connection_features else W_mm
        )

        # Windungsanzahl = Anzahl WINDING-Segmente auf der Hauptlage
        # (Fishbone: jede Rippe = eine Windung)
        winding_layer_name = (
            layout.winding_traces[0].layer_name
            if layout.winding_traces else "top_layer"
        )
        N_turns = sum(
            1 for c in layout.winding_traces if c.layer_name == winding_layer_name
        )
        if N_turns == 0:
            N_turns = max(1, len(layout.winding_traces))
            logger.warning("N_turns aus layer-Filter = 0, Fallback: %d (alle WINDING-Segmente)", N_turns)

        # Stackup-Parameter – H = Abstand Windungslage → nächste innere Lage
        T_mm, H_mm, epsilon_r = self._stackup_params(winding_layer_name)

        # Via-Parameter
        d_via_mm, n_vias = self._via_params(board)
        h_via_mm = self._via_height()

        if l_track_mm == 0.0:
            logger.warning(
                "l_track = 0 – keine WINDING-Features im TraceLayout gefunden. "
                "Klassifikation prüfen."
            )

        # Pitch (Mitte-Mitte-Abstand) aus WINDING-Features auf der Hauptlage
        p_mm = self._calc_pitch(winding_features, winding_layer_name)

        return GeometryParameters(
            W_mm=W_mm,
            H_mm=H_mm,
            T_mm=T_mm,
            l_track_mm=l_track_mm,
            h_via_mm=h_via_mm,
            d_via_mm=d_via_mm,
            n_vias=n_vias,
            l_trace_mm=l_trace_mm,
            w_trace_mm=w_trace_mm,
            epsilon_r=epsilon_r,
            N_turns=N_turns,
            p_mm=p_mm,
            winding_layer=winding_layer_name,
        )

    # ------------------------------------------------------------------
    # Pitch-Berechnung
    # ------------------------------------------------------------------

    @staticmethod
    def _calc_pitch(winding_features: list, winding_layer_name: str) -> float:
        """
        Berechnet den mittleren Pitch (Mitte-Mitte-Abstand) benachbarter
        WINDING-Segmente auf der Hauptlage [mm].

        Strategie:
            1. Mittelpunkte aller WINDING-Features auf der Hauptlage bestimmen.
            2. Für jeden Mittelpunkt den nächsten Nachbarn finden.
            3. Median der Abstände = Pitch.

        Falls weniger als 2 Features vorliegen, wird 2.0 mm als Fallback
        zurückgegeben.
        """
        # Mittelpunkte der Winding-Features auf der Hauptlage
        midpoints: list[tuple[float, float]] = []
        for f in winding_features:
            # Layer-Filter: nur Features auf der Hauptlage berücksichtigen
            if hasattr(f, 'layer') and f.layer != winding_layer_name:
                continue
            mx = (f.start.x_mm + f.end.x_mm) / 2.0
            my = (f.start.y_mm + f.end.y_mm) / 2.0
            midpoints.append((mx, my))

        if len(midpoints) < 2:
            # Fallback: Alle Features (ohne Layer-Filter)
            midpoints = [
                ((f.start.x_mm + f.end.x_mm) / 2.0,
                 (f.start.y_mm + f.end.y_mm) / 2.0)
                for f in winding_features
            ]

        if len(midpoints) < 2:
            logger.warning("Weniger als 2 WINDING-Features – Pitch-Fallback 2.0 mm.")
            return 2.0

        # Nächste-Nachbar-Abstände
        nn_dists: list[float] = []
        for i, (xi, yi) in enumerate(midpoints):
            min_d = float("inf")
            for j, (xj, yj) in enumerate(midpoints):
                if i == j:
                    continue
                d = math.hypot(xj - xi, yj - yi)
                if d < min_d:
                    min_d = d
            nn_dists.append(min_d)

        # Median statt Mittelwert (robust gegen Ausreißer)
        nn_dists.sort()
        n = len(nn_dists)
        pitch = nn_dists[n // 2] if n % 2 == 1 else (
            nn_dists[n // 2 - 1] + nn_dists[n // 2]
        ) / 2.0

        logger.debug("Pitch aus %d WINDING-Mittelpunkten: %.4f mm", n, pitch)
        return pitch

    # ------------------------------------------------------------------
    # Stackup-Parameter
    # ------------------------------------------------------------------

    def _stackup_params(self, winding_layer: str = "top_layer") -> tuple[float, float, float]:
        """
        Gibt (T_mm, H_mm, epsilon_r) zurück für die angegebene Windungslage.

        H ist der Abstand der Windungslage zur **direkt anliegenden** inneren Lage
        (nicht von Top zu Bottom!):

            top_layer    → Dielektrikum zwischen top_layer    und mid-layer_1
            bottom_layer → Dielektrikum zwischen mid-layer_2  und bottom_layer
            mid-layer_1  → Dielektrikum zwischen top_layer    und mid-layer_1
            mid-layer_2  → Dielektrikum zwischen mid-layer_2  und bottom_layer

        Suchstrategie:
            1. ``between_layers``-Feld im DielectricSpec (bevorzugt, explizit)
            2. Position im Stackup (Dielectric[i] liegt zwischen CopperLayer[i] und [i+1])
        """
        if self._stackup is None or not self._stackup.copper_layers:
            logger.debug("Stackup fehlt – Design-03-Fallback (T=%.4f H=%.4f εr=%.2f)",
                         _D03_T_MM, _D03_H_MM, _D03_EPS_R)
            return _D03_T_MM, _D03_H_MM, _D03_EPS_R

        # T: Kupferdicke der Windungslage
        winding_cu = next(
            (c for c in self._stackup.copper_layers if c.name == winding_layer),
            self._stackup.copper_layers[0],
        )
        T_mm = winding_cu.thickness_um / 1000.0

        # H + εr: Dielektrikum direkt anliegend an der Windungslage
        adjacent = self._find_adjacent_dielectric(winding_layer)
        if adjacent is None:
            logger.warning(
                "Kein anliegendes Dielektrikum für Lage '%s' gefunden – Fallback H=%.4f mm",
                winding_layer, _D03_H_MM,
            )
            return T_mm, _D03_H_MM, _D03_EPS_R

        logger.debug(
            "Stackup für Lage '%s': T=%.4f mm  H=%.4f mm  εr=%.2f  (Dielektrikum: %s)",
            winding_layer, T_mm, adjacent.thickness_mm, adjacent.epsilon_r, adjacent.name,
        )
        return T_mm, adjacent.thickness_mm, adjacent.epsilon_r

    def _find_adjacent_dielectric(
        self, layer_name: str
    ) -> DielectricSpec | None:
        """
        Findet das Dielektrikum, das direkt an ``layer_name`` angrenzt.

        Strategie 1 – ``between_layers`` explizit gesetzt:
            Suche das Dielektrikum, das ``layer_name`` in seinem
            ``between_layers``-Tupel enthält.

        Strategie 2 – Positionsbasiert (Fallback):
            Kupferlagen nach Index sortieren → Position i des gesuchten Layers.
            Randlage (i=0 oder i=last): Dielektrikum[0] bzw. Dielektrikum[-1].
            Innenlage: Dielektrikum[i-1] (näher zur Oberfläche).
        """
        stackup = self._stackup
        if stackup is None or not stackup.dielectrics:
            return None

        # --- Strategie 1: between_layers ---
        for d in stackup.dielectrics:
            if d.between_layers and layer_name in d.between_layers:
                return d

        # --- Strategie 2: Positionsbasiert ---
        cu_sorted = sorted(stackup.copper_layers, key=lambda c: c.index)
        cu_names  = [c.name for c in cu_sorted]
        if layer_name not in cu_names:
            return stackup.dielectrics[0]

        pos = cu_names.index(layer_name)
        # Randlagen: erste oder letzte Kupferlage
        if pos == 0:
            # Obere Außenlage → erstes Dielektrikum (nach innen)
            diel_idx = 0
        elif pos == len(cu_names) - 1:
            # Untere Außenlage → letztes Dielektrikum (nach innen)
            diel_idx = len(stackup.dielectrics) - 1
        else:
            # Innenlage → Dielektrikum oberhalb (zu kleinerer Indexseite)
            diel_idx = pos - 1

        diel_idx = max(0, min(diel_idx, len(stackup.dielectrics) - 1))
        return stackup.dielectrics[diel_idx]

    def _via_height(self) -> float:
        """Via-Höhe = Gesamtdicke der Leiterplatte."""
        if self._stackup is not None:
            return self._stackup.total_thickness_mm
        return _D03_TOTAL_MM

    # ------------------------------------------------------------------
    # Via-Parameter aus Bohrlage
    # ------------------------------------------------------------------

    def _via_params(self, board: Board) -> tuple[float, int]:
        """
        Gibt (d_via_mm, n_vias) aus der PTH-Bohrlage zurück.

        d_via_mm: Mittlerer Bohrdurchmesser aller PTH-Vias.
        n_vias:   Anzahl der PTH-Vias (Näherung: alle Vias = Spulen-Vias).
        """
        for layer in board.layers:
            if layer.layer_type == LayerType.DRILL and "plated" in layer.name.lower():
                pads = [p for p in layer.pads if p.is_via and p.diameter_mm > 0]
                if pads:
                    d_via_mm = sum(p.diameter_mm for p in pads) / len(pads)
                    n_vias = len(pads)
                    logger.debug("Via-Parameter aus Bohrlage '%s': d=%.3f mm, n=%d", layer.name, d_via_mm, n_vias)
                    return d_via_mm, n_vias

        # Fallback aus geometry_baseline.yaml
        d_via_mm = self._baseline_d_via()
        logger.warning("Keine PTH-Bohrlage gefunden – Via-Durchmesser aus Config: %.3f mm", d_via_mm)
        return d_via_mm, 0

    # ------------------------------------------------------------------
    # Baseline-Config-Fallbacks
    # ------------------------------------------------------------------

    def _baseline_W(self) -> float:
        if self._config_path:
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return float(data["coil"]["trace_width_mm"])
            except Exception:  # noqa: BLE001
                pass
        return 0.15  # typische Spurenbreite einer Rogowski-Spule

    def _baseline_d_via(self) -> float:
        if self._config_path:
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return float(data["via"]["drill_diameter_mm"])
            except Exception:  # noqa: BLE001
                pass
        return 0.20


# ---------------------------------------------------------------------------
# Interne Hilfsfunktion
# ---------------------------------------------------------------------------

def _seg_length(f) -> float:  # type: ignore[no-untyped-def]
    """Euklidische Segmentlänge [mm]."""
    return math.hypot(f.end.x_mm - f.start.x_mm, f.end.y_mm - f.start.y_mm)
