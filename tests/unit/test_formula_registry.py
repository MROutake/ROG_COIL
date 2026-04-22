"""
Konsistenz-Tests fuer die zentrale Formel-Registry.

Stellt sicher, dass

* jede im Code referenzierte ``FORMULAS[...]``-Schluessel auch in der
  Registry deklariert ist, und
* keine Registry-Eintraege verwaisen (kein Code verwendet sie mehr).

Diese Tests sind der Enforcement-Mechanismus fuer die Regel
"alle Formeln leben zentral in ``src/pcb_rogowski/domain/formulas.py``".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pcb_rogowski.domain.formulas import FORMULAS, Formula, check_coverage, resolve_impl

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "pcb_rogowski"
CALC_FILES = [
    SRC_ROOT / "domain" / "coil" / "service.py",
    SRC_ROOT / "domain" / "mutual" / "calculator.py",
]

# Pattern: FORMULAS["<key>"] or FORMULAS['<key>']
_PAT = re.compile(r'FORMULAS\[\s*[\"\']([A-Za-z0-9_]+)[\"\']\s*\]')


def _collect_referenced_keys() -> set[str]:
    refs: set[str] = set()
    for p in CALC_FILES:
        assert p.exists(), f"Missing calculation module: {p}"
        for m in _PAT.finditer(p.read_text(encoding="utf-8")):
            refs.add(m.group(1))
    return refs


def test_registry_is_nonempty() -> None:
    assert len(FORMULAS) > 0


def test_every_formula_has_required_fields() -> None:
    for key, f in FORMULAS.items():
        assert isinstance(f, Formula)
        assert f.key == key, f"Key mismatch for {key!r}: {f.key!r}"
        assert f.latex.strip(), f"Empty latex for {key!r}"
        assert f.description.strip(), f"Empty description for {key!r}"
        assert f.unit.strip(), f"Empty unit for {key!r}"
        assert f.reference.strip(), f"Empty reference for {key!r}"
        assert f.impl.strip(), f"Empty impl for {key!r}"
        assert "::" in f.impl, (
            f"impl for {key!r} muss Format 'module.path::attr' haben, "
            f"ist aber {f.impl!r}"
        )
        assert len(f.variables) > 0, f"Empty variables for {key!r}"


def test_every_impl_resolves() -> None:
    """Jeder ``impl``-Pfad muss per importlib/getattr auflösbar sein.

    Verhindert tote Verweise nach Refactoring (Umbenennen / Verschieben).
    Siehe docs/FORMELN-ANPASSEN.md §3.6.
    """
    broken: list[str] = []
    for key in FORMULAS:
        try:
            obj = resolve_impl(key)
        except (ImportError, AttributeError) as exc:
            broken.append(f"{key!r}: {exc}")
            continue
        if not callable(obj):
            broken.append(f"{key!r}: impl resolved to non-callable {type(obj).__name__}")
    assert not broken, (
        "impl-Pfade defekt -- Registry und Rechenkern sind out of sync. "
        "Details: docs/FORMELN-ANPASSEN.md §3.6\n" + "\n".join(broken)
    )


def test_no_missing_or_unused_keys() -> None:
    referenced = _collect_referenced_keys()
    missing, unused = check_coverage(referenced)
    assert not missing, (
        f"Formeln werden im Code referenziert, fehlen aber in der Registry: {missing}"
    )
    assert not unused, (
        f"Formeln stehen in der Registry, werden aber nicht referenziert: {unused}. "
        f"Entweder im Code benutzen oder aus formulas.py entfernen."
    )


def test_no_inline_formula_strings_in_calc_files() -> None:
    """Verhindert schleichende Regression: formula=\"...literal...\" im Rechenkern."""
    bad: list[str] = []
    for p in CALC_FILES:
        src = p.read_text(encoding="utf-8")
        # formula=<literal string>  (nicht ueber FORMULAS[...] aufgeloest)
        for m in re.finditer(r'formula\s*=\s*(["\'])', src):
            # Pruefe ob die gleiche Zeile FORMULAS enthaelt -- dann OK
            start = src.rfind("\n", 0, m.start()) + 1
            end = src.find("\n", m.end())
            line = src[start:end]
            if "FORMULAS[" in line:
                continue
            bad.append(f"{p.name}:{src[:m.start()].count(chr(10)) + 1}: {line.strip()}")
    assert not bad, (
        "Inline-Formel-Strings im Rechenkern gefunden -- bitte in "
        "src/pcb_rogowski/domain/formulas.py eintragen und ueber FORMULAS[...] "
        "referenzieren:\n" + "\n".join(bad)
    )
