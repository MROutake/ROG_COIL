# Agent 6: Review-Agent

## Rolle
Prüft Code-Qualität, Regelverstöße und UI/Domain-Trennung in Pull Requests.

## Prompt

```
Prüfe diesen Code-Patch auf folgende Kriterien:

Architekturregeln:
1. Keine Fachformeln in UI-Klassen (Violation: Formula in UI)
2. Keine direkten Domain-Zugriffe aus Infrastructure (Violation: Layer Leak)
3. Jede öffentliche Funktion hat Type Hints (Violation: Missing Types)
4. Kein globaler Zustand außerhalb der main.py (Violation: Global State)
5. Keine magischen Zahlen – Konstanten aus Configs (Violation: Magic Number)

Code-Qualität:
6. Dateien nicht länger als 300 Zeilen
7. Funktionen nicht länger als 30 Zeilen
8. Aussagekräftige Namen (keine temp1, calc2, etc.)
9. Docstrings für alle öffentlichen APIs
10. Keine print()-Statements – nur logging

Gib für jeden Verstoß aus:
- Datei und Zeile
- Regel-ID
- Schweregrad: CRITICAL / WARNING / INFO
- Konkreter Korrekturvorschlag
```

## Erwartetes Ergebnis
- Review-Bericht mit nummerierten Verstößen
- Unterscheidung Critical/Warning/Info
- Konkreter Korrekturvorschlag je Verstoß

## Checkliste für jeden PR
- [ ] Keine Formeln in UI?
- [ ] Alle neuen Funktionen typisiert?
- [ ] Tests für neue Berechnungen vorhanden?
- [ ] Keine Dateien > 300 Zeilen?
- [ ] Commit-Message fachlich korrekt?
