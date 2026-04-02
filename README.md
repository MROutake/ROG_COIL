# PCB Rogowski Tool

**Analytisches Analysetool für PCB-basierte Rogowski-Spulen**

Entwickelt im Rahmen einer Diplomarbeit. Dieses Repository stellt den professionellen
Neuaufbau des ursprünglichen Prototypen dar, strukturiert nach Clean-Architecture-Prinzipien.

---

## Projektziel

Das Tool ermöglicht die vollständige analytische Charakterisierung einer PCB-Rogowski-Spule:

- **Gerber-Import (RS-274X / X2)** aus Altium Designer via `gerbonara`
- **Interaktive Klassifikation** von Leiterbahnen und Via-Fenstern
- **Analytische Berechnung** von $L_\text{track}$, $L_\text{vias}$, $L_s$, $R_s$, $C_s$, $f_R$
- **Gegeninduktivitätsberechnung** $M_\text{ges}$ zum Dual-Busbar-Leiter
- **Physikalisches ODE-Sensor-Modell**
- **Vollständige Traceability** aller Berechnungen

---

## Architektur

Das Projekt ist nach einer strikten Schichtenarchitektur aufgebaut:

```
ui/          ← Nur Darstellung (PyQt6)
app/         ← Use Cases und Orchestrierung
domain/      ← Fachlogik, Formeln, Modelle (reine Python-Objekte)
infrastructure/ ← Gerber-Parser (gerbonara), YAML/JSON, Logging, Exportfunktionen
agents/      ← KI-Agenten-Prompts für GitHub Copilot
```

Keine Fachformeln in der GUI. Jede Berechnung liefert ein typisiertes
Ergebnisobjekt mit vollständigem Rechen-Protokoll.

Siehe [docs/architecture.md](docs/architecture.md) für Details.

---

## Setup

### Voraussetzungen

- Python 3.11 oder neuer
- Git

### Schnellstart

```bash
git clone git@github.com:MROutake/ROG_COIL.git
cd ROG_COIL

# Automatisches Bootstrap (venv + pip + pre-commit):
python scripts/bootstrap_project.py

# Umgebung aktivieren (Windows):
.venv\Scripts\activate

# Tests ausführen:
pytest
```

### Manuelle Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

pip install -e ".[dev]"
pre-commit install
```

---

## Projektstruktur

```
pcb_rogowski_tool/
├── src/pcb_rogowski/
│   ├── app/               ← Use Cases, DTOs
│   ├── domain/            ← Fachmodelle, Formeln
│   │   ├── board/         ← Board, Layer, Features
│   │   ├── coil/          ← CoilParameters
│   │   ├── mutual/        ← MutualInductanceResult
│   │   ├── trace/         ← TraceClassification, ViaWindow
│   │   ├── stackup/       ← Stackup, MaterialSet
│   │   └── common/        ← CalculationTrace, TraceStep
│   ├── infrastructure/    ← Gerber-Loader (gerbonara), Persistenz, Export
│   ├── ui/                ← Desktop-GUI (PyQt6)
│   ├── agents/prompts/    ← KI-Agenten-Prompts
│   └── main.py
├── tests/
│   ├── unit/              ← Formel- und Modell-Tests
│   ├── integration/       ← ODB → Board → Berechnung
│   ├── regression/        ← Schutz vor Refactoring-Fehlern
│   └── golden_cases/      ← Referenzfälle mit Sollwerten
├── configs/               ← geometry_baseline, materials, ...
├── docs/                  ← Architektur, Domänenmodell, ADRs
└── scripts/               ← Bootstrap, Qualitätsprüfung, Export
```

---

## Qualitätssicherung

```bash
# Alle Checks ausführen:
python scripts/run_quality_checks.py

# Mit automatischen Fixes:
python scripts/run_quality_checks.py --fix

# Einzelne Tools:
ruff check src tests
black src tests
mypy src
pytest --cov=src
```

---

## KI-Agenten-Strategie

Das Projekt nutzt GitHub Copilot mit definierten Rollen:

| Agent                  | Aufgabe                                  | Prompt                                          |
|------------------------|------------------------------------------|-------------------------------------------------|
| Architektur-Agent      | Ist-Analyse, Zielarchitektur             | [01_architecture_agent.md](src/pcb_rogowski/agents/prompts/01_architecture_agent.md) |
| Projektstruktur-Agent  | Gerüst und Tooling                       | [02_project_structure_agent.md](src/pcb_rogowski/agents/prompts/02_project_structure_agent.md) |
| Refactoring-Agent      | GUI/Domain-Trennung                      | [03_refactoring_agent.md](src/pcb_rogowski/agents/prompts/03_refactoring_agent.md) |
| Test-Agent             | Unit-Tests, Golden Cases                 | [04_test_agent.md](src/pcb_rogowski/agents/prompts/04_test_agent.md) |
| Dokumentations-Agent   | README, Architektur-Docs                 | [05_documentation_agent.md](src/pcb_rogowski/agents/prompts/05_documentation_agent.md) |
| Review-Agent           | Code-Review, Regelprüfung               | [06_review_agent.md](src/pcb_rogowski/agents/prompts/06_review_agent.md) |
| **Master-Agent**       | Sprint-Steuerung, Backlog-Verwaltung    | [00_master_agent.md](src/pcb_rogowski/agents/prompts/00_master_agent.md) |

---

## Sprint-Plan

| Sprint | Ziel                                     | Status      |
|--------|------------------------------------------|-------------|
| 1      | Fundament: Gerüst, Tooling, Domain-Modelle | ✅ Abgeschlossen |
| 2      | Gerber-Parser & Board-Modell (gerbonara) | ✅ Abgeschlossen |
| 3      | Rechenkern: CoilParameterService         | 🔲 Offen    |
| 4      | MutualInductanceService                  | 🔲 Offen    |
| 5      | GUI-Entkopplung                          | 🔲 Offen    |

---

## Commit-Konventionen

```
refactor: extract coil parameter calculation into domain service
test:     add golden cases for mutual inductance windows
docs:     add system architecture and calculation pipeline
feat:     add ODE sensor model to domain layer
fix:      correct sign convention in mutual inductance summation
```

---

## Lizenz

MIT License – siehe [LICENSE](LICENSE) (noch anzulegen)
