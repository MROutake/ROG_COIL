# Agent 4: Test-Agent

## Rolle
Erstellt Teststrategie, Unit-Tests, Golden Cases und Regressionstests.

## Prompt

```
Erstelle eine Teststrategie für dieses Projekt.

Berücksichtige:
- analytische Formeln für L_track, L_vias, L_trace, L_s, R_s, C_s, f_R
- Mutual-Inductance-Berechnung je Via-Fenster
- ODB-Parsing auf Basis kleiner Fixture-Dateien
- Validierungsregeln für Via-Fenster und Klassifikationen
- Regressionstests für bestehende Beispielprojekte

Liefere:
1. Test-Matrix (welche Formeln werden getestet?)
2. Verzeichnisstruktur für Tests
3. Beispieltests in pytest
4. Vorschlag für Golden Cases (Referenzfälle mit Sollwerten)
```

## Erwartetes Ergebnis
- Vollständige Test-Matrix
- pytest-konforme Testdateien
- Mindestens 5 Golden Cases mit dokumentierten Sollwerten
- Regressions-Fixture-Struktur

## Checkliste
- [ ] Jede Formel hat mindestens einen Unit-Test?
- [ ] Grenzfälle abgedeckt (N=1 Windung, sehr kleine Geometrien)?
- [ ] Golden Cases mit Quellenangaben?
- [ ] ODB-Parser mit Minimal-Fixture getestet?
- [ ] Validierungsregeln getestet?

## Test-Kategorien
| Kategorie     | Ort                    | Zweck                              |
|---------------|------------------------|------------------------------------|
| Unit          | tests/unit/            | Einzelne Formeln und Funktionen    |
| Integration   | tests/integration/     | ODB → Board → Berechnung           |
| Regression    | tests/regression/      | Schutz vor Refactoring-Fehlern     |
| Golden Cases  | tests/golden_cases/    | Referenzfälle mit Sollwerten       |
