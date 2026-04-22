# PCB Rogowski Coil Analysis Tool

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#lizenz)
[![Status](https://img.shields.io/badge/status-alpha-orange)]()

Wissenschaftliches Analyse- und Designwerkzeug für **PCB-basierte
Rogowski-Spulen**. Das Tool nimmt eine Gerber-/ODB-Eingabe eines Boards
entgegen, klassifiziert die Leiterbahn-Segmente elektrisch (Wicklung /
Rückleiter / Verbindung) und berechnet das vollständige RLC-Ersatz­
schaltbild inklusive Gegeninduktivität $M$ zum Primärleiter. Die
Ergebnisse werden in einer vierstufigen Desktop-GUI (PyQt6) sowie als
CLI-Skripte angeboten und sind gegen Bode100-Messungen validierbar.

> **Ziel:** Ein *reproduzierbarer, quellenbasierter* Workflow vom
> PCB-Layout bis zum Übertragungsverhalten $H(j\omega)=V_{out}/I_{prim}$.

---

## Inhalt

1. [Features](#features)
2. [Schnelleinstieg](#schnelleinstieg)
3. [GUI-Workflow (Tabs 1 – 4)](#gui-workflow)
4. [CLI-Skripte](#cli-skripte)
5. [Projektstruktur](#projektstruktur)
6. [Physikalisches Modell](#physikalisches-modell)
7. [Entwicklung & Mitwirken](#entwicklung--mitwirken)
8. [Literatur](#literatur)
9. [Lizenz](#lizenz)

---

## Features

- **Import**: Gerber (RS-274X) via `gerbonara`, optional ODB++.
- **Klassifikation**: Interaktive Zuordnung `winding / return / connection`
  plus Orientierung $\sigma\in\{-1,0,+1\}$; Batch-Modi (Rolle-zuweisen,
  Sigma-Flip, Via-zu-Fenster).
- **Induktivität $L$**: Ruehli/Lorenz-Formel pro Segment, Via-Beitrag,
  optional PEEC-Kreuzterme.
- **Widerstand $R$**: DC-Anteil $\rho\ell/A$ plus Skin-/Proximity-
  Modifikator.
- **Kapazität $C$**: geometrische Näherungen pro Lagenstack
  (Parallel­platten + Kantenstreu­anteile).
- **Gegeninduktivität $M$**: drei Methoden — analytisch, Flächenintegral
  ("field_integral", empfohlen), numerisches Linienintegral.
- **Übertragungsfunktion**: $H(j\omega)=j\omega M / (1-\omega^2 LC+j\omega RC)$
  und Klemmenimpedanz $Z(j\omega)$, beides live als Bode-Plot.
- **Bode100-Fit**: Vergleich Modell ↔ Messung im Output-Tab.
- **Visualisierung**: Ersatzschaltbild, Windungsfenster, B-Feld-Schnitt
  mit role-colorierter Leiterbahn-Overlay.

## Schnelleinstieg

### Voraussetzungen

- Python **3.11+** (3.12 getestet)
- Windows, Linux oder macOS
- ~500 MB Plattenplatz (inkl. Bibliotheken)

### Installation

```powershell
git clone <repo-url> ROG_COIL_Auswrtung
cd ROG_COIL_Auswrtung

# 1) Virtuelle Umgebung anlegen
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate            # Linux / macOS

# 2) Paket editierbar installieren (inkl. Entwicklertools)
pip install -e ".[dev]"
```

### Start

```powershell
# Desktop-GUI
pcb-rogowski-gui

# CLI (Hilfe anzeigen)
pcb-rogowski --help
```

### Beispieldaten

Unter [data_samples/gerber/](data_samples/gerber/) liegen drei
PCB-Designs (`Design_01`, `Design_02`, `Design_03`) mit zugehörigen
Bode100-Referenzmessungen in [data_samples/Bode100/](data_samples/Bode100/).

---

## GUI-Workflow

Die Desktop-GUI führt den Anwender in vier Tabs sequenziell durch den
Analyseprozess:

| Tab | Aufgabe | Kern-Artefakt |
|-----|---------|---------------|
| **1 — Design**         | Gerber-Ordner + optionale YAMLs auswählen   | `DesignInputs`           |
| **2 — Klassifikation** | Segmente & Vias interaktiv klassifizieren   | `ClassificationSpec`, `windows_*.yaml` |
| **3 — Analyse**        | Berechnung $L,R,C,M$ + Plots                | `AnalysisResult`         |
| **4 — Output**         | Report, Bode-Vergleich, Export              | CSV / PNG                |

### Tab 2 – Klassifikation

- **Modi**: `Leiter` (Segmente) ↔ `Vias` (Fenster-Definition).
- **Interaktion**: `Navigate` (Pan/Zoom) ↔ `Select` (Klick); erforderlich,
  damit Matplotlib-Werkzeuge nicht mit der Selektion kollidieren.
- Rollen‐Farbcodierung: <span style="color:#00e676">Wicklung (winding)</span>,
  <span style="color:#ef5350">Rückleiter (return)</span>,
  <span style="color:#546e7a">Verbindung</span>,
  <span style="color:#8a5cf6">unklassifiziert (violett gestrichelt)</span>.
- Fenster werden durch **zwei Via-Klicks** (A → B) angelegt; das Vorzeichen
  $\sigma$ ist toggelbar (Default $+1$).

### Tab 3 – Analyse

Vier Sub-Plots:

1. **Ersatzschaltbild** — schematisch mit eingetragenen Werten.
2. **Windungsfenster** — maßstäbliches Rechteck ($h_{via}\times\ell$).
3. **B-Feld XY** — 2D-Magnetfeld (Heatmap $\log_{10}|B|$ + geschlossene
   Feldlinien aus $A_z$-Isolinien). Leiterbahn-Overlay und Fenster‐
   Overlay sind per Checkbox zuschaltbar.
4. **Übertragungsfunktion** — Bode-Diagramm, umschaltbar zwischen
   - $H(j\omega) = V_{out}/I_{prim}$ (Rogowski-Ausgang, Einheit Ω),
   - $Z(j\omega)$ (Klemmenimpedanz; direkt vergleichbar mit Bode100-Fit).

Darunter der **Rechenschritt-Trace** (`CalculationTraceView`): jeder
Zwischenschritt wird mit Formel (read-only), Eingabegrößen und
Zahlenwert angezeigt. Die Formeln stammen aus der zentralen Registry
([src/pcb_rogowski/domain/formulas.py](src/pcb_rogowski/domain/formulas.py)) —
siehe Abschnitt *Formel-Registry* weiter unten.

---

## CLI-Skripte

Die *Entwicklerskripte* unter [scripts/](scripts/) bilden die GUI-Schritte
reproduzierbar ab (z. B. für Batch-Läufe):

| Skript | Zweck |
|--------|-------|
| [load_gerber.py](scripts/load_gerber.py)     | Gerber-Ordner → `Board`-Objekt |
| [classify_board.py](scripts/classify_board.py)  | Interaktives Matplotlib-Pendant zu Tab 2 |
| [define_windows.py](scripts/define_windows.py)  | Via-Fenster-Editor |
| [calculate_coil.py](scripts/calculate_coil.py)    | $L,R,C$ ohne GUI berechnen |
| [calculate_mutual.py](scripts/calculate_mutual.py) | Gegeninduktivität $M$ |
| [fit_bode100.py](scripts/fit_bode100.py)       | Messungs-Fit gegen Modell |
| [compare_designs.py](scripts/compare_designs.py)  | Mehrere Designs nebeneinander plotten |
| [visualize_board.py](scripts/visualize_board.py)  | Debug-Plot der importierten Geometrie |

Alle Skripte folgen dem Muster `python scripts/<name>.py --help`.

---

## Projektstruktur

```
src/pcb_rogowski/
├── main.py                # Einstiegspunkte: main() (CLI), main_gui() (Qt)
├── agents/                # Experimentelle LLM-gestützte Auto-Klassifikation
├── app/                   # Use-Cases (Ablaufsteuerung, keine Logik)
│   └── use_cases/analyze_design.py
├── domain/                # Reine Fachlogik – KEINE UI-/IO-Abhängigkeiten
│   ├── board/             #   Board, Layer, LineFeature, Pad
│   ├── trace/             #   Klassifikation, Topologie-Reparatur
│   ├── coil/              #   Induktivität, Widerstand, Kapazität, TF
│   ├── mutual/            #   M-Berechnung (3 Methoden)
│   └── ...
├── infrastructure/        # IO-Adapter: Gerber, ODB, YAML, Bode100 CSV
└── ui/desktop/            # PyQt6-GUI (Tabs, geteilte Canvases, Theme)
```

Die Architektur folgt dem Prinzip **Domain → Application → Interface**
(Ports & Adapters). Details siehe [docs/architecture.md](docs/architecture.md)
und die Architekturentscheidungen unter [docs/adr/](docs/adr/).

---

## Physikalisches Modell

Alle Formeln sind ausführlich in [docs/berechnungen.md](docs/berechnungen.md)
dokumentiert. Kurzübersicht:

**Ersatzschaltbild (LRC + M)**
$$
Z(s)=\frac{R+sL}{1+sRC+s^2LC},\qquad
H(s)=\frac{V_{out}(s)}{I_{prim}(s)}=\frac{sM}{1+sRC+s^2LC}
$$

**Eigeninduktivität (Ruehli/Lorenz)**
$$
L_{\mathrm{self},i}=\frac{\mu_0\,l_i}{2\pi}
\left[\ln\!\frac{2l_i}{W+T}+0{,}5+0{,}2235\,\frac{W+T}{l_i}\right]
$$

**Gegeninduktivität (Flächenintegral)**
$$
M=\frac{1}{I_{prim}}\int_{A_{win}}\mathbf{B}(\mathbf{r})\cdot\mathrm{d}\mathbf{A}
$$

**Resonanzfrequenz**
$$
f_{res}=\frac{1}{2\pi\sqrt{LC}}
$$

Referenzen zu den einzelnen Formeln sind jeweils im zugehörigen
Python-Modul (Docstring) sowie in [docs/berechnungen.md](docs/berechnungen.md)
aufgeführt.

---

## Formel-Registry — zentrale Anpassung aller Formeln

**Alle** in der Berechnung verwendeten Formeln werden an genau einer
Stelle deklariert:

> [`src/pcb_rogowski/domain/formulas.py`](src/pcb_rogowski/domain/formulas.py)

### Warum eine zentrale Datei?

* Formeln in GUI, Reports und JSON-Traces sind *konsistent* — alle
  lesen aus derselben Quelle.
* Änderungen müssen nur an **einem** Ort gemacht (und dokumentiert)
  werden.
* Konsistenztests (siehe unten) verhindern, dass freie Formel-Strings
  schleichend wieder im Rechenkern landen.

### Aufbau

Jeder Eintrag ist ein unveränderliches `Formula`-Objekt:

```python
Formula(
    key="L_track_self_segment",
    latex="L_self,i = µ₀·l_i/(2π)·[ln(2·l_i/(w+t)) + 0.5 + 0.2235·(w+t)/l_i]",
    description="Freiraum-Selbstinduktivität nach Ruehli/Lorenz …",
    variables={"l_i": "Segmentlänge [m]", "w": "Leiterbreite [m]", ...},
    unit="µH",
    reference="Ruehli 1972; docs/berechnungen.md §L_track",
)
```

Die Felder im Einzelnen:

| Feld          | Bedeutung |
|---------------|-----------|
| `key`         | Stabiler Bezeichner (wird aus dem Rechenkern per `FORMULAS["<key>"]` aufgelöst — **nie umbenennen** ohne Code-Update). |
| `latex`       | Unicode-Darstellung; wird von `FormulaBox` in matplotlib-MathText gerendert. Mehrzeilig erlaubt. |
| `description` | Fachlich-physikalische Erläuterung inkl. Modellannahmen. |
| `variables`   | Variablen-Glossar `{symbol → Bedeutung [Einheit]}`. |
| `unit`        | Einheit der linken Seite (= `TraceStep.unit`). |
| `reference`   | Literaturverweis oder Abschnitt in [docs/berechnungen.md](docs/berechnungen.md). |

### Wie passe ich eine Formel an?

1. **Anzeige ändern** (nur Text/LaTeX): Feld `latex` in `formulas.py`
   anpassen. Beim nächsten GUI-Start erscheint der neue String überall.
2. **Physik ändern**: zusätzlich die Python-Implementierung in
   - [`src/pcb_rogowski/domain/coil/service.py`](src/pcb_rogowski/domain/coil/service.py)
     (für $L, R, C, f_{res}$) bzw.
   - [`src/pcb_rogowski/domain/mutual/calculator.py`](src/pcb_rogowski/domain/mutual/calculator.py)
     (für $M$)
   synchron anpassen. Die Registry beschreibt die Formel — sie führt
   sie **nicht** aus; Rechenlogik und LaTeX-Anzeige müssen selbst
   konsistent gehalten werden (die unten genannten Tests decken die
   wichtigsten Regressionen ab).
3. Falls die Herleitung relevant geändert wurde: Abschnitt in
   [docs/berechnungen.md](docs/berechnungen.md) aktualisieren und im
   Feld `reference` der Formel verlinken.
4. Beim **Umbenennen** eines `key` alle Call-Sites anpassen — das
   Konsistenz-Test fängt einseitige Umbenennungen auf.

### Neue Formel hinzufügen

1. Neuen `_add(Formula(...))`-Block ans Ende der passenden Sektion in
   [formulas.py](src/pcb_rogowski/domain/formulas.py) anhängen.
2. Im Rechenkern `FORMULAS["<neuer_key>"].latex` beim Aufbau des
   zugehörigen `TraceStep` verwenden — **nicht** den Formelstring frei
   tippen.
3. `pytest tests/unit/test_formula_registry.py` ausführen.

### Konsistenz-Tests

Unter [tests/unit/test_formula_registry.py](tests/unit/test_formula_registry.py)
prüfen vier Tests automatisch:

| Test | prüft |
|------|-------|
| `test_registry_is_nonempty`                          | Registry nicht leer |
| `test_every_formula_has_required_fields`             | Alle Felder gefüllt, Keys konsistent |
| `test_no_missing_or_unused_keys`                     | Jeder im Code referenzierte Key ist deklariert; keine verwaisten Einträge |
| `test_no_inline_formula_strings_in_calc_files`       | Kein `formula="…"`-Literal im Rechenkern außerhalb von `FORMULAS[...]` |

Damit ist garantiert, dass *alle* verwendeten Formeln tatsächlich in
`formulas.py` stehen und zentral geprüft bzw. angepasst werden können.

### Programmatischer Zugriff

```python
from pcb_rogowski.domain.formulas import FORMULAS, latex, check_coverage

print(latex("L_vias"))          # -> "L_vias = n · µ₀·h / (2π) · (1 + ln(4h/d))"
print(FORMULAS["L_vias"].reference)

# z. B. in einem Report: Tabelle aller Formeln exportieren
for f in FORMULAS.values():
    print(f.key, "|", f.unit, "|", f.reference)
```

---

## Entwicklung & Mitwirken

Bitte [CONTRIBUTING.md](CONTRIBUTING.md) lesen. Kurzfassung:

```powershell
pip install -e ".[dev]"
pre-commit install
ruff check src scripts tests
black --check src scripts tests
pytest
```

Codestil: `ruff` + `black` (120 Zeichen), Typ-Annotationen verpflichtend
(`mypy --strict` für `domain/`), Docstrings im NumPy-Stil.

---

## Literatur

- F. W. Grover, *Inductance Calculations*, Dover, 1946.
- A. E. Ruehli, "Inductance Calculations in a Complex Integrated Circuit
  Environment", *IBM Journal*, 1972.
- V. P. Lorenz, "Self-Inductance of Rectangular Conductors", 1879.
- IEEE Std 1459-2010 (Leistungsgrößen unter nicht-sinusoidalen
  Bedingungen).
- D. A. Ward, J. La T. Exon, "Using Rogowski coils for transient current
  measurements", *Engineering Science and Education Journal*, 1993.

Detaillierte Herleitungen: [docs/berechnungen.md](docs/berechnungen.md).

---

## Lizenz

MIT — siehe Paket-Metadaten in [pyproject.toml](pyproject.toml).
