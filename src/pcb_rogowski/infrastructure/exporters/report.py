"""
Infrastructure: Berechnungsbericht-Exporter.

Exportiert CalculationTrace-Objekte in verschiedene Formate:
JSON, Markdown und später PDF.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pcb_rogowski.domain.common.trace import CalculationTrace

logger = logging.getLogger(__name__)


class CalculationReportExporter:
    """Exportiert Rechen-Protokolle in JSON- oder Markdown-Format."""

    def export_json(self, trace: CalculationTrace, output_path: Path) -> None:
        """Schreibt den Trace als JSON-Datei."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(trace.to_json(), encoding="utf-8")
        logger.info("JSON-Bericht exportiert: %s", output_path)

    def export_markdown(self, trace: CalculationTrace, output_path: Path) -> None:
        """Schreibt den Trace als Markdown-Datei."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(trace.to_markdown(), encoding="utf-8")
        logger.info("Markdown-Bericht exportiert: %s", output_path)

    def export_all(self, trace: CalculationTrace, output_dir: Path) -> None:
        """Exportiert alle Formate in ein Verzeichnis."""
        name = trace.calculation_name.replace(" ", "_").lower()
        self.export_json(trace, output_dir / f"{name}.json")
        self.export_markdown(trace, output_dir / f"{name}.md")
