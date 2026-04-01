# ADR-001: Schichtenarchitektur für PCB Rogowski Tool

**Datum:** 2026-04-01
**Status:** Angenommen
**Entscheider:** Projektteam

## Kontext

Das Projekt war als Diplomarbeits-Prototyp entstanden. GUI, Fachlogik und
Datenzugriff waren eng gekoppelt. Für Wartbarkeit, Testbarkeit und
Erweiterbarkeit ist eine klare Strukturierung notwendig.

## Entscheidung

Das Projekt wird nach einer 4-Schichten-Architektur strukturiert:

1. **Presentation Layer** (`ui/`) – nur Darstellung und Eingabe
2. **Application Layer** (`app/`) – Use Cases, Orchestrierung
3. **Domain Layer** (`domain/`) – Fachlogik, reine Python-Objekte
4. **Infrastructure Layer** (`infrastructure/`) – IO, Persistenz, Logging

## Begründung

- Domain-Layer ist vollständig testbar ohne UI oder Datei-IO
- Neue Berechnungsmodule können ohne Umbau der UI ergänzt werden
- Trennung erlaubt unabhängige Weiterentwicklung jeder Schicht
- Entspricht Standardmuster (Clean Architecture, Hexagonal Architecture)

## Konsequenzen

- Positive: hohe Testbarkeit, modulare Erweiterbarkeit, klare Abhängigkeiten
- Negative: mehr Dateien, mehr Abstraktionen, initiale Lernkurve
- Neutrale: Strangler-Pattern für Migration – kein Big Bang

## Alternativen verworfen

- **MVC ohne Schichten**: zu flach, Domain und UI vermischen sich schnell
- **Vollständiger Neubau**: zu riskant, fachliches Wissen geht verloren
