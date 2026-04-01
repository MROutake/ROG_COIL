# Domänenmodell – PCB Rogowski Tool

## Kernobjekte

### Board

Vollständiges PCB-Modell nach ODB++-Import.

| Attribut      | Typ              | Beschreibung                          |
|---------------|------------------|---------------------------------------|
| `name`        | `str`            | Projektname aus ODB++                 |
| `layers`      | `list[Layer]`    | Alle Lagen                            |
| `outline_mm`  | `tuple` optional | Board-Außenmaße                       |
| `source_file` | `str`            | Ursprungsdatei                        |

### Layer

Eine einzelne PCB-Lage mit ihren Features.

| Attribut     | Typ                 | Beschreibung             |
|--------------|---------------------|--------------------------|
| `name`       | `str`               | Lagenbezeichner          |
| `layer_type` | `LayerType`         | COPPER, SILKSCREEN, ...  |
| `index`      | `int`               | Stackup-Position         |
| `lines`      | `list[LineFeature]` | Leiterbahnen             |
| `pads`       | `list[PadFeature]`  | Pads und Vias            |

### TraceClassification

Klassifikation eines einzelnen Leiterbahn-Segments.

| Attribut     | Typ          | Beschreibung                        |
|--------------|--------------|-------------------------------------|
| `feature_id` | `str`        | Referenz auf LineFeature            |
| `role`       | `TraceRole`  | WINDING / CONNECTION / RETURN       |
| `sigma`      | `int`        | Orientierungsvorzeichen ±1          |
| `window_id`  | `str | None` | Zugehöriges Via-Fenster             |

### ViaWindow

Rechteckiges Integrationsgebiet für M-Berechnung.

| Attribut               | Typ   | Beschreibung                  |
|------------------------|-------|-------------------------------|
| `window_id`            | `str` | Eindeutiger Bezeichner        |
| `x/y_min/max_mm`       | `float` | Eckpunkte in mm             |
| `sigma`                | `int` | Vorzeichen für Summation      |

### CoilParameters *(frozen dataclass)*

| Attribut          | Einheit | Beschreibung                    |
|-------------------|---------|---------------------------------|
| `l_track_uH`      | µH      | Induktivität Spurleiter         |
| `l_vias_uH`       | µH      | Induktivität Vias               |
| `l_trace_uH`      | µH      | Gesamtinduktivität Leiter       |
| `l_total_uH`      | µH      | Gesamtinduktivität Spule        |
| `r_series_ohm`    | Ω       | Serienwiderstand                |
| `c_series_pF`     | pF      | Serienkapazität                 |
| `resonance_mhz`   | MHz     | Eigenresonanzfrequenz           |
| `trace`           | —       | Rechen-Protokoll                |

### CalculationTrace *(frozen dataclass)*

| Attribut            | Typ                  | Beschreibung                        |
|---------------------|----------------------|-------------------------------------|
| `calculation_name`  | `str`                | Name der Berechnung                 |
| `steps`             | `tuple[TraceStep]`   | Einzelne Rechenschritte             |
| `warnings`          | `tuple[str]`         | Warnungen                           |
| `quality_status`    | `QualityStatus`      | OK / WARNING / ERROR                |
| `source_files`      | `tuple[str]`         | Eingabedateien                      |
| `config_versions`   | `dict[str, str]`     | Verwendete Konfig-Versionen         |

## Enumerationen

| Enum         | Werte                              |
|--------------|------------------------------------|
| `TraceRole`  | WINDING, CONNECTION, RETURN        |
| `LayerType`  | COPPER, DRILL, SILKSCREEN, ...     |
| `QualityStatus` | OK, WARNING, ERROR              |
