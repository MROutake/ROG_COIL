# Contributing to `pcb-rogowski`

Vielen Dank für Dein Interesse, am PCB-Rogowski-Analyse-Tool mitzuwirken!
Dieses Dokument beschreibt den Workflow, Codestil und die
Qualitätssicherungs­prozesse, damit Änderungen schnell und reviewfähig
eingebracht werden können.

## Entwicklungsumgebung einrichten

```powershell
git clone <repo-url> ROG_COIL_Auswrtung
cd ROG_COIL_Auswrtung

python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate          # Linux / macOS

pip install -e ".[dev]"
pre-commit install
```

## Branching- und Commit-Konventionen

- **Branch-Namen**: `feature/<kurzbeschreibung>`, `fix/<issue-id>`,
  `docs/<thema>`.
- **Commit-Nachrichten**: [Conventional Commits](https://www.conventionalcommits.org/):

  ```
  feat(ui): add transfer-function sub-tab in analysis view
  fix(coil): correct skin-effect coefficient for Cu at 20 °C
  docs(readme): document Bode100 fit workflow
  ```

- Ein Commit = eine logische Änderung. Formatierungscommits bitte separat
  halten (`style: ...`).

## Codestil

| Werkzeug  | Zweck                             | Befehl                                 |
|-----------|-----------------------------------|----------------------------------------|
| `ruff`    | Linting + Import-Sortierung       | `ruff check src scripts tests`         |
| `black`   | Auto-Formatierung (120 Spalten)   | `black src scripts tests`              |
| `mypy`    | Statische Typprüfung              | `mypy src/pcb_rogowski/domain`         |
| `pytest`  | Tests                             | `pytest`                               |
| `pre-commit` | Alle Checks im Git-Hook        | `pre-commit run --all-files`           |

Konkrete Richtlinien:

- **Typ-Annotationen sind Pflicht** für alle öffentlichen Funktionen und
  Methoden (ausgenommen Tests).
- **Docstrings** im NumPy-Stil (Parameters, Returns, Examples). Jede
  öffentliche Klasse + jedes Modul beginnt mit einer Docstring, die
  Zweck, Ein-/Ausgaben und relevante Formeln beschreibt.
- **Physikalische Formeln** bitte sowohl in der Docstring (als LaTeX)
  als auch in `docs/berechnungen.md` referenzieren.
- **Keine Domain-Logik in UI/IO-Modulen.** Die Schichtung
  (Domain → Application → Interface) ist in
  [docs/adr/ADR-001-layered-architecture.md](docs/adr/ADR-001-layered-architecture.md)
  verbindlich festgelegt.
- **SI-Einheiten** in der Domain; Anzeigeeinheiten (µH, pF, nH) nur in
  UI-Adaptern oder expliziten Property-Convertern.

## Tests

- **Unit-Tests** (`tests/unit/`): reine Domänenlogik, keine Dateien.
- **Integrations-Tests** (`tests/integration/`): mit Beispielgerbern.
- **Golden-Cases** (`tests/golden_cases/`): numerisch fixierte
  Referenzergebnisse (Regression).
- **UI-Tests**: `pytest-qt`, `QT_QPA_PLATFORM=offscreen` setzen.

```powershell
$env:QT_QPA_PLATFORM="offscreen"; pytest
pytest --cov=pcb_rogowski --cov-report=term-missing
```

## Pull Requests – Checkliste

- [ ] `pre-commit run --all-files` ist grün.
- [ ] Neue Funktion → neuer Test.
- [ ] Geänderte Formel → `docs/berechnungen.md` aktualisiert.
- [ ] Neues Architekturdetail → ADR unter `docs/adr/ADR-NNN-*.md`.
- [ ] README / CHANGELOG gepflegt, falls Benutzeroberfläche betroffen.

## Architekturentscheidungen (ADR)

Wesentliche Entscheidungen werden als *Architecture Decision Records* im
Verzeichnis [docs/adr/](docs/adr/) abgelegt (MADR-Format). Jede neue ADR
erhält eine fortlaufende Nummer und beschreibt **Kontext, Entscheidung
und Konsequenzen**.

## Fragen?

Bitte öffne ein Issue mit dem Label `question` oder starte eine
Discussion. Für größere Feature-Vorschläge vorab eine ADR-Skizze
einreichen.
