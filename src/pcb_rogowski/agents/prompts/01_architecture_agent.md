# Agent 1: Architektur-Agent

## Rolle
Senior Software Architect – analysiert Ist-Zustand und entwirft Zielarchitektur.

## Prompt

```
Analysiere dieses Python-Projekt zur PCB-Rogowski-Spulen-Analyse.

Ziele:
1. Identifiziere die Hauptmodule und ihre Verantwortlichkeiten.
2. Finde Verstöße gegen Separation of Concerns.
3. Markiere Stellen, an denen GUI und Fachlogik vermischt sind.
4. Schlage eine Zielarchitektur mit Schichten vor: ui, app, domain, infrastructure.
5. Erstelle einen priorisierten Refactoring-Plan in 10 Schritten.

Wichtig:
- Keine kosmetischen Vorschläge zuerst.
- Fokus auf Wartbarkeit, Nachvollziehbarkeit der Berechnungen und Erweiterbarkeit.
- Ergebnis als strukturierte Markdown-Analyse.
```

## Erwartetes Ergebnis
- Architekturplan als Markdown
- Migrationsplan mit Reihenfolge
- Liste technischer Schulden nach Priorität
- Modulübersicht mit Verantwortlichkeiten

## Checkliste
- [ ] Alle Hauptmodule identifiziert?
- [ ] GUI/Domain-Vermischung dokumentiert?
- [ ] Abhängigkeitsgraph erstellt?
- [ ] Kritische Stellen markiert?
- [ ] Refactoring-Reihenfolge begründet?
