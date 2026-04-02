#!/usr/bin/env python
"""
calculate_mutual.py – Gegenseitige Induktivität M_prim zwischen
Dual-Busbar-Primärleiter und PCB-Rogowski-Spule berechnen.

Verwendet die Fenster-Extraktion (WindowExtractor) und die analytische
Formel für rechteckige Fenster:

    M_m = (µ₀·h_m)/(2π) · σ_m · [ln((a₁+b)/a₁) − ln((a₂+b)/a₂)]

    M_ges = Σ M_m

Aufrufbeispiel::

    python scripts/calculate_mutual.py data_samples/gerber
    python scripts/calculate_mutual.py data_samples/gerber/Desgin_03 --method numerical
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Windows: stdout auf UTF-8 umstellen
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import yaml

from pcb_rogowski.domain.mutual.calculator import ConductorConfig
from pcb_rogowski.domain.mutual.service import MutualInductanceService
from pcb_rogowski.domain.mutual.models import MutualInductanceResult
from pcb_rogowski.domain.trace.classifier import (
    ClassificationSpec,
    ClassifierConfig,
    FishboneClassifier,
    TopologyGapFiller,
)
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.infrastructure.stackup.loader import StackupLoader

# ────────────────────────────────────────────────────────────────────
# Formatierungs-Helfer
# ────────────────────────────────────────────────────────────────────

_SEP  = "-" * 82
_SEP2 = "=" * 82


def _hdr(title: str) -> None:
    print(f"\n{_SEP2}")
    print(f"  {title}")
    print(_SEP2)


def _row(label: str, value: str, unit: str = "") -> None:
    u = f"  [{unit}]" if unit else ""
    print(f"  {label:<40s}  {value:>14s}{u}")


def _design_key(name: str) -> str | None:
    m = re.search(r"(\d+)", name)
    return str(int(m.group(1))) if m else None


# ────────────────────────────────────────────────────────────────────
# Busbar-Konfiguration aus YAML laden
# ────────────────────────────────────────────────────────────────────

def _load_busbar_config(
    yaml_path: Path,
    coil_center_x: float | None = None,
    coil_center_y: float | None = None,
) -> ConductorConfig:
    """
    Liest die Busbar-Geometrie aus ``geometry_baseline.yaml`` und erzeugt
    eine ConductorConfig.

    Die Busbar-Leiter verlaufen senkrecht durch die PCB (z-Achse).
    Ihre Position wird relativ zum Spulenzentrum angegeben::

        center_offset_mm:  Abstand Busbar-Mittelebene ↔ Spulenzentrum
        width_mm:          Breite des Busbars

    Daraus ergeben sich zwei Linienleiter:
        Leiter 1 (+I): center_offset − width/2
        Leiter 2 (−I): center_offset + width/2

    Falls kein Spulenzentrum angegeben wird, werden die Leiter relativ
    zum Koordinatenursprung positioniert.
    """
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    bus = cfg.get("busbar", {})
    width       = bus.get("width_mm", 10.0)
    offset      = bus.get("center_offset_mm", 0.0)

    # Spulenzentrum: Koordinate, an der die Busbar-Mitte sitzt
    cx = coil_center_x if coil_center_x is not None else 0.0
    cy = coil_center_y if coil_center_y is not None else 0.0

    # Leiter verlaufen in z-Richtung (senkrecht zur PCB),
    # ihre x,y-Position bestimmt den radialen Abstand zum Fenster.
    # Konvention: Offset verschiebt in x-Richtung, Leiter haben gleiche y.
    x1 = cx + offset - width / 2.0
    x2 = cx + offset + width / 2.0

    return ConductorConfig(
        x1_mm=x1, y1_mm=cy,
        x2_mm=x2, y2_mm=cy,
        axis="z",
    )


# ────────────────────────────────────────────────────────────────────
# Einzelnes Design verarbeiten
# ────────────────────────────────────────────────────────────────────

def _process_design(
    gerber_dir: Path,
    stackup_path: Path,
    geometry_path: Path,
    method: str,
) -> tuple[str, MutualInductanceResult | None]:
    """Berechnet M_prim für ein einzelnes Design."""

    yaml_path   = gerber_dir / "classification_draft.yaml"
    design_name = gerber_dir.name

    print(f"\n  {'='*60}")
    print(f"  Design: {design_name}")
    print(f"  {'='*60}")

    try:
        # Board laden
        board = GerberBoardLoader().load_from_gerber(gerber_dir)
        all_lines = sum(len(la.lines) for la in board.copper_layers)
        print(f"  Board geladen:         {all_lines} Leiterbahn-Segmente")

        # --- Klassifikation laden oder erzeugen ---
        if yaml_path.exists():
            spec = ClassificationSpec.from_yaml(yaml_path)
            counts_before = spec.role_counts()
            print(f"  Klassifikation:        YAML  ({yaml_path.relative_to(_ROOT)})")
            print(f"  Rollen (aus YAML):     {counts_before}")

            spec = TopologyGapFiller().fill(board, spec)
            counts_after = spec.role_counts()
            print(f"  Rollen (nach Gap-Fill): {counts_after}")
        else:
            print(f"  Klassifikation:        [!] Keine YAML -> FishboneClassifier (auto)")
            cfg  = ClassifierConfig.from_yaml(_ROOT / "configs" / "defaults.yaml")
            spec = FishboneClassifier(cfg).classify(board)
            print(f"  Rollen (auto):         {spec.role_counts()}")

        counts = spec.role_counts()
        if counts.get("winding", 0) == 0:
            print("  [SKIP]  Keine Winding-Segmente -> Design wird uebersprungen.")
            return design_name, None

        # Stackup laden
        stackup = None
        if stackup_path.exists():
            stackup = StackupLoader.from_yaml(stackup_path)
            print(f"  Stackup:               {stackup_path.name}")
        else:
            print(f"  Stackup:               [!] Nicht gefunden -> Fallback-Werte")

        # Layout + Spulenzentrum bestimmen
        layout = spec.to_trace_layout()

        # Spulenzentrum = Schwerpunkt aller Winding-Segmente
        winding_segs = [
            c for c in layout.classifications
            if c.role.value == "winding"
        ]
        if winding_segs:
            # Passende Board-Features finden
            line_by_id = {}
            for la in board.copper_layers:
                for f in la.lines:
                    line_by_id[f.feature_id] = f

            xs, ys = [], []
            for c in winding_segs:
                feat = line_by_id.get(c.feature_id)
                if feat:
                    xs.append((feat.start.x_mm + feat.end.x_mm) / 2)
                    ys.append((feat.start.y_mm + feat.end.y_mm) / 2)

            cx = sum(xs) / len(xs) if xs else 0.0
            cy = sum(ys) / len(ys) if ys else 0.0
            print(f"  Spulenzentrum:         ({cx:.3f}, {cy:.3f}) mm")
        else:
            cx, cy = 0.0, 0.0

        # Busbar-Konfiguration laden
        conductor = _load_busbar_config(geometry_path, cx, cy)
        print(f"  Leiter 1 (+I):         ({conductor.x1_mm:.3f}, {conductor.y1_mm:.3f}) mm")
        print(f"  Leiter 2 (-I):         ({conductor.x2_mm:.3f}, {conductor.y2_mm:.3f}) mm")

        # M_prim berechnen
        svc = MutualInductanceService(
            conductor=conductor,
            stackup=stackup,
            method=method,
        )
        result, extraction = svc.compute_with_details(layout, board)

        # Ergebnis ausgeben
        print(f"\n  {'-'*50}")
        print(f"  Fenster-Extraktion:")
        print(f"    Fenster:             {len(extraction.windows)}")
        print(f"    Winding-Segmente:    {extraction.n_winding_segments}")
        print(f"    Dominante Achse:     {extraction.dominant_axis}")
        print(f"    Mittl. Zahnlaenge:   {extraction.mean_tooth_length_mm:.3f} mm")
        print(f"    Mittl. Pitch:        {extraction.mean_pitch_mm:.3f} mm")

        print(f"\n  M_prim Ergebnis:")
        print(f"    M_ges = {result.m_total_nH:.4f} nH")
        print(f"    Methode: {method}")

        if result.window_contributions:
            print(f"\n  {'Fenster':<10} {'M_m [nH]':>12} {'sigma':>7} "
                  f"{'Flaeche [mm2]':>14} {'Anteil':>8}")
            print(f"  {'-'*56}")
            for w in result.window_contributions:
                print(f"  {w.window_id:<10} {w.m_nH:>+12.4f} {w.sigma:>+7d} "
                      f"{w.area_mm2:>14.4f} {w.percentage:>7.1f}%")
            print(f"  {'-'*56}")
            print(f"  {'SUMME':<10} {result.m_total_nH:>+12.4f}")

        return design_name, result

    except Exception as exc:
        import traceback
        print(f"  [FEHLER]  {exc}")
        traceback.print_exc()
        return design_name, None


# ────────────────────────────────────────────────────────────────────
# Zusammenfassungstabelle
# ────────────────────────────────────────────────────────────────────

def _print_summary(results: list[tuple[str, MutualInductanceResult | None]]) -> None:
    _hdr("Zusammenfassung: M_prim aller Designs")

    valid = [(n, r) for n, r in results if r is not None]
    if not valid:
        print("  [INFO]  Keine Ergebnisse zum Vergleichen.")
        return

    COL = 14
    print(f"\n  {'Design':<20}  {'M_ges [nH]':>{COL}}  {'N_Fenster':>{COL}}")
    print(f"  {_SEP}")
    for name, r in valid:
        n_win = len(r.window_contributions)
        print(f"  {name:<20}  {r.m_total_nH:>{COL}.4f}  {n_win:>{COL}d}")
    print(f"  {_SEP}")

    # Hinweis zur Empfindlichkeit
    print(f"\n  Hinweis:")
    print(f"    M_prim = Gegeninduktivitaet Primaerleiter <-> Rogowski-Spule")
    print(f"    Sensorempfindlichkeit: U_out = M_prim * dI/dt")
    print(f"    Vorzeichen-Konvention: sigma = +1 fuer CW-Winding, -1 fuer CCW")


# ────────────────────────────────────────────────────────────────────
# Argument-Parser und main()
# ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M_prim: Gegenseitige Induktivitaet Primaerleiter <-> Rogowski-Spule",
    )
    p.add_argument("designs_root", type=Path,
                   help="Pfad zum Root-Verzeichnis mit Gerber-Designs.")
    p.add_argument("--stackup", "-s", type=Path,
                   default=_ROOT / "configs" / "stackup_design03.yaml",
                   help="Stackup-YAML (Standard: configs/stackup_design03.yaml).")
    p.add_argument("--geometry", "-g", type=Path,
                   default=_ROOT / "configs" / "geometry_baseline.yaml",
                   help="Geometrie-YAML mit Busbar-Konfiguration.")
    p.add_argument("--method", "-m", type=str, default="analytical",
                   choices=["analytical", "numerical"],
                   help="Berechnungsmethode (Standard: analytical).")
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Ergebnis als JSON speichern.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    designs_root = args.designs_root.resolve()

    if not designs_root.is_dir():
        print(f"[FEHLER]  Verzeichnis nicht gefunden: {designs_root}", file=sys.stderr)
        return 1

    # Gerber-Verzeichnisse finden
    _GERBER_EXTS = {
        ".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".g1", ".g2", ".g3",
        ".gbr", ".ger", ".gtp", ".gbp", ".gko", ".gm1", ".gm2",
    }

    def _is_gerber_dir(path: Path) -> bool:
        return path.is_dir() and any(
            f.suffix.lower() in _GERBER_EXTS for f in path.iterdir() if f.is_file()
        )

    if _is_gerber_dir(designs_root):
        gerber_dirs = [designs_root]
    else:
        gerber_dirs = sorted(d for d in designs_root.iterdir() if _is_gerber_dir(d))

    if not gerber_dirs:
        print(f"[FEHLER]  Keine Gerber-Verzeichnisse in {designs_root} gefunden.",
              file=sys.stderr)
        return 1

    _hdr(f"M_prim-Berechnung: {len(gerber_dirs)} Designs")
    print(f"  Root:     {designs_root}")
    print(f"  Methode:  {args.method}")
    print(f"  Geometrie: {args.geometry}")

    # Alle Designs berechnen
    results: list[tuple[str, MutualInductanceResult | None]] = []
    for gerber_dir in gerber_dirs:
        name, result = _process_design(
            gerber_dir, args.stackup, args.geometry, args.method,
        )
        results.append((name, result))

    # Zusammenfassung
    _print_summary(results)

    # JSON-Export
    if args.output:
        valid = [(n, r) for n, r in results if r is not None]
        out_path = args.output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "designs_root": str(designs_root),
            "method": args.method,
            "results": [
                {
                    "design": name,
                    "m_total_nH": r.m_total_nH,
                    "n_windows": len(r.window_contributions),
                    "windows": [
                        {
                            "id": w.window_id,
                            "m_nH": w.m_nH,
                            "sigma": w.sigma,
                            "area_mm2": w.area_mm2,
                            "percentage": w.percentage,
                        }
                        for w in r.window_contributions
                    ],
                }
                for name, r in valid
            ],
        }

        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"\n  Ergebnis gespeichert: {out_path}")

    print(f"\n{'='*80}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
