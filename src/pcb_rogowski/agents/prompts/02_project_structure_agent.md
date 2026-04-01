# Agent 2: Projektstruktur-Agent

## Rolle
Generiert professionelle Projektgerüste nach definierten Architekturvorgaben.

## Prompt

```
Erzeuge für dieses Python-Projekt eine professionelle Zielstruktur.

Rahmenbedingungen:
- Source-Code unter src/
- Tests unter tests/
- Docs unter docs/
- Konfigurationen unter configs/
- GUI getrennt von Domain- und Infrastrukturcode
- Python Packaging mit pyproject.toml
- pytest, ruff, black, mypy, pre-commit integrieren

Liefere:
1. vollständige Ordnerstruktur
2. Inhalt für pyproject.toml
3. Inhalt für .pre-commit-config.yaml
4. Vorschlag für erste README-Struktur
5. Migrationshinweise vom Altprojekt zur neuen Struktur
```

## Erwartetes Ergebnis
- Kompletter Projekt-Scaffold
- Standardisierte Entwicklerumgebung
- Alle Konfigurationsdateien lauffähig

## Checkliste
- [ ] pyproject.toml mit allen Dev-Dependencies?
- [ ] pre-commit hooks konfiguriert?
- [ ] Alle __init__.py vorhanden?
- [ ] .gitignore vollständig?
- [ ] README-Grundstruktur erstellt?
