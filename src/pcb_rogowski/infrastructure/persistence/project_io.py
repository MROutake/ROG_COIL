"""
Persistenz des GUI-Projektzustands (Liste aller Designs).

Einfaches YAML-Format -- diff-freundlich, manuell editierbar.

Beispiel::

    version: 1
    designs:
      - name: Design 1
        gerber_dir: data_samples/gerber/Desgin_01
        classification_yaml: data_samples/gerber/Desgin_01/classification_draft.yaml
        windows_yaml: configs/windows_Design_2.yaml
        stackup_yaml: configs/stackup_design03.yaml
        bode100_csv: data_samples/Bode100/Desgin_01/Measurement_RogDua (1).csv
        temperature_celsius: 20.0
        method_mutual: analytical
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pcb_rogowski.app.use_cases.analyze_design import DesignInputs


def _rel_or_abs(p: Path | None, root: Path) -> str | None:
    if p is None:
        return None
    p = Path(p)
    try:
        return str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _resolve(p: str | None, root: Path) -> Path | None:
    if not p:
        return None
    pp = Path(p)
    return pp if pp.is_absolute() else (root / pp)


def save_project(path: Path, designs: list[DesignInputs]) -> None:
    """Speichert die Design-Liste als YAML (Pfade relativ zur Projektdatei)."""
    root = Path(path).parent.resolve()
    data = {
        "version": 1,
        "designs": [
            {
                "name": d.name,
                "gerber_dir": _rel_or_abs(d.gerber_dir, root),
                "classification_yaml": _rel_or_abs(d.classification_yaml, root),
                "windows_yaml": _rel_or_abs(d.windows_yaml, root),
                "stackup_yaml": _rel_or_abs(d.stackup_yaml, root),
                "bode100_csv": _rel_or_abs(d.bode100_csv, root),
                "defaults_yaml": _rel_or_abs(d.defaults_yaml, root),
                "temperature_celsius": d.temperature_celsius,
                "method_mutual": d.method_mutual,
            }
            for d in designs
        ],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_project(path: Path) -> list[DesignInputs]:
    """Laedt eine Projektdatei und liefert die Design-Liste."""
    root = Path(path).parent.resolve()
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    designs: list[DesignInputs] = []
    for d in data.get("designs", []):
        gerber = _resolve(d.get("gerber_dir"), root)
        if gerber is None:
            continue
        designs.append(DesignInputs(
            name=str(d.get("name", gerber.name)),
            gerber_dir=gerber,
            classification_yaml=_resolve(d.get("classification_yaml"), root),
            windows_yaml=_resolve(d.get("windows_yaml"), root),
            stackup_yaml=_resolve(d.get("stackup_yaml"), root),
            bode100_csv=_resolve(d.get("bode100_csv"), root),
            defaults_yaml=_resolve(d.get("defaults_yaml"), root),
            temperature_celsius=float(d.get("temperature_celsius", 20.0)),
            method_mutual=str(d.get("method_mutual", "analytical")),
        ))
    return designs
