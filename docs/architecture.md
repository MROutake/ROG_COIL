# Architekturübersicht

Dieses Dokument erläutert die Schichtarchitektur des Pakets
`pcb_rogowski` und zeigt den typischen Datenfluss vom Gerber-Import bis
zum Bode-Plot.

> Die *warum*-Fragen zu einzelnen Entscheidungen sind in den
> Architecture Decision Records unter [docs/adr/](adr/) versioniert.
> Eingangs­punkt:
> [ADR-001 Layered Architecture](adr/ADR-001-layered-architecture.md).

## 1 Schichten

```
┌─────────────────────────────────────────────────────────┐
│  ui.desktop   (PyQt6-Tabs, Matplotlib-Canvases, Theme)  │
│  scripts/     (CLI-Einstiegspunkte)                     │
└───────────────▲─────────────────────────────────────────┘
                │ verwendet
┌───────────────┴─────────────────────────────────────────┐
│  app.use_cases   (Ablaufsteuerung, Worker-Glue)         │
│     ▸ analyze_design()                                  │
└───────────────▲─────────────────────────────────────────┘
                │ verwendet
┌───────────────┴─────────────────────────────────────────┐
│  domain/                                                │
│   ▸ board         (Board, Layer, LineFeature, Pad)      │
│   ▸ trace         (ClassificationSpec, TopologyFiller)  │
│   ▸ coil          (L, R, C, TransferFunction)           │
│   ▸ mutual        (M: analytical / field / numerical)   │
│  Reine Python-Objekte, KEINE Qt-/IO-Abhängigkeit.       │
└───────────────▲─────────────────────────────────────────┘
                │ wird befüllt von
┌───────────────┴─────────────────────────────────────────┐
│  infrastructure/  (Ports & Adapters)                    │
│   ▸ gerber_loader, odb_loader, bode100_reader, yaml_io  │
└─────────────────────────────────────────────────────────┘
```

Leitsatz: **Abhängigkeiten zeigen nur nach innen**. `domain/` importiert
*nichts* aus `infrastructure/`, `app/` oder `ui/`. Damit bleibt die
Fachlogik testbar und austauschbar.

## 2 Datenfluss: `analyze_design`

Der zentrale Use-Case in
[src/pcb_rogowski/app/use_cases/analyze_design.py](../src/pcb_rogowski/app/use_cases/analyze_design.py)
orchestriert den gesamten Berechnungs­pipeline:

```
DesignInputs (YAML-Pfade)
        │
        ▼
┌──────────────────────────┐
│ 1. Gerber-Import         │  infrastructure.gerber_loader
│    → Board               │
├──────────────────────────┤
│ 2. Klassifikation laden  │  domain.trace.classifier
│    → ClassificationSpec  │
│    → TopologyGapFiller   │
├──────────────────────────┤
│ 3. TraceLayout bauen     │  domain.trace.layout
│    (winding/return geordnet)
├──────────────────────────┤
│ 4. Coil-Parameter        │  domain.coil.*
│    L_self, L_via, R, C   │
│    → CoilParameters      │
├──────────────────────────┤
│ 5. Gegeninduktivität M   │  domain.mutual.calculator
│    (Fensterliste)        │
│    → MutualInductanceResult
├──────────────────────────┤
│ 6. Bode100-Fit (optional)│  domain.coil.fitting
│    → FitResult           │
└──────────────────────────┘
        │
        ▼
AnalysisResult  (Eingabe für Tab 3 / Tab 4)
```

Jeder Rechenschritt hängt zusätzlich einen `TraceStep` an die zentrale
`CalculationTrace` – diese ist in der GUI editierbar (FormulaBox) und
wird in `output/formulas_<design>.yaml` persistiert.

## 3 GUI-Komposition

```
MainWindow
├─ Tab 1 DesignTab         →  verwaltet DesignInputs
├─ Tab 2 ClassificationTab →  ClassifyCanvas + ViaWindow-Editor
├─ Tab 3 AnalysisTab       →  SchematicCanvas, WindowGeometryCanvas,
│                              BFieldCanvas, TransferFunctionCanvas
└─ Tab 4 OutputTab         →  Bode-Plot (Modell ↔ Messung), Report
```

Kommunikation zwischen Tabs läuft ausschließlich über
`ProjectState` (Qt-Signals):

- `selection_changed(int)` – aktuelles Design gewechselt.
- `analysis_updated(int)`  – neuer `AnalysisResult` verfügbar.
- `classification_changed` – `ClassificationSpec` modifiziert.

Dadurch bleiben die Tabs entkoppelt und einzeln testbar.

## 4 Erweiterungs­punkte

| Wunsch                          | Erweiterungspunkt                                        |
|---------------------------------|----------------------------------------------------------|
| Neues Import-Format             | Adapter unter `infrastructure/` + Registry in `load_gerber` |
| Alternative M-Methode           | neues Modul in `domain/mutual/`, Registrierung über `method_mutual` |
| Neue Visualisierung             | `MplCanvas`-Subklasse in `ui/desktop/shared/`, Tab einbinden |
| Andere Resonanzmodelle          | zusätzliche `TransferFunction`-Variante in `domain/coil/transfer_function.py` |

## 5 Teststrategie

Die Schichtung wird durch die Teststruktur gespiegelt:

- `tests/unit/domain/*`          → reine Formeln (deterministisch, < 1 s).
- `tests/integration/*`          → Gerber → AnalysisResult mit Beispielboards.
- `tests/golden_cases/*`         → numerische Referenzen (Regression).
- `tests/ui/*`                   → `pytest-qt`, offscreen-Rendering.

Siehe auch [CONTRIBUTING.md](../CONTRIBUTING.md#tests).
