#!/usr/bin/env python
"""
calculate_coil.py - Ersatzschaltparameter aller PCB-Rogowski-Spulen berechnen und vergleichen.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys

# Windows: stdout auf UTF-8 umstellen, damit Sonderzeichen korrekt erscheinen
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from typing import Literal, NamedTuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from pcb_rogowski.domain.coil.geometry import GeometryExtractor
from pcb_rogowski.domain.coil.service import CoilParameterServiceImpl
from pcb_rogowski.domain.trace.classifier import (
    ClassificationSpec,
    ClassifierConfig,
    FishboneClassifier,
    TopologyGapFiller,
)
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.infrastructure.stackup.loader import StackupLoader


class DesignResult(NamedTuple):
    name: str
    l_total_uH: float
    r_series_ohm: float
    c_series_pF: float


class MeasuredRef(NamedTuple):
    """Referenzmesswerte aus dem Bode 100 Netzwerkanalysator."""
    l_uH: float             # Induktivitaet [µH]
    r_series_ohm: float     # Serienwiderstand [Ω]
    c_pF: float             # Parasitaere Kapazitaet [pF]
    r_parallel_kOhm: float  # Paralleler Verlustwiderstand [kΩ]


# ---------------------------------------------------------------------------
# Bode 100 Messwerte  (Quelle: Netzwerkanalysator-Messung, April 2026)
# ---------------------------------------------------------------------------
_BODE100: dict[str, MeasuredRef] = {
    "1": MeasuredRef(l_uH=2.031,      r_series_ohm=5.200, c_pF=84.9, r_parallel_kOhm=3.6),
    "2": MeasuredRef(l_uH=0.3988,     r_series_ohm=1.700, c_pF=12.3, r_parallel_kOhm=12.4),
    "3": MeasuredRef(l_uH=0.410644,   r_series_ohm=2.116, c_pF=12.9, r_parallel_kOhm=12.4),
}


_SEP  = "-" * 82
_SEP2 = "=" * 82


def _hdr(title: str) -> None:
    print(f"\n{_SEP2}")
    print(f"  {title}")
    print(_SEP2)


def _row(label: str, value: str, unit: str = "") -> None:
    u = f"  [{unit}]" if unit else ""
    print(f"  {label:<35s}  {value:>14s}{u}")


def _warn(msg: str) -> None:
    print(f"  [WARNUNG]  {msg}")


def _design_key(name: str) -> str | None:
    """Extrahiert die Design-Nummer aus einem Verzeichnisnamen.

    Beispiele:  'Desgin_01' -> '1',  'Design_3' -> '3',  'pcb03' -> '3'
    """
    m = re.search(r"(\d+)", name)
    return str(int(m.group(1))) if m else None


def _pct_err(calc: float, meas: float) -> float:
    """Relative Abweichung in Prozent: (berechnet - gemessen) / gemessen * 100."""
    if meas == 0:
        return float("nan")
    return (calc - meas) / meas * 100.0


def _fmt_pct(val: float) -> str:
    """Formatiert Prozentwert mit Vorzeichen; markiert grosse Abweichungen."""
    if val != val:   # nan
        return "  n/a  "
    sign = "+" if val >= 0 else ""
    marker = "  !!" if abs(val) > 30 else ("  !" if abs(val) > 15 else "")
    return f"{sign}{val:6.1f}%{marker}"


def _process_design(
    gerber_dir: Path,
    stackup_path: Path,
    temp: float,
) -> DesignResult | None:
    """Berechnet Parameter fuer ein einzelnes Design."""

    yaml_path   = gerber_dir / "classification_draft.yaml"
    design_name = gerber_dir.name

    print(f"\n  {'='*60}")
    print(f"  Design: {design_name}")
    print(f"  {'='*60}")

    try:
        # Board laden
        board = GerberBoardLoader().load_from_gerber(gerber_dir)
        all_lines = sum(len(la.lines) for la in board.copper_layers)
        print(f"  Board geladen:          {all_lines} Leiterbahn-Segmente")

        # --- Klassifikation laden oder erzeugen ---
        if yaml_path.exists():
            spec = ClassificationSpec.from_yaml(yaml_path)
            n_manual = sum(
                1 for e in spec.entries
                if e.note and e.note.startswith("manuell")
            )
            counts_before = spec.role_counts()
            print(f"  Klassifikation:         YAML  ({yaml_path.relative_to(_ROOT)})")
            print(f"  Manuelle Eintraege:     {n_manual} von {len(spec.entries)}")
            print(f"  Rollen (aus YAML):      {counts_before}")

            # Fehlende Segmente per Topologie auffuellen
            spec = TopologyGapFiller().fill(board, spec)
            counts_after = spec.role_counts()
            print(f"  Rollen (nach Gap-Fill): {counts_after}")
        else:
            print(f"  Klassifikation:         [!] Keine YAML -> FishboneClassifier (auto)")
            cfg  = ClassifierConfig.from_yaml(_ROOT / "configs" / "defaults.yaml")
            spec = FishboneClassifier(cfg).classify(board)
            print(f"  Rollen (auto):          {spec.role_counts()}")

        counts = spec.role_counts()
        if counts.get("winding", 0) == 0:
            print("  [SKIP]  Keine Winding-Segmente -> Design wird uebersprungen.")
            return None

        # Stackup laden
        stackup = None
        if stackup_path.exists():
            stackup = StackupLoader.from_yaml(stackup_path)
            print(f"  Stackup:                {stackup_path.name}")
        else:
            print(f"  Stackup:                [!] Nicht gefunden -> Fallback-Werte")

        # Berechnung
        layout    = spec.to_trace_layout()
        extractor = GeometryExtractor(stackup=stackup)
        service   = CoilParameterServiceImpl(extractor=extractor)
        result    = service.calculate(layout, board, temperature_celsius=temp)

        print(f"  Ergebnis:               L={result.l_total_uH:.4f} uH  "
              f"R={result.r_series_ohm:.4f} Ohm  "
              f"C={result.c_series_pF:.4f} pF")

        return DesignResult(
            name=design_name,
            l_total_uH=result.l_total_uH,
            r_series_ohm=result.r_series_ohm,
            c_series_pF=result.c_series_pF,
        )

    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"  [FEHLER]  {exc}")
        traceback.print_exc()
        return None


def _print_comparison_table(results: list[DesignResult]) -> None:
    """Zeigt Berechnungsergebnisse und Vergleich mit Bode 100 Messung."""
    _hdr("Berechnete Ersatzschaltparameter")

    if not results:
        print("  [INFO]  Keine Ergebnisse zum Vergleichen.")
        return

    # --- Tabelle: nur Berechnungswerte ---
    COL = 16
    print(f"\n  {'Design':<20}  {'L_C [uH]':>{COL}}  {'R_C [Ohm]':>{COL}}  {'C_C [pF]':>{COL}}")
    print(f"  {_SEP}")
    for r in results:
        print(f"  {r.name:<20}  {r.l_total_uH:>{COL}.6f}  "
              f"{r.r_series_ohm:>{COL}.4f}  {r.c_series_pF:>{COL}.4f}")
    print(f"  {_SEP}")

    # --- Abschnitt: Vergleich mit Bode 100 ---
    _hdr("Vergleich Berechnung vs. Bode 100 Messung")

    any_ref = False
    for r in results:
        key = _design_key(r.name)
        ref = _BODE100.get(key) if key else None
        if ref is None:
            print(f"\n  {r.name}: keine Bode-100-Referenz vorhanden.")
            continue

        any_ref = True
        print(f"\n  Design {key}  ({r.name})")
        hdr_line = f"  {'Parameter':<14}  {'Berechnet':>12}  {'Gemessen':>12}  {'Abs. Fehler':>13}  {'Rel. Fehler':>12}"
        sep_line = "  " + "-" * (len(hdr_line) - 2)
        print(sep_line)
        print(hdr_line)
        print(sep_line)

        # Induktivitaet
        abs_l = r.l_total_uH - ref.l_uH
        print(f"  {'L   [uH]':<14}  {r.l_total_uH:>12.4f}  {ref.l_uH:>12.4f}  "
              f"{abs_l:>+13.4f}  {_fmt_pct(_pct_err(r.l_total_uH, ref.l_uH)):>12}")

        # Serienwiderstand
        abs_r = r.r_series_ohm - ref.r_series_ohm
        print(f"  {'R_s [Ohm]':<14}  {r.r_series_ohm:>12.4f}  {ref.r_series_ohm:>12.4f}  "
              f"{abs_r:>+13.4f}  {_fmt_pct(_pct_err(r.r_series_ohm, ref.r_series_ohm)):>12}")

        # Kapazitaet
        abs_c = r.c_series_pF - ref.c_pF
        print(f"  {'C   [pF]':<14}  {r.c_series_pF:>12.4f}  {ref.c_pF:>12.4f}  "
              f"{abs_c:>+13.4f}  {_fmt_pct(_pct_err(r.c_series_pF, ref.c_pF)):>12}")

        # R_p (nur Messwert – Berechnung liefert keinen Parallellwiderstand)
        print(f"  {'R_p [kOhm]':<14}  {'(n. ber.)':>12}  {ref.r_parallel_kOhm:>11.1f}  "
              f"  {'---':>13}  {'---':>12}")
        print(sep_line)

    if not any_ref:
        print("  [INFO]  Keine Bode-100-Referenzwerte fuer die berechneten Designs.")
        return

    # --- Legende ---
    print("\n  Legende:")
    print("    Rel. Fehler = (Berechnet - Gemessen) / Gemessen * 100")
    print("    !  = Abweichung > 15%    !!  = Abweichung > 30%")
    print("    R_p (Parallelverluste) wird vom Berechnungsmodell noch nicht ausgegeben.")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Alle PCB-Rogowski-Spulen – Ersatzschaltparameter vergleichen",
    )
    p.add_argument("designs_root", type=Path,
                   help="Pfad zum Root-Verzeichnis mit mehreren Gerber-Designs.")
    p.add_argument("--stackup", "-s", type=Path,
                   default=_ROOT / "configs" / "stackup_design03.yaml",
                   help="Stackup-YAML (Standard: configs/stackup_design03.yaml).")
    p.add_argument("--temp", type=float, default=20.0,
                   help="Betriebstemperatur [°C] (Standard: 20.0).")
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Ergebnis als JSON speichern.")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    designs_root = args.designs_root.resolve()

    if not designs_root.is_dir():
        print(f"[FEHLER]  Verzeichnis nicht gefunden: {designs_root}", file=sys.stderr)
        return 1

    # Alle Gerber-Verzeichnisse finden
    # Gerber-Dateien haben oft nicht-standardisierte Endungen (GTL, GBL, G1, …)
    _GERBER_EXTS = {
        ".gtl", ".gbl", ".gts", ".gbs", ".gto", ".gbo", ".g1", ".g2", ".g3",
        ".gbr", ".ger", ".gtp", ".gbp", ".gko", ".gm1", ".gm2",
    }

    def _is_gerber_dir(path: Path) -> bool:
        return path.is_dir() and any(
            f.suffix.lower() in _GERBER_EXTS for f in path.iterdir() if f.is_file()
        )

    # Entweder wurde direkt ein Gerber-Verzeichnis übergeben, oder dessen Parent
    if _is_gerber_dir(designs_root):
        gerber_dirs = [designs_root]
    else:
        gerber_dirs = sorted(d for d in designs_root.iterdir() if _is_gerber_dir(d))

    if not gerber_dirs:
        print(f"[FEHLER]  Keine Gerber-Verzeichnisse in {designs_root} gefunden.",
              file=sys.stderr)
        return 1

    _hdr(f"Verarbeite {len(gerber_dirs)} Designs")
    print(f"  Root: {designs_root}")
    print(f"  Modell: Ruehli/Lorenz (Selbstinduktivit\u00e4t), Temperatur: {args.temp} \u00b0C")

    # Alle Designs berechnen
    results = []
    for gerber_dir in gerber_dirs:
        result = _process_design(gerber_dir, args.stackup, args.temp)
        if result:
            results.append(result)

    # Vergleichstabelle
    _print_comparison_table(results)

    # JSON-Export
    if args.output and results:
        out_path = args.output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "designs_root": str(designs_root),
            "model": "self_inductance_ruehli",
            "temperature_celsius": args.temp,
            "results": [r._asdict() for r in results],
        }

        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"\n  Ergebnis gespeichert: {out_path}")

    print(f"\n{'='*80}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
