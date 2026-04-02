"""
Klassifikations-Domäne: Manuelle und automatische Segmentklassifikation.

Exportiert
----------
ClassificationEntry
    Einzelner, mutabler Segmenteintrag (role, sigma, window_id, note).
ClassifierConfig
    Konfigurationsparameter für den FishboneClassifier; lädt aus defaults.yaml.
ClassificationSpec
    Vollständige Klassifikation eines Boards – YAML-Serialisierung / -Deserialisierung.
TopologyGapFiller
    BFS-basiertes Auffüllen nicht klassifizierter Segmente entlang der Leiterbahn-Topologie.
FishboneClassifier
    Heuristischer Auto-Klassifikator (Layer-Name + Längenschwelle + Sigma-Richtung).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML ist nicht installiert. Bitte 'pip install pyyaml' ausführen."
    ) from exc

if TYPE_CHECKING:
    from pcb_rogowski.domain.board.models import Board, LineFeature
    from pcb_rogowski.domain.trace.models import TraceLayout


# ---------------------------------------------------------------------------
# ClassificationEntry
# ---------------------------------------------------------------------------

@dataclass
class ClassificationEntry:
    """
    Klassifikation eines einzelnen Leiterbahn-Segments (mutable).

    Im Gegensatz zu ``TraceClassification`` erlaubt dieses Dataclass
    ``sigma = 0`` (noch nicht festgelegt / Verbindungsleiter).

    Attributes:
        feature_id: Eindeutige ID des zugehörigen ``LineFeature``
                    (stabiler Geometrie-Hash, persistent über Ladevorgänge hinweg).
        layer_name: Lagenname des Segments.
        role:       Fachliche Rolle: ``"winding"`` | ``"connection"`` | ``"return"``.
        sigma:      Orientierungsvorzeichen: ``+1``, ``-1`` oder ``0`` (undefiniert).
        window_id:  Zugehöriges Via-Fenster für M-Berechnung (optional).
        note:       Freitext-Notiz, z. B. ``"manuell:winding"`` oder ``"auto:fishbone"``.
    """

    feature_id: str
    layer_name: str
    role: str
    sigma: int = 0
    window_id: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ("winding", "connection", "return"):
            raise ValueError(
                f"role muss 'winding', 'connection' oder 'return' sein, "
                f"erhalten: {self.role!r}"
            )
        if self.sigma not in (-1, 0, 1):
            raise ValueError(
                f"sigma muss -1, 0 oder +1 sein, erhalten: {self.sigma}"
            )


# ---------------------------------------------------------------------------
# ClassifierConfig
# ---------------------------------------------------------------------------

@dataclass
class ClassifierConfig:
    """
    Konfigurationsparameter für den :class:`FishboneClassifier`.

    Kann aus einer ``defaults.yaml`` / ``configs/*.yaml`` geladen werden
    (Schlüssel ``classifier:``).  Alle Felder sind überschreibbar,
    damit ``inspect_board.py`` CLI-Argumente direkt setzen kann.

    Attributes:
        angle_tolerance_deg:        Winkeltoleranz für „parallele" Segmente [°].
        min_parallel_segments:      Mindestanzahl paralleler Segmente für Fishbone-Erkennung.
        short_segment_threshold_mm: Längenschwelle Windungs- vs. Verbindungsleiter [mm].
        winding_layer_name:         Lagenname der Windungsleiter.
        return_layer_name:          Lagenname des Rückleiters.
    """

    angle_tolerance_deg: float = 10.0
    min_parallel_segments: int = 3
    short_segment_threshold_mm: float = 1.0   # Startwert; per defaults.yaml überschreibbar
    winding_layer_name: str = "top_layer"
    return_layer_name: str = "bottom_layer"

    @classmethod
    def from_yaml(cls, path: Path) -> "ClassifierConfig":
        """Lädt die Classifier-Konfiguration aus einer YAML-Datei."""
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        cfg = data.get("classifier", {})
        return cls(
            angle_tolerance_deg=float(
                cfg.get("angle_tolerance_deg", cls.angle_tolerance_deg)
            ),
            min_parallel_segments=int(
                cfg.get("min_parallel_segments", cls.min_parallel_segments)
            ),
            short_segment_threshold_mm=float(
                cfg.get("short_segment_threshold_mm", cls.short_segment_threshold_mm)
            ),
            winding_layer_name=str(
                cfg.get("winding_layer_name", cls.winding_layer_name)
            ),
            return_layer_name=str(
                cfg.get("return_layer_name", cls.return_layer_name)
            ),
        )


# ---------------------------------------------------------------------------
# ClassificationSpec
# ---------------------------------------------------------------------------

@dataclass
class ClassificationSpec:
    """
    Vollständige Klassifikation eines Boards.

    Wird per YAML serialisiert / deserialisiert und dient als Eingabe für
    :class:`~scripts.classify_board.ClassificationEditor` und alle
    nachgelagerten Berechnungsmodule.

    YAML-Format
    -----------
    ::

        board_name: "Desgin_03"
        source_gerber: "data_samples/gerber/Desgin_03"
        auto_detected: false
        notes: "Manuelle Klassifikation."
        entries:
          - feature_id: "ln_a3f8c12d9b01"
            layer_name: "top_layer"
            role: "winding"
            sigma: 1
            window_id: null
            note: "manuell:winding"
    """

    board_name: str
    source_gerber: str
    entries: list[ClassificationEntry] = field(default_factory=list)
    auto_detected: bool = False
    notes: str = ""

    # ------------------------------------------------------------------
    # YAML I/O
    # ------------------------------------------------------------------

    def to_yaml(self, path: Path) -> None:
        """Serialisiert die Klassifikation als YAML-Datei."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {
            "board_name":    self.board_name,
            "source_gerber": self.source_gerber,
            "auto_detected": self.auto_detected,
            "notes":         self.notes,
            "entries": [
                {
                    "feature_id": e.feature_id,
                    "layer_name": e.layer_name,
                    "role":       e.role,
                    "sigma":      e.sigma,
                    "window_id":  e.window_id,
                    "note":       e.note,
                }
                for e in self.entries
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            yaml.dump(
                data,
                fh,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

    @classmethod
    def from_yaml(cls, path: Path) -> "ClassificationSpec":
        """Lädt eine Klassifikation aus einer YAML-Datei."""
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        entries = [
            ClassificationEntry(
                feature_id=str(e["feature_id"]),
                layer_name=str(e.get("layer_name", "")),
                role=str(e["role"]),
                sigma=int(e.get("sigma", 0)),
                window_id=e.get("window_id"),
                note=e.get("note"),
            )
            for e in (data.get("entries") or [])
        ]
        return cls(
            board_name=str(data.get("board_name", "")),
            source_gerber=str(data.get("source_gerber", "")),
            entries=entries,
            auto_detected=bool(data.get("auto_detected", False)),
            notes=str(data.get("notes", "")),
        )

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def role_counts(self) -> dict[str, int]:
        """Gibt die Anzahl der Einträge pro Rolle zurück."""
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.role] = counts.get(e.role, 0) + 1
        return counts

    def entry_by_id(self) -> dict[str, ClassificationEntry]:
        """Gibt ein schnelles Lookup-Dict ``{feature_id → entry}`` zurück."""
        return {e.feature_id: e for e in self.entries}

    def to_trace_layout(self) -> "TraceLayout":
        """
        Konvertiert die :class:`ClassificationSpec` in ein :class:`TraceLayout`.

        Das ``TraceLayout`` wird von :class:`~pcb_rogowski.domain.coil.service.CoilParameterServiceImpl`
        und :class:`~pcb_rogowski.domain.coil.geometry.GeometryExtractor` für alle
        Berechnungen verwendet.

        Sigma-Konvertierung:
            - ``"winding"``    → ``sigma`` aus Entry (±1); falls 0 → +1 als Fallback
            - ``"return"``     → ``sigma = -1`` (immer)
            - ``"connection"`` → ``sigma = +1`` (Vorzeichen irrelevant, wird nicht summiert)

        Returns:
            :class:`TraceLayout` mit allen klassifizierten Segmenten.
            ``via_windows`` ist leer (wird für M-Berechnung separat befüllt).
        """
        from pcb_rogowski.domain.trace.models import (
            TraceClassification,
            TraceLayout,
            TraceRole,
        )

        _role_map = {
            "winding":    TraceRole.WINDING,
            "connection": TraceRole.CONNECTION,
            "return":     TraceRole.RETURN,
        }
        _sigma_default = {
            "winding":    1,
            "connection": 1,   # neutral – nicht summiert
            "return":    -1,
        }

        classifications: list[TraceClassification] = []
        for e in self.entries:
            role = _role_map.get(e.role, TraceRole.CONNECTION)
            if e.role == "winding":
                sigma = e.sigma if e.sigma in (-1, 1) else 1
            else:
                sigma = _sigma_default[e.role]

            classifications.append(TraceClassification(
                feature_id=e.feature_id,
                layer_name=e.layer_name,
                role=role,
                sigma=sigma,
                window_id=e.window_id,
            ))

        return TraceLayout(
            board_name=self.board_name,
            classifications=classifications,
            via_windows=[],
        )


# ---------------------------------------------------------------------------
# TopologyGapFiller
# ---------------------------------------------------------------------------

class TopologyGapFiller:
    """
    Füllt nicht klassifizierte Segmente per Topologie-Propagation (BFS).

    Algorithmus
    -----------
    1.  Alle Endpunkte der Segmente werden auf ein Snap-Raster quantisiert
        (Standard: 0.01 mm), um Floating-Point-Unschärfen auszugleichen.
    2.  Ein Adjacency-Graph wird aufgebaut: Zwei Segmente gelten als Nachbarn,
        wenn sie einen Endpunkt teilen (nach Snap).
    3.  Von allen bereits klassifizierten Segmenten startet eine BFS-Welle,
        die Rollen an unklassifizierte Nachbar-Segmente weitergibt.
    4.  Rolle des neuen Segments:

        * Haben **alle** klassifizierten Nachbarn an **beiden** Endpunkten
          dieselbe Rolle → diese Rolle wird übernommen.
        * Sonst → Rolle des unmittelbaren BFS-Vorgängers.

    5.  Sigma-Zuweisung für neue ``"winding"``-Segmente:
        Sigma wird gegenüber dem Vorgänger-Sigma negiert (alternierende
        Windungsrichtung). Für ``"connection"`` → 0, für ``"return"`` → −1.

    Bereits klassifizierte Segmente (manuell oder aus YAML) werden
    **nicht** verändert.
    """

    _SNAP: float = 0.01  # mm – Quantisierungsraster für Endpunkte

    def fill(
        self,
        board: "Board",
        spec: ClassificationSpec,
    ) -> ClassificationSpec:
        """
        Führt das Gap-Filling durch und gibt eine **neue** ClassificationSpec zurück.

        Bestehende Einträge in ``spec`` bleiben unverändert; neu befüllte
        Segmente erhalten ``note="auto:gap-fill"``.

        Args:
            board: Vollständig geladenes Board-Modell.
            spec:  Bestehende (ggf. teilweise) Klassifikation.

        Returns:
            Neue :class:`ClassificationSpec` mit bestehenden + gap-gefüllten Einträgen.
        """
        all_lines: list[LineFeature] = [
            f for la in board.copper_layers for f in la.lines
        ]

        # Alle Linien indizieren
        feature_by_id: dict[str, LineFeature] = {f.feature_id: f for f in all_lines}

        # Endpunkt-Index: snap-quantisierter Punkt → Liste von feature_ids
        endpoint_to_ids: dict[tuple[int, int], list[str]] = {}
        for f in all_lines:
            for pt in (f.start, f.end):
                key = self._snap_key(pt.x_mm, pt.y_mm)
                endpoint_to_ids.setdefault(key, []).append(f.feature_id)

        # Adjacency-Graph: feature_id → {benachbarte feature_ids}
        adjacency: dict[str, set[str]] = {f.feature_id: set() for f in all_lines}
        for ids in endpoint_to_ids.values():
            for a in ids:
                for b in ids:
                    if a != b:
                        adjacency[a].add(b)

        # Aktueller Klassifikationsstand
        entry_map: dict[str, ClassificationEntry] = {
            e.feature_id: e for e in spec.entries
        }

        # BFS-Queue: (feature_id_to_fill, predecessor_entry)
        queue: deque[tuple[str, ClassificationEntry]] = deque()
        for e in spec.entries:
            for neighbor_id in adjacency.get(e.feature_id, set()):
                if neighbor_id not in entry_map:
                    queue.append((neighbor_id, e))

        new_entries: list[ClassificationEntry] = []

        while queue:
            fid, predecessor = queue.popleft()
            if fid in entry_map:
                # Bereits klassifiziert (manuell oder durch frühere BFS-Runde)
                continue
            f = feature_by_id.get(fid)
            if f is None:
                continue

            # --- Rollenwahl ---
            start_key = self._snap_key(f.start.x_mm, f.start.y_mm)
            end_key   = self._snap_key(f.end.x_mm,   f.end.y_mm)
            start_roles = self._neighbor_roles(
                start_key, endpoint_to_ids, entry_map, fid
            )
            end_roles = self._neighbor_roles(
                end_key, endpoint_to_ids, entry_map, fid
            )
            all_roles = start_roles | end_roles

            if len(all_roles) == 1:
                # Eindeutige Einigung beider Seiten
                role = next(iter(all_roles))
            else:
                # Uneinigkeit → Vorgänger-Rolle übernehmen
                role = predecessor.role

            sigma = self._infer_sigma(role, predecessor)

            entry = ClassificationEntry(
                feature_id=fid,
                layer_name=f.layer_name,
                role=role,
                sigma=sigma,
                window_id=predecessor.window_id,
                note="auto:gap-fill",
            )
            entry_map[fid] = entry
            new_entries.append(entry)

            # Unklassifizierte Nachbarn in die Queue einstellen
            for neighbor_id in adjacency.get(fid, set()):
                if neighbor_id not in entry_map:
                    queue.append((neighbor_id, entry))

        return ClassificationSpec(
            board_name=spec.board_name,
            source_gerber=spec.source_gerber,
            entries=list(spec.entries) + new_entries,
            auto_detected=spec.auto_detected,
            notes=spec.notes,
        )

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _snap_key(self, x: float, y: float) -> tuple[int, int]:
        """Quantisiert einen Punkt auf das Snap-Raster."""
        factor = 1.0 / self._SNAP
        return (round(x * factor), round(y * factor))

    @staticmethod
    def _neighbor_roles(
        endpoint_key: tuple[int, int],
        endpoint_to_ids: dict[tuple[int, int], list[str]],
        entry_map: dict[str, ClassificationEntry],
        exclude_id: str,
    ) -> set[str]:
        """Gibt die Rollen aller klassifizierten Segmente an einem Endpunkt zurück."""
        return {
            entry_map[fid].role
            for fid in endpoint_to_ids.get(endpoint_key, [])
            if fid != exclude_id and fid in entry_map
        }

    @staticmethod
    def _infer_sigma(role: str, predecessor: ClassificationEntry) -> int:
        """Leitet den sigma-Wert für ein neues Segment aus dem Vorgänger ab."""
        if role == "connection":
            return 0
        if role == "return":
            return -1
        # winding: Vorgänger-Sigma alternieren
        if predecessor.role == "winding" and predecessor.sigma in (-1, 1):
            return -predecessor.sigma
        return 1  # Standardwert, wenn kein Winding-Vorgänger bekannt


# ---------------------------------------------------------------------------
# FishboneClassifier
# ---------------------------------------------------------------------------

class FishboneClassifier:
    """
    Heuristischer Auto-Klassifikator für das Fishbone-Muster einer Rogowski-Spule.

    Strategie
    ---------
    1.  **Layer-basierte Grobklassifikation**

        - Segmente auf ``config.winding_layer_name``  → ``"winding"``
        - Segmente auf ``config.return_layer_name``   → ``"return"``
        - Alle anderen Kupferlagen                    → ``"connection"``

    2.  **Längen-basierte Verfeinerung** (nur auf Winding- und unbekannten Lagen)

        - Segmente kürzer als ``config.short_segment_threshold_mm``
          → ``"connection"`` (kurze Querstücke / Via-Footprints)

    3.  **Sigma-Zuweisung für Winding-Segmente**

        Die lokale Richtung des Segments bestimmt das Vorzeichen:

        - ``dy > 0`` (nach oben)  → ``σ = +1``
        - ``dy < 0`` (nach unten) → ``σ = -1``
        - ``|dy| < 1e-6`` (horizontal): ``dx ≥ 0`` → ``+1``, sonst ``-1``

    Diese Heuristik liefert einen sinnvollen Ausgangspunkt; alle Fehler können
    anschließend interaktiv mit ``scripts/classify_board.py`` korrigiert werden.
    """

    def __init__(self, config: ClassifierConfig | None = None) -> None:
        self.config: ClassifierConfig = config or ClassifierConfig()

    def classify(self, board: "Board") -> ClassificationSpec:
        """
        Klassifiziert alle Kupfer-Linien des Boards.

        Args:
            board: Vollständig geladenes Board-Modell.

        Returns:
            :class:`ClassificationSpec` mit einem Eintrag pro ``LineFeature``.
        """
        cfg = self.config
        entries: list[ClassificationEntry] = []

        for layer in board.copper_layers:
            for f in layer.lines:
                role, sigma = self._classify_feature(f, layer.name, cfg)
                entries.append(
                    ClassificationEntry(
                        feature_id=f.feature_id,
                        layer_name=f.layer_name,
                        role=role,
                        sigma=sigma,
                        window_id=None,
                        note="auto:fishbone",
                    )
                )

        return ClassificationSpec(
            board_name=board.name,
            source_gerber=str(board.source_file),
            entries=entries,
            auto_detected=True,
            notes=(
                f"Automatische Fishbone-Klassifikation.  "
                f"Winding-Layer='{cfg.winding_layer_name}'  "
                f"Return-Layer='{cfg.return_layer_name}'  "
                f"Schwelle={cfg.short_segment_threshold_mm} mm"
            ),
        )

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    @staticmethod
    def _seg_length(f: "LineFeature") -> float:
        return math.hypot(
            f.end.x_mm - f.start.x_mm,
            f.end.y_mm - f.start.y_mm,
        )

    @staticmethod
    def _seg_sigma(f: "LineFeature") -> int:
        """Vorzeichen basierend auf der lokalen Segment-Richtung."""
        dy = f.end.y_mm - f.start.y_mm
        if abs(dy) > 1e-6:
            return 1 if dy > 0 else -1
        dx = f.end.x_mm - f.start.x_mm
        return 1 if dx >= 0 else -1

    def _classify_feature(
        self,
        f: "LineFeature",
        layer_name: str,
        cfg: ClassifierConfig,
    ) -> tuple[str, int]:
        """Gibt ``(role, sigma)`` für ein einzelnes :class:`LineFeature` zurück."""
        length = self._seg_length(f)

        # Return-Layer
        if layer_name == cfg.return_layer_name:
            return "return", -1

        # Winding-Layer
        if layer_name == cfg.winding_layer_name:
            if length < cfg.short_segment_threshold_mm:
                return "connection", 0
            return "winding", self._seg_sigma(f)

        # Alle anderen Lagen → kurze Stücke = connection, lange = winding
        if length < cfg.short_segment_threshold_mm:
            return "connection", 0
        return "winding", self._seg_sigma(f)
