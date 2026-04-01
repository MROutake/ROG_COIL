#!/usr/bin/env python3
"""
bootstrap_project.py – Entwicklungsumgebung einmalig einrichten.

Führt alle Schritte durch, die nach dem ersten `git clone` nötig sind:
1. Virtuelle Umgebung anlegen (falls nicht vorhanden)
2. Abhängigkeiten installieren
3. pre-commit hooks installieren
4. Überprüfen ob alles funktioniert

Aufruf:
    python scripts/bootstrap_project.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Führt einen Shell-Befehl aus und gibt die Ausgabe aus."""
    print(f"\n▶ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, capture_output=False)
    if check and result.returncode != 0:
        print(f"❌ Fehler bei: {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result


def main() -> None:
    print("=" * 60)
    print("PCB Rogowski Tool – Projekt-Bootstrap")
    print("=" * 60)

    venv = ROOT / ".venv"
    python = venv / "Scripts" / "python.exe" if sys.platform == "win32" else venv / "bin" / "python"
    pip = venv / "Scripts" / "pip.exe" if sys.platform == "win32" else venv / "bin" / "pip"

    # 1. Virtuelle Umgebung
    if not venv.exists():
        print("\n📦 Erstelle virtuelle Umgebung (.venv)...")
        run([sys.executable, "-m", "venv", str(venv)])
    else:
        print("\n✅ Virtuelle Umgebung bereits vorhanden.")

    # 2. Pakete installieren
    print("\n📥 Installiere Abhängigkeiten (inkl. Dev-Tools)...")
    run([str(pip), "install", "--upgrade", "pip"])
    run([str(pip), "install", "-e", ".[dev]"])

    # 3. pre-commit installieren
    print("\n🔗 Installiere pre-commit hooks...")
    pre_commit = venv / "Scripts" / "pre-commit.exe" if sys.platform == "win32" else venv / "bin" / "pre-commit"
    run([str(pre_commit), "install"])

    # 4. pytest ausführen
    print("\n🧪 Führe Tests aus...")
    pytest = venv / "Scripts" / "pytest.exe" if sys.platform == "win32" else venv / "bin" / "pytest"
    run([str(pytest), "--tb=short", "-q"], check=False)

    print("\n" + "=" * 60)
    print("✅ Bootstrap abgeschlossen!")
    print(f"   Aktiviere die Umgebung: .venv\\Scripts\\activate")
    print("=" * 60)


if __name__ == "__main__":
    main()
