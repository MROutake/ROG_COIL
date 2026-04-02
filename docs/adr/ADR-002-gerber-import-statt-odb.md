# ADR-002: Gerber-Import (gerbonara) statt ODB++

**Datum:** 2026-04-01
**Status:** Angenommen
**Entscheider:** Projektteam

## Kontext

Das Projekt benötigt einen zuverlässigen Weg, PCB-Layout-Daten aus Altium Designer
zu importieren. Ursprünglich war ODB++ als Importformat vorgesehen. Bei der
praktischen Umsetzung stellte sich heraus, dass:

- ODB++ ein proprietäres Archivformat ist, das aufwändiges Custom-Parsing erfordert
- keine geeignete, stabil gewartete Python-Bibliothek für ODB++ existiert
- Gerber (RS-274X / X2) der de-facto Standard für PCB-Fabrikationsexporte ist
  und von Altium Designer vollständig unterstützt wird
- für die physikalische Berechnung (Gegeninduktivität, Segmentierung) primär
  Liniensegmente und Bohrungspositionen benötigt werden – beides liefert Gerber

## Entscheidung

Der Import erfolgt über **Gerber RS-274X / X2** mit der Bibliothek **gerbonara**.

### Erwartete Dateien (Altium-Export)

| Datei                          | Inhalt                       | Verwendung            |
|-------------------------------|------------------------------|-----------------------|
| `*_Copper_Signal_Top.gbr`     | Oberste Kupferlage           | Traces, Pads          |
| `*_Copper_Signal_N.gbr`       | Inner Layer N                | Traces, Pads          |
| `*_Copper_Signal_Bot.gbr`     | Unterste Kupferlage          | Traces, Pads          |
| `*_PTH_Drill.gbr`             | Plattierte Bohrungen (Vias)  | PadFeature is_via     |
| `*_NPTH_Drill.gbr`            | Mechanische Bohrungen        | PadFeature is_via     |
| `*_Profile.gbr`               | Board-Außenkontur            | outline_mm            |
| `*_Soldermask_*.gbr`          | Lötstopplack                 | Anzeige               |
| `*_Legend_*.gbr`              | Silkscreen                   | Anzeige               |
| `*_Mechanical_*.gbr`          | Mechanische Lagen            | Anzeige               |

### Parse-Pipeline

```
Gerber-Verzeichnis
    │
    ▼ _classify_file()          → Lagentyp + Stackup-Index
    ▼ GerberFile.open()         → gerbonara-Objekte
    ▼ parse_lines()             → list[LineFeature]   (Line + Region-Segmente)
    ▼ parse_pads()              → list[PadFeature]    (Flash + Drill-Holes)
    ▼ GerberBoardLoader         → Board-Domainobjekt
```

### gerbonara-Objekte → Domain-Modell

| gerbonara-Typ  | Domain-Typ      | Bemerkung                                 |
|----------------|-----------------|-------------------------------------------|
| `Line`         | `LineFeature`   | Direkte Übernahme, Apertur → width_mm     |
| `Region`       | `LineFeature[]` | Segmentierung der Outline                 |
| `Arc`          | `LineFeature`   | Annäherung als Sehne (Start→End)          |
| `Flash`        | `PadFeature`    | Pads und Vias, Apertur → diameter_mm      |

## Begründung

- **gerbonara** liefert direkt typisierte Objekte (`Line`, `Arc`, `Flash`, `Region`)
  ohne manuelles Tokenisieren des Gerber-Formats
- Gerber ist ein offener Standard (IPC-RS-274X) – keine proprietären Abhängigkeiten
- Das Board-Domainmodell (`Board`, `Layer`, `LineFeature`, `PadFeature`) bleibt
  vollständig unverändert – nur die Infrastructure-Schicht wird ersetzt
- Die Visualisierung, alle Berechnungsmodule und die GUI benötigen
  **keine Anpassungen** (Schichtenarchitektur bewährt sich)

## Konsequenzen

- **Positiv:** stabile, aktiv gewartete Abhängigkeit; direkter Zugriff auf
  Geometrieobjekte; keine Altium-Lizenz für den Import notwendig
- **Positiv:** `GerberBoardLoader` ist vollständig testbar mit echten
  `.gbr`-Dateien aus `data_samples/gerber/`
- **Negativ:** Gerber enthält keine Netzlisten-Information (Connectivity).
  Für spätere Phasen (automatische Trace-Klassifikation) muss ggf. IPC-356
  zusätzlich importiert werden
- **Neutral:** ODB++-bezogener Code (`infrastructure/odb`) kann entfernt werden
  sobald alle Tests auf Gerber migriert sind

## Alternativen verworfen

| Alternative          | Grund für Ablehnung                                          |
|----------------------|--------------------------------------------------------------|
| ODB++ Custom-Parser  | Zu aufwändig, keine stabile Library, proprietäres Format     |
| pygerber             | Liefert AST, keine direkten Geometrieobjekte                 |
| KiCad .kicad_pcb     | Nicht der Ziel-Workflow (Altium Designer)                    |
| IPC-2581             | Noch weniger Tooling-Unterstützung als ODB++                 |
