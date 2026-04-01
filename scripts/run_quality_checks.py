#!/usr/bin/env python3
"""
run_quality_checks.py – Alle Qualitätsprüfungen lokal ausführen.

Führt der Reihe nach aus:
1. ruff  – Linting + Import-Check
2. black – Formatierungsprüfung
3. mypy  – Statische Typprüfung
4. pytest – Tests mit Coverage

Aufruf:
    python scripts/run_quality_checks.py
    python scripts/run_quality_checks.py --fix   (wendet ruff/black-Fixes an)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"


def run(cmd: list[str], label: str) -> bool:
    """Führt einen Befehl aus. Gibt True zurück wenn erfolgreich."""
    print(f"\n{'─'*50}")
    print(f"▶ {label}")
    print(f"  Befehl: {' '.join(cmd)}")
    print(f"{'─'*50}")
    result = subprocess.run(cmd, cwd=ROOT)
    status = "✅ OK" if result.returncode == 0 else "❌ FEHLER"
    print(f"\n{status}: {label}")
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Qualitätsprüfungen ausführen")
    parser.add_argument("--fix", action="store_true", help="Automatische Fixes anwenden")
    args = parser.parse_args()

    print("=" * 60)
    print("PCB Rogowski Tool – Qualitätsprüfungen")
    print("=" * 60)

    results: dict[str, bool] = {}

    # ruff
    ruff_cmd = ["ruff", "check", "src", "tests"]
    if args.fix:
        ruff_cmd.append("--fix")
    results["ruff"] = run(ruff_cmd, "ruff – Linting")

    # black
    black_cmd = ["black", "--check", "src", "tests"] if not args.fix else ["black", "src", "tests"]
    results["black"] = run(black_cmd, "black – Formatierung")

    # mypy
    results["mypy"] = run(
        ["mypy", "src", "--ignore-missing-imports"],
        "mypy – Typprüfung"
    )

    # pytest
    results["pytest"] = run(
        ["pytest", "--tb=short", "-v", "--cov=src", "--cov-report=term-missing"],
        "pytest – Tests + Coverage"
    )

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("Zusammenfassung:")
    all_ok = True
    for tool, ok in results.items():
        icon = "✅" if ok else "❌"
        print(f"  {icon} {tool}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\n❌ Qualitätsprüfungen fehlgeschlagen.")
        sys.exit(1)
    else:
        print("\n✅ Alle Prüfungen bestanden.")


if __name__ == "__main__":
    main()
