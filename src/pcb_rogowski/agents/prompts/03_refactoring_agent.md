# Agent 3: Refactoring-Agent

## Rolle
Extrahiert Fachlogik aus der GUI, führt Separation of Concerns durch.

## Prompt

```
Refaktoriere den vorhandenen Code so, dass die Berechnungslogik vollständig
aus der GUI extrahiert wird.

Regeln:
- Keine Formeln in UI-Klassen
- Jede Berechnung bekommt typisierte Input- und Output-Modelle
- Ergebnisobjekte müssen Rechen-Trace und Warnungen unterstützen
- Bestehendes Verhalten fachlich erhalten
- Große Dateien in kleinere Module aufteilen

Arbeite in kleinen sicheren Schritten:
1. Identifiziere UI-nahe Fachlogik
2. Extrahiere Domain-Services
3. Extrahiere Use Cases
4. Ersetze direkte Zugriffe durch Schnittstellen
5. Schlage passende Tests vor

Gib für jeden Schritt den konkreten Code-Änderungsvorschlag an.
```

## Erwartetes Ergebnis
- Kleinere Module mit klaren Verantwortlichkeiten
- Klarere Abhängigkeiten
- Bessere Testbarkeit

## Checkliste
- [ ] Alle Formeln aus UI entfernt?
- [ ] Domain-Services typisiert?
- [ ] DTOs für alle Schnittstellen definiert?
- [ ] Keine direkten UI-Zugriffe in Domain?
- [ ] Tests für extrahierte Logik vorhanden?

## Priorisierung
1. `viewer.py` – größte Datei, höchste Komplexität
2. Tab-Klassen – GUI/Logic-Vermischung
3. Berechnungsfunktionen – in Domain-Services überführen
