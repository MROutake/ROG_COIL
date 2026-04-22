"""Helper to populate __init__.py docstrings (one-shot use)."""
from pathlib import Path

base = Path(__file__).resolve().parents[1] / "src" / "pcb_rogowski"

DOCS = {
    "__init__.py": '''"""PCB Rogowski Coil Analysis Tool.

Wissenschaftliches Framework zur Berechnung, Visualisierung und
Validierung von PCB-basierten Rogowski-Spulen. Bereitstellung eines
kompletten Workflows:

1. **Import**: Gerber (gerbonara), optional ODB++.
2. **Klassifikation**: Segment-Rollen (winding / return / connection)
   plus Orientierung sigma und Via-Fenster.
3. **Berechnung**: L (Ruehli/Lorenz), R (DC + Skin/Proximity),
   C (Parallelplatten), M (analytisch / Flaechenintegral / numerisch).
4. **Uebertragungsfunktion**: H(s) = s*M / (1 + s*R*C + s^2*L*C).
5. **Validierung**: Fit gegen Bode100-Messungen.

Einstiegspunkte: :func:`pcb_rogowski.main.main` (CLI) und
:func:`pcb_rogowski.main.main_gui` (PyQt6-GUI).

Alle Formeln siehe ``docs/berechnungen.md``.
"""
''',
    "domain/__init__.py": '''"""Domain Layer -- Fachmodelle und Berechnungs-Primitive.

Vollstaendig unabhaengig von UI, IO und Framework. Alle Groessen in
SI-Einheiten; Anzeige-Umrechnungen (uH, pF, nH) geschehen ausschliesslich
in :mod:`pcb_rogowski.ui` oder in expliziten Convenience-Properties.

Subpakete
---------

* ``board``      -- Board-/Layer-/LineFeature-/Pad-Modelle.
* ``trace``      -- Klassifikation, Topologie-Reparatur.
* ``coil``       -- L, R, C und Uebertragungsfunktion (LRC+M).
* ``mutual``     -- Gegeninduktivitaet M (3 Methoden).
* ``materials``  -- Materialdaten (Cu-Leitfaehigkeit T-abhaengig, eps_r).
* ``stackup``    -- Lagenaufbau (Kupferdicke, Prepreg, Dielektrika).
* ``common``     -- :class:`CalculationTrace`, :class:`TraceStep`.
* ``validation`` -- Bereichs- und Konsistenzpruefungen.

Architektur-Regel: Keine Importe aus :mod:`pcb_rogowski.infrastructure`,
:mod:`pcb_rogowski.app` oder :mod:`pcb_rogowski.ui`. Siehe
``docs/adr/ADR-001-layered-architecture.md``.
"""
''',
    "app/__init__.py": '''"""Application Layer -- Use-Cases und Ablaufsteuerung.

Dieses Paket orchestriert die Domaenen-Logik (Pipeline
Gerber-Import -> Klassifikation -> RLC/M-Berechnung) und enthaelt
bewusst KEINE Fachformeln, GUI- oder IO-Details.

Zentraler Einstiegspunkt:
:func:`pcb_rogowski.app.use_cases.analyze_design.analyze_design`.
"""
''',
    "infrastructure/__init__.py": '''"""Infrastructure Layer -- Ports & Adapters.

Enthaelt alle externen IO-Adapter: Gerber-/ODB-Import, YAML-Persistenz
fuer Klassifikation + Fenster, Bode100-CSV-Reader und Report-Exporter.
Abhaengig von externen Bibliotheken (gerbonara, pandas, pyyaml), nicht
aber von :mod:`pcb_rogowski.ui` oder :mod:`pcb_rogowski.app`.
"""
''',
    "ui/__init__.py": '''"""User-Interface-Layer (Qt-Desktop + ViewModels)."""
''',
    "domain/coil/__init__.py": '''"""Coil-Berechnungen: L, R, C und Uebertragungsfunktion.

Module
------

* ``inductance``        -- Eigen- und Via-Induktivitaet (Ruehli/Lorenz).
* ``resistance``        -- DC-Widerstand + Skin-/Proximity-Zuschlag.
* ``capacitance``       -- Parasitaere Parallelkapazitaet.
* ``transfer_function`` -- LRC+M-Ersatzschaltbild (``scipy.signal``).
* ``fitting``           -- Nichtlineare Anpassung an Bode100-Messungen.

Einheiten im gesamten Subpaket: SI (H, F, Ohm, Hz). Herleitungen:
``docs/berechnungen.md`` Abschnitt 2 - 4.
"""
''',
}

for rel, txt in DOCS.items():
    p = base / rel
    p.write_text(txt, encoding="utf-8")
    print("wrote", rel, len(txt))
