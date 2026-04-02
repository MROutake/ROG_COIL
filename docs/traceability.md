# Traceability-Konzept

## Ziel

Jede fachlich relevante Berechnung soll vollständig nachvollziehbar sein:
- Welche Eingabewerte wurden verwendet?
- Welche Formel wurde angewendet?
- Was sind die Zwischenschritte?
- Gibt es Warnungen oder Qualitätseinschränkungen?
- Welche Software-Version und welcher Commit wurden verwendet?

## Struktur

```python
@dataclass(frozen=True)
class TraceStep:
    name: str               # z. B. "Berechne L_track"
    formula: str            # z. B. "L = µ₀·N²·A/l"
    inputs: dict[str, float]
    output: float
    unit: str
    note: str | None = None

@dataclass(frozen=True)
class CalculationTrace:
    calculation_name: str
    steps: tuple[TraceStep, ...]
    warnings: tuple[str, ...]
    quality_status: QualityStatus
    source_files: tuple[str, ...]
    config_versions: dict[str, str]
    timestamp: str
    software_version: str
    git_commit: str
```

## Anwendungsbeispiel

```python
trace = CalculationTrace(
    calculation_name="CoilParameters",
    steps=(
        TraceStep(
            name="Berechne L_track",
            formula="L = µ₀·N²·(w·h)/l",
            inputs={"N": 40, "w_mm": 5.0, "h_mm": 1.6, "l_mm": 200.0},
            output=0.850,
            unit="µH",
            note="Näherungsformel nach [1]"
        ),
    ),
    warnings=(),
    quality_status=QualityStatus.OK,
    source_files=("COIL_Copper_Signal_Top.gbr", "COIL_PTH_Drill.gbr"),
    config_versions={"geometry": "1.0", "materials": "1.0"},
    timestamp="2026-04-01T10:00:00",
    software_version="0.1.0",
    git_commit="abc1234",
)
```

## Export-Formate

| Format   | Methode              | Verwendungszweck                        |
|----------|----------------------|-----------------------------------------|
| JSON     | `trace.to_json()`    | Maschinell verarbeitbar, archivierbar   |
| Markdown | `trace.to_markdown()`| Lesbar, für Berichte                    |
| (PDF)    | zukünftig            | Formaler Prüfbericht                    |

## Wann wird ein Trace erstellt?

Für jede Berechnung, die:
- Physikalische Formeln auswertet
- Konfigurationswerte verwendet
- Ergebnisse produziert, die in Berichten erscheinen sollen
- Validierungsregeln prüft

## Qualitätsstatus-Regeln

| Status    | Bedingung                                              |
|-----------|--------------------------------------------------------|
| `OK`      | Alle Eingaben im gültigen Bereich, keine Warnungen     |
| `WARNING` | Eingaben außerhalb Empfehlungsbereich, Ergebnis gültig |
| `ERROR`   | Berechnung nicht möglich (fehlende Daten, Division/0)  |
