"""
Infrastructure: Stackup-Loader.

Lädt eine ``stackup_*.yaml``-Datei und wandelt sie in ein
:class:`~pcb_rogowski.domain.stackup.models.Stackup`-Domainobjekt um.

Verwendung::

    from pcb_rogowski.infrastructure.stackup.loader import StackupLoader

    stackup = StackupLoader.from_yaml(Path("configs/stackup_design03.yaml"))
    print(stackup.total_thickness_mm)   # → 0.96012 mm (3 × 0.32004 mm)
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pcb_rogowski.domain.stackup.models import (
    CopperLayerSpec,
    DielectricSpec,
    Stackup,
)


class StackupLoader:
    """Lädt Stackup-Definitionen aus YAML-Dateien."""

    @staticmethod
    def from_yaml(path: Path) -> Stackup:
        """
        Parst eine ``stackup_*.yaml``-Datei und gibt ein :class:`Stackup` zurück.

        Unterstütztes Schema (entspricht ``configs/stackup_design03.yaml``)::

            stackup:
              name: "Design03_4Layer"
              total_thickness_mm: 1.12268   # optional – falls vorhanden wird er
                                            # für h_via verwendet, sonst Summe Dielektrika
              copper_layers:
                - name: "top_layer"
                  thickness_um: 35.56
                  index: 0
              dielectrics:
                - name: "Dielectric_1"
                  thickness_mm: 0.32004
                  epsilon_r: 4.8
                  loss_tangent: 0.02

        Args:
            path: Pfad zur YAML-Datei.

        Returns:
            :class:`Stackup`-Objekt mit Kupfer- und Dielektrikumslagen.

        Raises:
            FileNotFoundError: Datei nicht gefunden.
            KeyError / ValueError: Fehlerhaftes Schema.
        """
        if not path.is_file():
            raise FileNotFoundError(f"Stackup-YAML nicht gefunden: {path}")

        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        # Wurzel-Schlüssel „stackup:" ist optional (Datei kann auch direkt starten)
        data: dict = raw.get("stackup", raw)

        copper_layers = [
            CopperLayerSpec(
                name=str(c["name"]),
                thickness_um=float(c["thickness_um"]),
                index=int(c["index"]),
            )
            for c in data.get("copper_layers", [])
        ]

        dielectrics = [
            DielectricSpec(
                name=str(d["name"]),
                thickness_mm=float(d["thickness_mm"]),
                epsilon_r=float(d["epsilon_r"]),
                loss_tangent=float(d.get("loss_tangent", 0.02)),
                between_layers=(
                    tuple(str(x) for x in d["between_layers"])  # type: ignore[arg-type]
                    if "between_layers" in d and len(d["between_layers"]) == 2
                    else None
                ),
            )
            for d in data.get("dielectrics", [])
        ]

        stackup = Stackup(
            name=str(data.get("name", path.stem)),
            copper_layers=copper_layers,
            dielectrics=dielectrics,
        )

        # Gesamtdicke aus YAML überschreibt berechneten Wert (enthält Lötstopplack etc.)
        explicit_total = data.get("total_thickness_mm")
        if explicit_total is not None:
            stackup._total_thickness_override = float(explicit_total)  # type: ignore[attr-defined]

        return stackup
