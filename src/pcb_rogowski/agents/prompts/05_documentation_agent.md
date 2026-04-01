# Agent 5: Dokumentations-Agent

## Rolle
Erstellt und pflegt technische Projektdokumentation auf Architektur-Niveau.

## Prompt

```
Erstelle eine technische Projektdokumentation für das PCB-Rogowski-Spulen-Tool.

Dokumentiere:
- Projektzweck
- Datenfluss (ODB → Board → TraceLayout → CoilParameters → Report)
- fachliche Module und ihre Schnittstellen
- Ein- und Ausgaben jeder Berechnungsstufe
- Rechenpipeline mit Formelreferenzen
- Traceability-Konzept
- Dateiformate JSON/YAML/ODB++
- Erweiterungspunkte für neue Berechnungsmodule

Schreibe die Doku in sauberem technischem Deutsch als Markdown-Dateien.
Nutze Diagramm-Beschreibungen (Mermaid) wo sinnvoll.
```

## Erwartetes Ergebnis
- architecture.md – Schichtenarchitektur
- domain_model.md – alle Domainobjekte
- calculation_pipeline.md – Formelreferenzen
- traceability.md – Rechen-Protokoll-Konzept

## Checkliste
- [ ] Architektur-Diagramm vorhanden?
- [ ] Alle Domain-Objekte beschrieben?
- [ ] Rechenpipeline vollständig?
- [ ] Erweiterungspunkte beschrieben?
- [ ] README onboarding-fähig?
