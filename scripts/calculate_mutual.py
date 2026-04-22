#!/usr/bin/env python
"""
calculate_mutual.py – Gegenseitige Induktivität M_prim zwischen
Dual-Busbar-Primärleiter und PCB-Rogowski-Spule berechnen.

Verwendet manuell definierte Fenster-YAMLs (configs/windows_Design_X.yaml)
und berechnet M über drei mögliche Methoden:

1) **field_integral** (Standard, exakt für Linienleiter):
    M_m = σ_m · h_m · (µ₀)/(2π) · ∫(via_a→via_b) F⊥(l) dl

    Integriert die Normalkomponente des realen, resultierenden B-Feldes
    (Superposition beider Leiter) entlang des Via-zu-Via-Pfades.
    Keine Annahme über die Feldgeometrie nötig.

2) **analytical** (vereinfacht):
    M_m = (µ₀·h_m)/(2π) · σ_m · [ln((a₁+b)/a₁) − ln((a₂+b)/a₂)]
    Setzt konzentrische Feldlinien um jeden Leiter voraus.

3) **numerical** (2D-Rasterintegration über die Fensterfläche)

    M_ges = Σ |M_m|  (betragsmäßige Aufsummierung)

Aufrufbeispiel::

    python scripts/calculate_mutual.py --design 2
    python scripts/calculate_mutual.py --design 2 3
    python scripts/calculate_mutual.py --design 2 3 --plot
    python scripts/calculate_mutual.py --design 3 --compare
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure

# Windows: stdout auf UTF-8 umstellen
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import yaml

from pcb_rogowski.domain.mutual.calculator import ConductorConfig, MutualInductanceCalculator
from pcb_rogowski.domain.mutual.models import MutualInductanceResult
from pcb_rogowski.domain.trace.models import ViaWindow

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


# ────────────────────────────────────────────────────────────────────
# Fenster-YAML laden
# ────────────────────────────────────────────────────────────────────

def _load_windows_from_yaml(yaml_path: Path) -> tuple[list[ViaWindow], float]:
    """
    Lädt Via-Fenster aus einer manuell erstellten YAML-Datei.

    Returns:
        (windows, h_via_mm) – Liste der ViaWindow-Objekte und die Via-Höhe.
    """
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    h_via_mm = float(data.get("h_via_mm", 1.12268))
    windows: list[ViaWindow] = []

    for wd in data.get("windows", []):
        via_a = wd.get("via_a_xy")
        via_b = wd.get("via_b_xy")

        win = ViaWindow(
            window_id=wd["window_id"],
            x_min_mm=float(wd["x_min_mm"]),
            y_min_mm=float(wd["y_min_mm"]),
            x_max_mm=float(wd["x_max_mm"]),
            y_max_mm=float(wd["y_max_mm"]),
            sigma=int(wd.get("sigma", 1)),
            via_a_xy=tuple(via_a) if via_a else None,
            via_b_xy=tuple(via_b) if via_b else None,
            dist_mm=float(wd["dist_mm"]) if "dist_mm" in wd else None,
            h_via_mm=float(wd.get("h_via_mm", h_via_mm)),
        )
        windows.append(win)

    return windows, h_via_mm


def _coil_center_from_windows(windows: list[ViaWindow]) -> tuple[float, float]:
    """Berechnet das Spulenzentrum aus den Via-Positionen aller Fenster."""
    xs: list[float] = []
    ys: list[float] = []

    for w in windows:
        if w.via_a_xy is not None:
            xs.append(w.via_a_xy[0])
            ys.append(w.via_a_xy[1])
        if w.via_b_xy is not None:
            xs.append(w.via_b_xy[0])
            ys.append(w.via_b_xy[1])

    if not xs:
        # Fallback: BBox-Mittelpunkte
        for w in windows:
            xs.append((w.x_min_mm + w.x_max_mm) / 2)
            ys.append((w.y_min_mm + w.y_max_mm) / 2)

    cx = sum(xs) / len(xs) if xs else 0.0
    # y-Zentrum: Mittelwert von min und max (wie in Referenz)
    cy = (min(ys) + max(ys)) / 2.0 if ys else 0.0

    return cx, cy


# ────────────────────────────────────────────────────────────────────
# Busbar-Konfiguration aus YAML laden
# ────────────────────────────────────────────────────────────────────

def _load_busbar_config(
    yaml_path: Path,
    coil_center_x: float,
    coil_center_y: float,
) -> ConductorConfig:
    """
    Liest die Busbar-Geometrie aus ``geometry_baseline.yaml`` und erzeugt
    eine ConductorConfig.

    Die Busbar-Leiter verlaufen senkrecht durch die PCB (z-Achse).
    Ihre Position wird relativ zum Spulenzentrum angegeben.

    Der Parameter ``separation_axis`` bestimmt, ob die beiden Leiter
    in x- oder y-Richtung getrennt werden:
        - ``"y"``: Leiter 1 bei y_center − width/2, Leiter 2 bei y_center + width/2
        - ``"x"``: Leiter 1 bei x_center − width/2, Leiter 2 bei x_center + width/2
    """
    with open(yaml_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    bus = cfg.get("busbar", {})
    width     = bus.get("width_mm", 10.0)
    offset    = bus.get("center_offset_mm", 0.0)
    sep_axis  = bus.get("separation_axis", "y")

    cx = coil_center_x
    cy = coil_center_y

    if sep_axis == "y":
        # Leiter getrennt in y-Richtung (übereinander)
        y1 = cy + offset - width / 2.0
        y2 = cy + offset + width / 2.0
        return ConductorConfig(
            x1_mm=cx, y1_mm=y1,
            x2_mm=cx, y2_mm=y2,
            axis="z",
        )
    else:
        # Leiter getrennt in x-Richtung (nebeneinander)
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
    design_key: str,
    geometry_path: Path,
    method: str,
) -> tuple[str, MutualInductanceResult | None, ConductorConfig | None, list[ViaWindow]]:
    """Berechnet M_prim für ein einzelnes Design aus der Fenster-YAML."""

    design_name = f"Design_{design_key}"

    # Fenster-YAML suchen
    windows_yaml = _ROOT / "configs" / f"windows_{design_name}.yaml"
    if not windows_yaml.exists():
        print(f"\n  [SKIP]  {design_name}: Keine Fenster-YAML gefunden")
        print(f"          Erwartet: {windows_yaml}")
        return design_name, None, None, []

    print(f"\n  {'='*60}")
    print(f"  Design: {design_name}")
    print(f"  {'='*60}")

    try:
        # Fenster aus YAML laden
        windows, h_via_mm = _load_windows_from_yaml(windows_yaml)
        print(f"  Fenster-YAML:          {windows_yaml.name}")
        print(f"  Anzahl Fenster:        {len(windows)}")
        print(f"  h_via (PCB-Dicke):     {h_via_mm:.5f} mm")

        if not windows:
            print("  [SKIP]  Keine Fenster in YAML definiert.")
            return design_name, None, None, []

        # Spulenzentrum aus Via-Positionen berechnen
        cx, cy = _coil_center_from_windows(windows)
        print(f"  Spulenzentrum:         ({cx:.3f}, {cy:.3f}) mm")

        # Busbar-Konfiguration laden
        conductor = _load_busbar_config(geometry_path, cx, cy)
        print(f"  Leiter 1 (+I):         ({conductor.x1_mm:.3f}, {conductor.y1_mm:.3f}) mm")
        print(f"  Leiter 2 (-I):         ({conductor.x2_mm:.3f}, {conductor.y2_mm:.3f}) mm")

        sep = math.hypot(conductor.x2_mm - conductor.x1_mm,
                         conductor.y2_mm - conductor.y1_mm)
        print(f"  Leiter-Abstand:        {sep:.3f} mm")

        # M_prim berechnen
        calculator = MutualInductanceCalculator(
            conductor=conductor,
            method=method,
        )
        result = calculator.compute(windows, h_eff_mm=h_via_mm)

        # Ergebnis ausgeben
        print(f"\n  {'-'*50}")
        print(f"  M_prim Ergebnis:")
        print(f"    M_ges = {result.m_total_nH:.4f} nH")
        print(f"    Methode: {method}")
        print(f"    Summation: |M_m| (betragsmäßig)")

        if result.window_contributions:
            print(f"\n  {'Fenster':<10} {'M_m [nH]':>12} {'|M_m| [nH]':>12} {'sigma':>7} "
                  f"{'b_m [mm]':>10} {'Anteil':>8}")
            print(f"  {'-'*64}")
            for i, w in enumerate(result.window_contributions):
                # b_m aus dist_mm
                b_str = f"{windows[i].dist_mm:.3f}" if (i < len(windows) and windows[i].dist_mm) else "?"
                print(f"  {w.window_id:<10} {w.m_nH:>+12.4f} {abs(w.m_nH):>12.4f} {w.sigma:>+7d} "
                      f"{b_str:>10} {w.percentage:>7.1f}%")
            print(f"  {'-'*64}")
            print(f"  {'SUMME |M|':<10} {result.m_total_nH:>+12.4f}")

        return design_name, result, conductor, windows

    except Exception as exc:
        import traceback
        print(f"  [FEHLER]  {exc}")
        traceback.print_exc()
        return design_name, None, None, []


# ────────────────────────────────────────────────────────────────────
# Visualisierung: Busbar + Coil + B-Feld-Konturen
# ────────────────────────────────────────────────────────────────────

def _plot_field(
    design_name: str,
    conductor: ConductorConfig,
    windows: list[ViaWindow],
    result: MutualInductanceResult,
    save_path: Path | None = None,
) -> "Figure":
    """
    Erzeugt einen Plot mit:
    - Via-Positionen der Spule
    - Busbar-Leiterpositionen
    - Magnetfeld-Linien als geschlossene Konturen (Vektorpotential A_z)
    - Fenster-Rechtecke (farbig nach σ)
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    # Via-Positionen sammeln
    via_xs, via_ys = [], []
    for w in windows:
        if w.via_a_xy:
            via_xs.append(w.via_a_xy[0])
            via_ys.append(w.via_a_xy[1])
        if w.via_b_xy:
            via_xs.append(w.via_b_xy[0])
            via_ys.append(w.via_b_xy[1])

    # Bereich für B-Feld-Berechnung (etwas größer als Spulenausdehnung)
    if via_xs and via_ys:
        x_range = [min(via_xs), max(via_xs)]
        y_range = [min(via_ys), max(via_ys)]
    else:
        x_range = [min(w.x_min_mm for w in windows), max(w.x_max_mm for w in windows)]
        y_range = [min(w.y_min_mm for w in windows), max(w.y_max_mm for w in windows)]

    margin = max(x_range[1] - x_range[0], y_range[1] - y_range[0]) * 0.3
    x_lo, x_hi = x_range[0] - margin, x_range[1] + margin
    y_lo, y_hi = y_range[0] - margin, y_range[1] + margin

    # Gitter für Vektorpotential A_z
    nx, ny = 400, 400
    xg = np.linspace(x_lo, x_hi, nx)
    yg = np.linspace(y_lo, y_hi, ny)
    X, Y = np.meshgrid(xg, yg)

    # Leiter-Positionen
    x1, y1 = conductor.x1_mm, conductor.y1_mm
    x2, y2 = conductor.x2_mm, conductor.y2_mm

    # Vektorpotential A_z = -(µ₀ I)/(2π) · [ln(ρ₁) - ln(ρ₂)]
    # Konturen von A_z = const sind die Magnetfeld-Linien
    rho1 = np.sqrt((X - x1)**2 + (Y - y1)**2)
    rho2 = np.sqrt((X - x2)**2 + (Y - y2)**2)

    # Regularisierung: Mindestabstand
    rho1 = np.maximum(rho1, 0.1)
    rho2 = np.maximum(rho2, 0.1)

    A_z = np.log(rho1 / rho2)  # proportional zu A_z (Konstanten kürzen sich)

    # Plot
    plt.style.use("dark_background")
    fig, ax = plt.subplots(1, 1, figsize=(14, 12), facecolor="#1a1a2e")
    ax.set_facecolor("#0d1117")
    ax.set_aspect("equal")

    # B-Feld-Konturen (geschlossene Linien)
    levels = np.linspace(-3.0, 3.0, 41)
    cs = ax.contour(X, Y, A_z, levels=levels, colors="#3388cc",
                     linewidths=0.5, alpha=0.5)

    # Fenster-Rechtecke
    for w in windows:
        color = "#44aaff" if w.sigma == 1 else "#ff8800"
        rect = mpatches.Rectangle(
            (w.x_min_mm, w.y_min_mm),
            w.x_max_mm - w.x_min_mm,
            w.y_max_mm - w.y_min_mm,
            linewidth=1.5, edgecolor=color, facecolor=color,
            alpha=0.15, zorder=4,
        )
        ax.add_patch(rect)

    # Via-Positionen
    if via_xs and via_ys:
        ax.scatter(via_xs, via_ys, s=12, c="#00ff88", marker="o",
                   zorder=6, label="Vias", edgecolors="white", linewidths=0.3)

    # Busbar-Leiter (als große Marker)
    ax.plot(x1, y1, "x", color="#ff4444", markersize=18, markeredgewidth=3,
            zorder=10, label=f"Leiter 1 (+I) ({x1:.1f}, {y1:.1f})")
    ax.plot(x2, y2, "o", color="#ff4444", markersize=14, markeredgewidth=2,
            fillstyle="none", zorder=10,
            label=f"Leiter 2 (−I) ({x2:.1f}, {y2:.1f})")

    # Spulenzentrum
    ccx, ccy = _coil_center_from_windows(windows)
    ax.plot(ccx, ccy, "+", color="#ffff00", markersize=14, markeredgewidth=2,
            zorder=10, label=f"Spulenzentrum ({ccx:.1f}, {ccy:.1f})")

    # Legende
    ax.legend(loc="upper left", fontsize=9, facecolor="#16213e",
              edgecolor="#334455", labelcolor="white")

    # Titel und Labels
    ax.set_title(
        f"{design_name}  —  M_ges = {result.m_total_nH:.4f} nH\n"
        f"B-Feld-Linien (geschlossene Konturen) + {len(windows)} Fenster",
        color="white", fontsize=13, fontweight="bold",
    )
    ax.set_xlabel("x [mm]", color="white")
    ax.set_ylabel("y [mm]", color="white")
    ax.tick_params(colors="white")

    # σ-Legende
    sigma_pos = mpatches.Patch(facecolor="#44aaff", alpha=0.3, label="σ = +1")
    sigma_neg = mpatches.Patch(facecolor="#ff8800", alpha=0.3, label="σ = −1")
    ax2 = ax.legend(loc="upper left", fontsize=9, facecolor="#16213e",
                     edgecolor="#334455", labelcolor="white")
    ax.add_artist(ax2)
    ax.legend(handles=[sigma_pos, sigma_neg], loc="lower right", fontsize=9,
              facecolor="#16213e", edgecolor="#334455", labelcolor="white",
              title="Fenster-σ", title_fontproperties={"weight": "bold"})

    plt.tight_layout()

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, facecolor=fig.get_facecolor())
        print(f"  Plot gespeichert: {save_path}")

    return fig


# ────────────────────────────────────────────────────────────────────
# Vergleich: field_integral vs. analytical
# ────────────────────────────────────────────────────────────────────

def _compare_methods(
    design_key: str,
    geometry_path: Path,
    windows: list[ViaWindow],
    conductor: ConductorConfig,
    fi_result: MutualInductanceResult,
) -> None:
    """Berechnet das gleiche Design mit der analytischen Methode und
    gibt eine Vergleichstabelle aus."""

    h_via_mm = windows[0].h_via_mm if windows and windows[0].h_via_mm else 1.12268

    calc_an = MutualInductanceCalculator(
        conductor=conductor,
        method="analytical",
    )
    an_result = calc_an.compute(windows, h_eff_mm=h_via_mm)

    print(f"\n  {'─'*60}")
    print(f"  Vergleich: field_integral vs. analytical")
    print(f"  {'─'*60}")

    # Fensterweiser Vergleich (erste/letzte 5 + Zusammenfassung)
    fi_wins = {w.window_id: w for w in fi_result.window_contributions}
    an_wins = {w.window_id: w for w in an_result.window_contributions}

    print(f"  {'Fenster':<10}  {'field_int [nH]':>14}  {'analytical [nH]':>15}  "
          f"{'Δ [nH]':>10}  {'Δ [%]':>8}")
    print(f"  {'-'*62}")

    deltas = []
    for wid in fi_wins:
        fi_m = fi_wins[wid].m_nH
        an_m = an_wins.get(wid)
        if an_m is None:
            continue
        an_m_val = an_m.m_nH
        delta = fi_m - an_m_val
        pct = (delta / abs(an_m_val) * 100.0) if abs(an_m_val) > 1e-12 else 0.0
        deltas.append((wid, fi_m, an_m_val, delta, pct))

    # Zeige erste 5 und letzte 5 wenn > 10
    show = deltas if len(deltas) <= 12 else deltas[:5] + [None] + deltas[-5:]
    for item in show:
        if item is None:
            print(f"  {'  ...':>10}")
            continue
        wid, fi_m, an_m_val, delta, pct = item
        print(f"  {wid:<10}  {fi_m:>+14.4f}  {an_m_val:>+15.4f}  "
              f"{delta:>+10.4f}  {pct:>+7.1f}%")

    print(f"  {'-'*62}")
    print(f"  {'M_ges':<10}  {fi_result.m_total_nH:>14.4f}  {an_result.m_total_nH:>15.4f}  "
          f"{fi_result.m_total_nH - an_result.m_total_nH:>+10.4f}  "
          f"{(fi_result.m_total_nH - an_result.m_total_nH) / max(abs(an_result.m_total_nH), 1e-12) * 100:>+7.1f}%")
    print(f"  {'─'*60}")


# ────────────────────────────────────────────────────────────────────
# Zusammenfassungstabelle
# ────────────────────────────────────────────────────────────────────

def _print_summary(
    results: list[tuple[str, MutualInductanceResult | None, ConductorConfig | None, list[ViaWindow]]],
) -> None:
    _hdr("Zusammenfassung: M_prim aller Designs")

    valid = [(n, r) for n, r, _, _ in results if r is not None]
    if not valid:
        print("  [INFO]  Keine Ergebnisse zum Vergleichen.")
        return

    COL = 14
    print(f"\n  {'Design':<20}  {'M_ges [nH]':>{COL}}  {'N_Fenster':>{COL}}  {'Summation':>{COL}}")
    print(f"  {_SEP}")
    for name, r in valid:
        n_win = len(r.window_contributions)
        print(f"  {name:<20}  {r.m_total_nH:>{COL}.4f}  {n_win:>{COL}d}  {'Σ|M_m|':>{COL}}")
    print(f"  {_SEP}")

    print(f"\n  Hinweis:")
    print(f"    M_prim = Gegeninduktivitaet Primaerleiter <-> Rogowski-Spule")
    print(f"    Sensorempfindlichkeit: U_out = M_prim * dI/dt")
    print(f"    Summation: M_ges = Sigma |M_m| (betragsmaessige Aufsummierung)")
    print(f"    b_m = Euklidische Via-zu-Via-Distanz")
    print(f"    a_1, a_2 = Abstand Fensterrand zum Leiter-Mittelpunkt (Achse)")


# ────────────────────────────────────────────────────────────────────
# Argument-Parser und main()
# ────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="M_prim: Gegenseitige Induktivitaet Primaerleiter <-> Rogowski-Spule\n"
                    "Berechnet M aus manuell definierten Fenster-YAMLs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--design", "-d", type=str, nargs="+", default=["2", "3"],
                   help="Design-Nummern (Standard: 2 3). Design 1 hat keine Fenster-YAML.")
    p.add_argument("--geometry", "-g", type=Path,
                   default=_ROOT / "configs" / "geometry_baseline.yaml",
                   help="Geometrie-YAML mit Busbar-Konfiguration.")
    p.add_argument("--method", "-m", type=str, default="field_integral",
                   choices=["field_integral", "analytical", "numerical"],
                   help="Berechnungsmethode (Standard: field_integral).")
    p.add_argument("--compare", "-c", action="store_true",
                   help="Vergleich: field_integral vs. analytical nebeneinander.")
    p.add_argument("--plot", "-p", action="store_true",
                   help="Visualisierung mit B-Feld-Konturen anzeigen.")
    p.add_argument("--output", "-o", type=Path, default=None,
                   help="Ergebnis als JSON speichern.")
    return p


def main() -> int:
    args = _build_parser().parse_args()

    _hdr(f"M_prim-Berechnung: Design {', '.join(args.design)}")
    print(f"  Methode:    {args.method}")
    if args.compare:
        print(f"  Vergleich:  field_integral vs. analytical")
    print(f"  Geometrie:  {args.geometry}")
    print(f"  Summation:  M_ges = Σ |M_m|")

    # Alle Designs berechnen
    results: list[tuple[str, MutualInductanceResult | None, ConductorConfig | None, list[ViaWindow]]] = []
    figs = []
    for dk in args.design:
        name, result, conductor, windows = _process_design(dk, args.geometry, args.method)
        results.append((name, result, conductor, windows))

        # Vergleich: auch mit analytischer Methode berechnen
        if args.compare and result is not None and conductor is not None and args.method != "analytical":
            _compare_methods(dk, args.geometry, windows, conductor, result)

        # Plot erzeugen falls gewünscht
        if args.plot and result is not None and conductor is not None:
            save_path = _ROOT / "output" / f"mutual_{name}.png"
            fig = _plot_field(name, conductor, windows, result, save_path=save_path)
            figs.append(fig)

    # Zusammenfassung
    _print_summary(results)

    # Alle Plots anzeigen
    if figs:
        import matplotlib.pyplot as plt
        plt.show()

    # JSON-Export
    if args.output:
        valid = [(n, r) for n, r, _, _ in results if r is not None]
        out_path = args.output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "method": args.method,
            "summation": "abs(M_m)",
            "b_m_source": "euclidean_via_distance",
            "results": [
                {
                    "design": name,
                    "m_total_nH": r.m_total_nH,
                    "n_windows": len(r.window_contributions),
                    "windows": [
                        {
                            "id": w.window_id,
                            "m_nH": w.m_nH,
                            "abs_m_nH": abs(w.m_nH),
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
