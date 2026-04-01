"""
Infrastructure: Persistenz-Manager (Stub).

Speichert und lädt Projektdaten im YAML/JSON-Format.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from pcb_rogowski.domain.trace.models import TraceLayout, TraceClassification, TraceRole, ViaWindow

logger = logging.getLogger(__name__)


class PersistenceManager:
    """
    Speichert und lädt Projektdaten (TraceLayout, Configs) als YAML/JSON.

    Status: Stub – Sprint 2 implementiert das vollständige Schema.
    """

    def save_trace_layout(self, layout: TraceLayout, path: Path) -> None:
        """Serialisiert ein TraceLayout als YAML-Datei."""
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "board_name": layout.board_name,
            "classifications": [
                {
                    "feature_id": c.feature_id,
                    "layer_name": c.layer_name,
                    "role": c.role.value,
                    "sigma": c.sigma,
                    "window_id": c.window_id,
                }
                for c in layout.classifications
            ],
            "via_windows": [
                {
                    "window_id": w.window_id,
                    "x_min_mm": w.x_min_mm,
                    "y_min_mm": w.y_min_mm,
                    "x_max_mm": w.x_max_mm,
                    "y_max_mm": w.y_max_mm,
                    "sigma": w.sigma,
                }
                for w in layout.via_windows
            ],
        }

        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(data, fh, allow_unicode=True, sort_keys=False)

        logger.info("TraceLayout gespeichert: %s", path)

    def load_trace_layout(self, path: Path) -> TraceLayout:
        """Lädt ein TraceLayout aus einer YAML-Datei."""
        if not path.exists():
            raise FileNotFoundError(f"Layout-Datei nicht gefunden: {path}")

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        classifications = [
            TraceClassification(
                feature_id=c["feature_id"],
                layer_name=c["layer_name"],
                role=TraceRole(c["role"]),
                sigma=c["sigma"],
                window_id=c.get("window_id"),
            )
            for c in data.get("classifications", [])
        ]

        via_windows = [
            ViaWindow(
                window_id=w["window_id"],
                x_min_mm=w["x_min_mm"],
                y_min_mm=w["y_min_mm"],
                x_max_mm=w["x_max_mm"],
                y_max_mm=w["y_max_mm"],
                sigma=w["sigma"],
            )
            for w in data.get("via_windows", [])
        ]

        logger.info("TraceLayout geladen: %s", path)
        return TraceLayout(
            board_name=data["board_name"],
            classifications=classifications,
            via_windows=via_windows,
        )
