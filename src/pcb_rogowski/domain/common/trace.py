"""
Domain-Modelle: Traceability – Rechen-Protokoll und Herleitung.

Jede wichtige Berechnung liefert ein CalculationTrace-Objekt,
das alle Zwischenschritte, Eingaben, Formeln und Warnungen enthält.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class QualityStatus(str, Enum):
    """Qualitätsstatus eines Berechnungsergebnisses."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class TraceStep:
    """
    Ein einzelner Rechenschritt in einer Berechnung.

    Attributes:
        name: Sprechender Name des Schritts (z. B. "Berechne L_track").
        formula: Formel als String (LaTeX oder Python-Ausdruck).
        inputs: Dict mit Eingabegrößen und ihren Werten.
        output: Numerisches Ergebnis dieses Schritts.
        unit: Physikalische Einheit des Ergebnisses.
        note: Optionaler Kommentar oder Begründung.
    """

    name: str
    formula: str
    inputs: dict[str, float]
    output: float
    unit: str
    note: str | None = None


@dataclass(frozen=True)
class CalculationTrace:
    """
    Vollständiges Rechen-Protokoll einer Berechnung.

    Enthält alle Schritte, Warnungen, Quellen und Metadaten.
    Wird an jedes Ergebnisobjekt angehängt und kann als JSON
    oder Markdown exportiert werden.
    """

    calculation_name: str
    steps: tuple[TraceStep, ...]
    warnings: tuple[str, ...]
    quality_status: QualityStatus
    source_files: tuple[str, ...]
    config_versions: dict[str, str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    software_version: str = "0.1.0"
    git_commit: str = "unknown"

    def to_dict(self) -> dict:
        """Serialisiert den Trace als Dictionary (für JSON-Export)."""
        return {
            "calculation_name": self.calculation_name,
            "timestamp": self.timestamp,
            "software_version": self.software_version,
            "git_commit": self.git_commit,
            "quality_status": self.quality_status.value,
            "source_files": list(self.source_files),
            "config_versions": self.config_versions,
            "warnings": list(self.warnings),
            "steps": [
                {
                    "name": s.name,
                    "formula": s.formula,
                    "inputs": s.inputs,
                    "output": s.output,
                    "unit": s.unit,
                    "note": s.note,
                }
                for s in self.steps
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialisiert den Trace als JSON-String."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        """Erstellt einen lesbaren Markdown-Bericht."""
        lines = [
            f"# Rechen-Protokoll: {self.calculation_name}",
            f"",
            f"**Zeitstempel:** {self.timestamp}",
            f"**Version:** {self.software_version} ({self.git_commit})",
            f"**Status:** {self.quality_status.value.upper()}",
            f"",
        ]
        if self.warnings:
            lines.append("## ⚠️ Warnungen")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        lines.append("## Rechenschritte")
        for i, step in enumerate(self.steps, 1):
            lines.append(f"### Schritt {i}: {step.name}")
            lines.append(f"**Formel:** `{step.formula}`")
            lines.append(f"**Eingaben:**")
            for k, v in step.inputs.items():
                lines.append(f"  - {k} = {v}")
            lines.append(f"**Ergebnis:** {step.output} {step.unit}")
            if step.note:
                lines.append(f"**Hinweis:** {step.note}")
            lines.append("")

        return "\n".join(lines)
