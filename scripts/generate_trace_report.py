#!/usr/bin/env python3
"""
generate_trace_report.py – Rechen-Protokoll aus einer JSON-Trace-Datei exportieren.

Liest eine CalculationTrace-JSON-Datei und gibt einen formatierten
Markdown-Bericht aus oder speichert ihn.

Aufruf:
    python scripts/generate_trace_report.py path/to/trace.json
    python scripts/generate_trace_report.py path/to/trace.json --output bericht.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def trace_dict_to_markdown(data: dict) -> str:
    """Wandelt ein Trace-Dictionary in einen Markdown-Bericht um."""
    lines = [
        f"# Rechen-Protokoll: {data.get('calculation_name', 'Unbekannt')}",
        "",
        f"**Zeitstempel:** {data.get('timestamp', '–')}",
        f"**Version:** {data.get('software_version', '–')} ({data.get('git_commit', '–')})",
        f"**Status:** {data.get('quality_status', '–').upper()}",
        "",
    ]

    warnings = data.get("warnings", [])
    if warnings:
        lines.append("## ⚠️ Warnungen")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    config_versions = data.get("config_versions", {})
    if config_versions:
        lines.append("## Verwendete Konfigurationen")
        for k, v in config_versions.items():
            lines.append(f"- {k}: `{v}`")
        lines.append("")

    steps = data.get("steps", [])
    if steps:
        lines.append("## Rechenschritte")
        for i, step in enumerate(steps, 1):
            lines.append(f"### Schritt {i}: {step.get('name', '–')}")
            lines.append(f"**Formel:** `{step.get('formula', '–')}`")
            inputs = step.get("inputs", {})
            if inputs:
                lines.append("**Eingaben:**")
                for k, v in inputs.items():
                    lines.append(f"  - {k} = {v}")
            lines.append(f"**Ergebnis:** {step.get('output', '–')} {step.get('unit', '')}")
            note = step.get("note")
            if note:
                lines.append(f"**Hinweis:** {note}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rechen-Protokoll aus JSON exportieren")
    parser.add_argument("input", type=Path, help="Pfad zur JSON-Trace-Datei")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Ausgabedatei (optional)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ Datei nicht gefunden: {args.input}", file=sys.stderr)
        sys.exit(1)

    with args.input.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    markdown = trace_dict_to_markdown(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"✅ Bericht gespeichert: {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
