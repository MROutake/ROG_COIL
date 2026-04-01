# Systemarchitektur – PCB Rogowski Tool

## Überblick

Das PCB Rogowski Tool ist eine Desktop-Anwendung zur analytischen Charakterisierung
von PCB-basierten Rogowski-Spulen. Es besteht aus fünf klar getrennten Schichten.

## Schichtenarchitektur

```
┌─────────────────────────────────────────────────────────────────┐
│  Presentation Layer (ui/)                                        │
│  GUI, Formulare, Tabellen, Diagramme, ViewModels                │
│  Regel: Keine Fachformeln in UI-Klassen                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ruft Use Cases auf
┌──────────────────────────▼──────────────────────────────────────┐
│  Application Layer (app/)                                        │
│  Use Cases, Services, DTOs                                       │
│  Orchestrierung, Laden/Speichern, Triggern von Berechnungen     │
└──────────────┬───────────────────────────┬──────────────────────┘
               │ delegiert an              │ delegiert an
┌──────────────▼──────────────┐  ┌─────────▼────────────────────┐
│  Domain Layer (domain/)      │  │  Infrastructure Layer         │
│  Fachmodelle, Formeln        │  │  (infrastructure/)            │
│  Validierung, Trace          │  │  ODB-Parser, YAML/JSON,       │
│  Keine Abhängigkeiten nach   │  │  Logging, Exportfunktionen   │
│  außen (Pure Python)         │  │                              │
└─────────────────────────────┘  └──────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Agent/Automation Layer (agents/)                                │
│  KI-gestützte Prompts, Workflows, Checklisten                   │
└─────────────────────────────────────────────────────────────────┘
```

## Datenfluss

```
ODB++-Datei
    │
    ▼ OdbBoardLoader (infrastructure/odb)
Board-Domainobjekt
    │
    ▼ Manuelle Klassifikation im UI
TraceLayout (domain/trace)
    │
    ├──▶ CoilParameterService (domain/coil) ──▶ CoilParameters + CalculationTrace
    │
    └──▶ MutualInductanceService (domain/mutual) ──▶ MutualInductanceResult + CalculationTrace
              │
              ▼
        CalculationReportExporter (infrastructure/exporters)
              │
              ▼
        JSON / Markdown Bericht
```

## Modulübersicht

| Modul                        | Verantwortlichkeit                              |
|------------------------------|-------------------------------------------------|
| `domain/board`               | Board, Layer, LineFeature, PadFeature           |
| `domain/trace`               | TraceClassification, ViaWindow, TraceLayout     |
| `domain/coil`                | CoilParameters, Induktivitätsformeln            |
| `domain/mutual`              | MutualInductanceResult, M-Berechnung            |
| `domain/ode`                 | Dynamisches Sensor-ODE-Modell                   |
| `domain/stackup`             | Stackup, MaterialSet                            |
| `domain/common`              | CalculationTrace, TraceStep, QualityStatus      |
| `infrastructure/odb`         | ODB++-Parser → Board-Mapping                   |
| `infrastructure/persistence` | YAML/JSON Speichern/Laden                       |
| `infrastructure/logging`     | Logging-Konfiguration                           |
| `infrastructure/exporters`   | Bericht-Export JSON/Markdown                    |
| `app/use_cases`              | LoadBoardProject, CalculateCoilParameters, ...  |
| `app/dto`                    | Request/Response-Objekte für Use Cases          |
| `ui/viewmodels`              | Aufbereitete Daten für GUI-Anzeige              |
| `ui/desktop`                 | Qt-basierte Desktop-Oberfläche                  |
| `agents/prompts`             | Agenten-Prompts für GitHub Copilot              |

## Architekturregeln

1. **Keine Fachlogik in der GUI** – UI darf nur Eingaben erfassen und Ergebnisse darstellen
2. **Ergebnisobjekte statt rohe Floats** – Jede Berechnung liefert typisierte Objekte
3. **Determinismus** – Gleiche Inputs → immer gleiche Outputs
4. **Keine GUI-Zugriffe in Domain** – Domain-Services sind reine Python-Klassen
5. **Konfiguration statt Magic Numbers** – Alle Konstanten aus YAML-Configs
6. **Traceability** – Jede Berechnung protokolliert ihre Schritte und Eingaben
