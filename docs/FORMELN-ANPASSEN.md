# Formeln anpassen — Konsistenz-Workflow

Dieses Dokument beschreibt, **wie du eine Formel in `pcb_rogowski`
ändern kannst, ohne dass Anzeige (GUI/Report) und Berechnung (Python)
auseinanderlaufen**.

Zielgruppe: Entwickler:innen, die Modelle tauschen, Korrekturterme
ergänzen oder Vorzeichen / Faktoren korrigieren wollen.

---

## 1. Zwei-Ebenen-Modell

Jede Formel existiert an **genau zwei** Stellen im Code:

| Ebene         | Ort                                                   | Zweck                                                   |
| ------------- | ----------------------------------------------------- | ------------------------------------------------------- |
| **Anzeige**   | `src/pcb_rogowski/domain/formulas.py` → `FORMULAS`   | LaTeX/Unicode für GUI, Reports, Calculation-Trace       |
| **Physik**    | Python-Methode, referenziert über `Formula.impl`      | Führt die eigentliche numerische Berechnung aus         |

Die beiden Ebenen sind **bewusst entkoppelt**: eine LaTeX-Schönheits­
korrektur soll nicht sofort den Rechenkern triggern. Umgekehrt: wenn
du am Python-Modell schraubst, musst du selbst nachziehen, dass der
Anzeige-String noch stimmt — dafür gibt es die Prüfroutinen unten.

### Warum kein Live-Formel-Editor?
Formeln sind keine Strings, sondern Python-Code mit Einheiten,
Randfallschutz und Gültigkeitsgrenzen. Ein GUI-Editor kann diese
Qualität nicht garantieren. Entscheidung: Python bleibt die Autorität,
Dokumentation hält das Ganze konsistent.

---

## 2. Entscheidungsmatrix

> **Was möchte ich ändern?**

| Situation                                           | Anzeige-Datei | Physik-Datei | Tests neu ausführen |
| --------------------------------------------------- | :-----------: | :----------: | :-----------------: |
| Tippfehler im LaTeX-String                          | ✅            | —            | Registry-Test        |
| Bezeichnung einer Variablen (nur Anzeige)           | ✅            | —            | Registry-Test        |
| Korrekturterm ergänzen (Physik ändert sich)         | ✅            | ✅           | **alle**             |
| Modell komplett tauschen (z.B. Wheeler → Grover)    | ✅            | ✅           | **alle + golden**    |
| Methode umbenennen / verschieben                    | `impl`-Feld  | ✅           | Registry-Test        |
| Neue Formel einführen                               | neuer Eintrag | neue Methode | **alle**             |
| Einheiten-Skalierung korrigieren                    | ggf. ✅      | ✅           | **alle + golden**    |

---

## 3. Schritt-für-Schritt: Physikalische Änderung

Beispiel-Szenario: Du willst `L_vias` vom aktuellen Goldfarb/Pucel-Modell
auf ein Wheeler-Modell umstellen.

### 3.1  Impl-Methode finden

```python
>>> from pcb_rogowski.domain.formulas import FORMULAS, resolve_impl
>>> FORMULAS["L_vias"].impl
'domain.coil.service::CoilParameterServiceImpl._calc_l_vias'
>>> resolve_impl("L_vias")
<function CoilParameterServiceImpl._calc_l_vias at 0x…>
```

Oder direkt im Editor: `Ctrl+Click` im `impl`-String-Literal
(Pylance löst den Pfad auf).

### 3.2  Physik anpassen

1. Die in `impl` referenzierte Methode öffnen.
2. **Body anpassen** (Formel-Implementierung).
3. **Docstring nachziehen** — speziell die Blöcke
   `Physik`, `Annahmen / Gültigkeitsbereich` und `Sanity-Zahl`.
4. Die in `Sanity-Zahl` angegebene Zahl von Hand nachrechnen und
   eintragen (wird von keiner Maschine geprüft, aber beim nächsten
   Lesen wertvoll).

### 3.3  Anzeige anpassen

In `src/pcb_rogowski/domain/formulas.py` den passenden `FORMULAS`-
Eintrag öffnen und `latex`, `description`, `variables`,
`reference` synchron ziehen.

### 3.4  Tests ausführen

```powershell
# Registry-Konsistenz (Keys, Felder, Impl auflösbar)
pytest tests/unit/test_formula_registry.py -v

# Numerische Regression (Golden-Cases für Design 01-03)
pytest tests/golden_cases -v

# Volle Suite (empfohlen bei Physik-Änderungen)
pytest -v
```

### 3.5  GUI-Roundtrip

1. `python -m pcb_rogowski.main` starten.
2. Test-Gerber laden (z.B. `data_samples/gerber/Desgin_03`).
3. Analyse ausführen → Calculation-Trace öffnen.
4. Sichtprüfen: Formel-Box zeigt die neue LaTeX, Ergebnis-Zahl
   entspricht der neuen Sanity-Zahl.

### 3.6  Methode umbenannt?

Wenn du die Python-Funktion umbenannt/verschoben hast, **musst du
das `impl`-Feld in der Registry nachziehen**. Der Registry-Test
fängt das ansonsten sofort ab:

```
AttributeError: module 'pcb_rogowski.domain.coil.service' has no
attribute 'CoilParameterServiceImpl._calc_l_vias'
```

---

## 4. Mapping-Tabelle (Stand: Phase 5)

Alle 10 registrierten Formeln und ihre Python-Implementierung:

| Registry-Key             | Anzeige (Kurz)                      | `impl`                                                                              |
| ------------------------ | ----------------------------------- | ----------------------------------------------------------------------------------- |
| `geometry_extract`       | Geometrie-Ableitung                 | `domain.coil.geometry::GeometryExtractor.extract`                                   |
| `L_track_self_segment`   | Selbstinduktivität Track-Segment    | `domain.coil.service::CoilParameterServiceImpl._calc_l_track`                       |
| `L_vias`                 | Via-Induktivität                    | `domain.coil.service::CoilParameterServiceImpl._calc_l_vias`                        |
| `L_trace`                | Induktivität der Anschlussleitung   | `domain.coil.service::CoilParameterServiceImpl._calc_l_trace`                       |
| `L_total`                | Summenformel L_C                    | `domain.coil.service::CoilParameterServiceImpl.compute`                             |
| `R_series`               | Temperaturabhängiger Serienwiderst. | `domain.coil.service::CoilParameterServiceImpl._calc_r_series`                      |
| `C_interturn_cps`        | CPS-Interleiter-Kapazität           | `domain.coil.service::CoilParameterServiceImpl._calc_c_series`                      |
| `f_res`                  | Resonanzfrequenz                    | `domain.coil.service::CoilParameterServiceImpl.compute`                             |
| `M_conductor_config`     | Primärleiter-Konfiguration          | `domain.mutual.calculator::MutualInductanceCalculator.compute`                      |
| `M_total`                | M_ges aus Fensterbeiträgen          | `domain.mutual.calculator::MutualInductanceCalculator._compute_window_field_integral` |

> **Automatische Prüfung:** `tests/unit/test_formula_registry.py::test_every_impl_resolves`
> ruft `resolve_impl(key)` für jeden Eintrag auf und schlägt fehl,
> sobald ein Pfad ins Leere zeigt.

---

## 5. Worked Example — `L_vias`-Modell tauschen

**Ausgangslage:** Aktuelles Modell ist Goldfarb/Pucel (zylindrische
Via, kein Plating-Effekt). Wir wollen auf Wheeler umstellen.

### Schritt 1 — Physik

Datei: [src/pcb_rogowski/domain/coil/service.py](src/pcb_rogowski/domain/coil/service.py#L271)

```python
def _calc_l_vias(self, g, steps, warnings) -> float:
    """Via-Induktivität [H]. Wheeler-Näherung.

    Registry-Key
    ------------
    ``L_vias``.

    Physik
    ------
    L_via = (µ₀·h)/(2π) · [ln(4h/d) - 1]           # Wheeler
    L_vias = 2·N · L_via

    Annahmen / Gültigkeitsbereich
    -----------------------------
    * h ≫ d  (langer, dünner Leiter).
    * Cu-Plating-Effekt vernachlässigt.

    Sanity-Zahl
    -----------
    h=1.6mm, d=0.3mm → L_via ≈ 1.4nH (Wheeler) vs. 1.0nH (Goldfarb).
    """
    mu0 = 4e-7 * math.pi
    h = g.h_board_mm * 1e-3
    d = g.d_via_mm * 1e-3
    if d <= 0 or h <= 0:
        warnings.append("Via-Maße nicht plausibel.")
        return 0.0
    l_single = (mu0 * h) / (2 * math.pi) * (math.log(4 * h / d) - 1.0)
    return 2.0 * g.N * l_single
```

### Schritt 2 — Anzeige

Datei: [src/pcb_rogowski/domain/formulas.py](src/pcb_rogowski/domain/formulas.py)

```python
_add(Formula(
    key="L_vias",
    latex=(
        "L_{via} = \\frac{\\mu_0 h}{2\\pi}\\left[\\ln\\frac{4h}{d} - 1\\right]\n"
        "L_{vias} = 2N \\cdot L_{via}"
    ),
    description=(
        "Wheeler-Näherung für dünne zylindrische Vias. "
        "h = Boardhöhe, d = Via-Durchmesser. "
        "Cu-Plating-Effekt vernachlässigt."
    ),
    variables={
        "h": "Boardhöhe [m]",
        "d": "Via-Durchmesser [m]",
        "N": "Windungszahl (2N = Anzahl Vias)",
        "µ₀": "magnetische Feldkonstante [H/m]",
    },
    unit="H",
    reference="docs/berechnungen.md §L_vias (Wheeler)",
    impl="domain.coil.service::CoilParameterServiceImpl._calc_l_vias",
))
```

### Schritt 3 — Tests

```powershell
pytest tests/unit/test_formula_registry.py tests/golden_cases -v
```

**Erwartet:** Golden-Cases schlagen fehl (Zahlen haben sich geändert).
Das ist der Signal-Moment: neue Referenzwerte prüfen, von Hand
plausibilisieren und die `expected_*`-Konstanten in den Golden-Cases
aktualisieren — **nur wenn die neue Physik bewusst gewünscht war**.

### Schritt 4 — GUI-Check

Ladung Design-03 → L_vias im Trace muss ~40% größer sein
(1.4nH vs 1.0nH pro Via).

---

## 6. Konsistenz-Gates (CI-tauglich)

Diese Checks laufen automatisch und fangen Desynchronisation ab:

| Gate                                             | Datei                                          | Prüft                                                          |
| ------------------------------------------------ | ---------------------------------------------- | -------------------------------------------------------------- |
| `test_formulas_registry_not_empty`               | `tests/unit/test_formula_registry.py`          | Registry existiert und ist nicht leer                          |
| `test_every_formula_has_required_fields`         | ″                                              | key/latex/description/variables/unit/reference/impl alle nicht-leer |
| `test_every_calc_step_uses_registry`             | ″                                              | Keine frei getippten Formel-Strings in `service.py`/`calculator.py` |
| `test_every_impl_resolves`                       | ″                                              | Jeder `impl`-Pfad ist per `resolve_impl()` importierbar        |
| `test_coil_parameters_golden_design_0x`          | `tests/golden_cases/test_coil_parameters_golden.py` | Numerische Regression gegen eingefrorene Design-Werte          |

---

## 7. Häufige Fallstricke

1. **Einheiten-Mismatch** — Registry schreibt `[µH]`, Python rechnet in
   `[H]`: *immer* in SI rechnen, Umrechnung nur beim Trace-Output.
2. **LaTeX-Escaping** — `\\` in Python = `\` in LaTeX. Bei Copy-Paste
   aus Lehrbüchern Backslashes verdoppeln.
3. **`impl`-Feld vergessen zu aktualisieren** — nach Refactorings
   (Methode umbenennen, Klasse verschieben): Registry-Test schlägt an,
   trotzdem gerne vergessen → erst pytest laufen lassen, dann pushen.
4. **Sanity-Zahl nicht nachgezogen** — Docstring-Zahl ist dokumentarisch,
   kein Test. Bei Physik-Änderung manuell neu rechnen.
5. **Golden-Case blind akzeptiert** — wenn die Regression fehlschlägt,
   darf der neue Wert NICHT einfach übernommen werden, ohne ihn von
   Hand zu plausibilisieren.

---

## 8. Querverweise

- Registry-Code:            [src/pcb_rogowski/domain/formulas.py](src/pcb_rogowski/domain/formulas.py)
- Coil-Impl:                [src/pcb_rogowski/domain/coil/service.py](src/pcb_rogowski/domain/coil/service.py)
- Mutual-Impl:              [src/pcb_rogowski/domain/mutual/calculator.py](src/pcb_rogowski/domain/mutual/calculator.py)
- Physik-Herleitungen:      [docs/berechnungen.md](docs/berechnungen.md)
- Registry-Tests:           [tests/unit/test_formula_registry.py](tests/unit/test_formula_registry.py)
- Numerische Golden-Cases:  [tests/golden_cases/test_coil_parameters_golden.py](tests/golden_cases/test_coil_parameters_golden.py)
