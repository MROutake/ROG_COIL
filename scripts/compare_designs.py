#!/usr/bin/env python
"""
compare_designs.py – Parametervergleich Design 1 vs. Design 2

Stellt alle berechneten und gemessenen Ersatzschaltparameter der beiden
Rogowski-Spulen-Designs gegenüber und visualisiert die Unterschiede.

Ansätze:
  1) Geometrie-Berechnung  (PEEC-Light: L, R_dc, C, f_res)
  2) Bode100-Fit           (RLC-Serienfit an Impedanzmessung)
  3) Bode100-Messung       (Referenzwerte aus Netzwerkanalysator)

Aufruf:
    python scripts/compare_designs.py
    python scripts/compare_designs.py --show
    python scripts/compare_designs.py --designs 1 2 3
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Windows: stdout auf UTF-8 umstellen
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import numpy as np

# ---------------------------------------------------------------------------
# Importiere den Berechnungs-Kern aus fit_bode100
# ---------------------------------------------------------------------------
# Damit wir nicht alles doppelt implementieren, nutzen wir process_design()
# aus dem bestehenden fit_bode100.py Skript.
sys.path.insert(0, str(_ROOT / "scripts"))
from fit_bode100 import process_design  # noqa: E402


# ---------------------------------------------------------------------------
# Referenzwerte (Bode100 Netzwerkanalysator-Messung)
# ---------------------------------------------------------------------------
_BODE100_REF = {
    "1": dict(l_uH=2.031,    r_ohm=5.200, c_pF=84.9,  r_p_kOhm=3.6),
    "2": dict(l_uH=0.3988,   r_ohm=1.700, c_pF=12.3,  r_p_kOhm=12.4),
    "3": dict(l_uH=0.410644, r_ohm=2.116, c_pF=12.9,  r_p_kOhm=12.4),
}


def _pct_err(calc: float, ref: float) -> float:
    """Relativer Fehler in Prozent."""
    if ref == 0:
        return float("nan")
    return (calc - ref) / ref * 100.0


# ---------------------------------------------------------------------------
# Daten sammeln
# ---------------------------------------------------------------------------

def _collect_data(design_keys: list[str], f_max_hz: float) -> list[dict]:
    """Führt die Berechnung + Fit für alle Designs durch und gibt
    eine Liste von Ergebnis-Dicts zurück."""

    all_results = []
    for dk in design_keys:
        print(f"\n{'='*80}")
        print(f"  Berechne Design {dk} ...")
        print(f"{'='*80}")
        try:
            r = process_design(dk, f_max_hz, do_plot=False, output_dir=None)
            if r:
                # Referenzmesswerte hinzufügen
                ref = _BODE100_REF.get(dk, {})
                r["reference"] = ref
                all_results.append(r)
        except Exception as exc:
            print(f"  [FEHLER] Design {dk}: {exc}")
            import traceback
            traceback.print_exc()

    return all_results


# ---------------------------------------------------------------------------
# Konsolen-Zusammenfassung
# ---------------------------------------------------------------------------

def _print_summary(results: list[dict]) -> None:
    """Druckt eine übersichtliche Vergleichstabelle."""

    SEP = "=" * 100
    print(f"\n\n{SEP}")
    print("  PARAMETERVERGLEICH – ALLE DESIGNS UND ANSÄTZE")
    print(SEP)

    # Header
    designs = [r["design"] for r in results]
    col_w = 18
    hdr = f"  {'Parameter':<22}"
    for dk in designs:
        hdr += f"  {'Design ' + dk:^{col_w*3+4}}"
    print(hdr)

    sub_hdr = f"  {'':<22}"
    for _ in designs:
        sub_hdr += f"  {'Geometrie':>{col_w}} {'Fit':>{col_w}} {'Messung':>{col_w}}"
    print(sub_hdr)
    print(f"  {'-' * (22 + len(designs) * (col_w*3 + 6))}")

    def _val(v, fmt=".4f"):
        return format(v, fmt) if v is not None else "---"

    # L [µH]
    row = f"  {'L [µH]':<22}"
    for r in results:
        g = r["geometry"]["L_uH"]
        f = r["fit"]["L_uH"]
        m = r["reference"].get("l_uH")
        row += f"  {_val(g):>{col_w}} {_val(f):>{col_w}} {_val(m):>{col_w}}"
    print(row)

    # R [Ω]
    row = f"  {'R [Ω]':<22}"
    for r in results:
        g = r["geometry"]["R_dc_ohm"]
        f = r["fit"]["R_dc_ohm"]
        m = r["reference"].get("r_ohm")
        row += f"  {_val(g):>{col_w}} {_val(f):>{col_w}} {_val(m):>{col_w}}"
    print(row)

    # C [pF]
    row = f"  {'C [pF]':<22}"
    for r in results:
        g = r["geometry"]["C_pF"]
        f = r["fit"]["C_pF"]
        m = r["reference"].get("c_pF")
        row += f"  {_val(g):>{col_w}} {_val(f):>{col_w}} {_val(m):>{col_w}}"
    print(row)

    # f_res [MHz]
    row = f"  {'f_res [MHz]':<22}"
    for r in results:
        g = r["geometry"]["f_res_MHz"]
        f = r["fit"]["f_res_MHz"]
        # f_res aus Referenz berechnen
        ref = r["reference"]
        m = None
        if ref.get("l_uH") and ref.get("c_pF"):
            m = 1.0 / (2 * np.pi * np.sqrt(
                ref["l_uH"] * 1e-6 * ref["c_pF"] * 1e-12)) / 1e6
        row += f"  {_val(g, '.3f'):>{col_w}} {_val(f, '.3f'):>{col_w}} {_val(m, '.3f'):>{col_w}}"
    print(row)

    print(f"  {'-' * (22 + len(designs) * (col_w*3 + 6))}")

    # Relative Fehler
    print(f"\n  RELATIVE ABWEICHUNG ZUR MESSUNG [%]")
    print(f"  {'-' * 80}")
    sub_hdr2 = f"  {'Parameter':<22}"
    for dk in designs:
        sub_hdr2 += f"  {'D' + dk + ' Geom':>{col_w}} {'D' + dk + ' Fit':>{col_w}}"
    print(sub_hdr2)
    print(f"  {'-' * 80}")

    params = [
        ("L [µH]",     "L_uH",     "l_uH"),
        ("R [Ω]",      "R_dc_ohm", "r_ohm"),
        ("C [pF]",     "C_pF",     "c_pF"),
    ]
    for label, geom_key, ref_key in params:
        row = f"  {label:<22}"
        for r in results:
            g = r["geometry"].get(geom_key)
            f = r["fit"].get(geom_key)
            m = r["reference"].get(ref_key)
            if g is not None and m:
                err_g = _pct_err(g, m)
                row += f"  {err_g:>+{col_w}.1f}%"
            else:
                row += f"  {'---':>{col_w}}"
            if f is not None and m:
                err_f = _pct_err(f, m)
                row += f"  {err_f:>+{col_w}.1f}%"
            else:
                row += f"  {'---':>{col_w}}"
        print(row)

    print(f"  {'-' * 80}")

    # Design-Strukturvergleich
    print(f"\n  DESIGN-STRUKTUR")
    print(f"  {'-' * 60}")
    row = f"  {'Eigenschaft':<30}"
    for dk in designs:
        row += f"  {'Design ' + dk:>{col_w}}"
    print(row)
    print(f"  {'-' * 60}")

    struct_keys = [
        ("Winding-Segmente",   "n_winding"),
        ("Return-Segmente",    "n_return"),
        ("L_self [µH]",        "l_self_uH"),
        ("L_vias [µH]",        "l_vias_uH"),
        ("L_mutual [µH]",      "l_mutual_uH"),
        ("C_coupling [pF]",    "c_coupling_pF"),
        ("C_interturn [pF]",   "c_interturn_pF"),
        ("C_via [pF]",         "c_via_pF"),
        ("p/W Verhältnis",     "pitch_over_w"),
    ]
    for label, key in struct_keys:
        row = f"  {label:<30}"
        for r in results:
            v = r["geometry"].get(key)
            if v is not None:
                if isinstance(v, int):
                    row += f"  {v:>{col_w}d}"
                elif isinstance(v, bool):
                    row += f"  {str(v):>{col_w}}"
                else:
                    row += f"  {v:>{col_w}.4f}"
            else:
                row += f"  {'---':>{col_w}}"
        print(row)
    print(f"  {'-' * 60}\n")


# ---------------------------------------------------------------------------
# Visualisierung
# ---------------------------------------------------------------------------

def _create_plots(results: list[dict], output_dir: Path, show: bool) -> None:
    """Erzeugt Vergleichsplots für alle Parameter."""

    try:
        import matplotlib
        if not show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("  [WARN]  matplotlib nicht installiert – keine Plots.")
        return

    designs = [f"Design {r['design']}" for r in results]
    n_designs = len(designs)
    x = np.arange(n_designs)

    # Farbschema
    c_geom = "#2196F3"   # Blau
    c_fit  = "#FF9800"   # Orange
    c_meas = "#4CAF50"   # Grün

    # ======================================================================
    # Plot 1: Balkendiagramm – L, R, C, f_res (4 Subplots)
    # ======================================================================
    fig1, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig1.suptitle(
        "Parametervergleich – Geometrie vs. Fit vs. Messung",
        fontsize=15, fontweight="bold", y=0.98,
    )

    bar_w = 0.22

    # --- L [µH] ---
    ax = axes[0, 0]
    g_vals = [r["geometry"]["L_uH"] for r in results]
    f_vals = [r["fit"]["L_uH"] if r["fit"]["L_uH"] else 0 for r in results]
    m_vals = [r["reference"].get("l_uH", 0) for r in results]

    ax.bar(x - bar_w, g_vals, bar_w, label="Geometrie", color=c_geom, edgecolor="white", zorder=3)
    ax.bar(x,         f_vals, bar_w, label="Fit",       color=c_fit,  edgecolor="white", zorder=3)
    ax.bar(x + bar_w, m_vals, bar_w, label="Messung",   color=c_meas, edgecolor="white", zorder=3)
    ax.set_ylabel("L [µH]", fontsize=11)
    ax.set_title("Induktivität L", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(designs)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    # Werte auf Balken
    for i, (gv, fv, mv) in enumerate(zip(g_vals, f_vals, m_vals)):
        ax.text(i - bar_w, gv, f"{gv:.3f}", ha="center", va="bottom", fontsize=7)
        ax.text(i,         fv, f"{fv:.3f}", ha="center", va="bottom", fontsize=7)
        ax.text(i + bar_w, mv, f"{mv:.3f}", ha="center", va="bottom", fontsize=7)

    # --- R [Ω] ---
    ax = axes[0, 1]
    g_vals = [r["geometry"]["R_dc_ohm"] for r in results]
    f_vals = [r["fit"]["R_dc_ohm"] if r["fit"]["R_dc_ohm"] else 0 for r in results]
    m_vals = [r["reference"].get("r_ohm", 0) for r in results]

    ax.bar(x - bar_w, g_vals, bar_w, label="Geometrie", color=c_geom, edgecolor="white", zorder=3)
    ax.bar(x,         f_vals, bar_w, label="Fit",       color=c_fit,  edgecolor="white", zorder=3)
    ax.bar(x + bar_w, m_vals, bar_w, label="Messung",   color=c_meas, edgecolor="white", zorder=3)
    ax.set_ylabel("R [Ω]", fontsize=11)
    ax.set_title("Serienwiderstand R", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(designs)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    for i, (gv, fv, mv) in enumerate(zip(g_vals, f_vals, m_vals)):
        ax.text(i - bar_w, gv, f"{gv:.2f}", ha="center", va="bottom", fontsize=7)
        ax.text(i,         fv, f"{fv:.2f}", ha="center", va="bottom", fontsize=7)
        ax.text(i + bar_w, mv, f"{mv:.2f}", ha="center", va="bottom", fontsize=7)

    # --- C [pF] ---
    ax = axes[1, 0]
    g_vals = [r["geometry"]["C_pF"] for r in results]
    f_vals = [r["fit"]["C_pF"] if r["fit"]["C_pF"] else 0 for r in results]
    m_vals = [r["reference"].get("c_pF", 0) for r in results]

    ax.bar(x - bar_w, g_vals, bar_w, label="Geometrie", color=c_geom, edgecolor="white", zorder=3)
    ax.bar(x,         f_vals, bar_w, label="Fit",       color=c_fit,  edgecolor="white", zorder=3)
    ax.bar(x + bar_w, m_vals, bar_w, label="Messung",   color=c_meas, edgecolor="white", zorder=3)
    ax.set_ylabel("C [pF]", fontsize=11)
    ax.set_title("Parasitäre Kapazität C", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(designs)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    for i, (gv, fv, mv) in enumerate(zip(g_vals, f_vals, m_vals)):
        ax.text(i - bar_w, gv, f"{gv:.1f}", ha="center", va="bottom", fontsize=7)
        ax.text(i,         fv, f"{fv:.1f}", ha="center", va="bottom", fontsize=7)
        ax.text(i + bar_w, mv, f"{mv:.1f}", ha="center", va="bottom", fontsize=7)

    # --- f_res [MHz] ---
    ax = axes[1, 1]
    g_vals = [r["geometry"]["f_res_MHz"] for r in results]
    f_vals = [r["fit"]["f_res_MHz"] if r["fit"]["f_res_MHz"] else 0 for r in results]
    m_vals = []
    for r in results:
        ref = r["reference"]
        if ref.get("l_uH") and ref.get("c_pF"):
            m_vals.append(1.0 / (2 * np.pi * np.sqrt(
                ref["l_uH"] * 1e-6 * ref["c_pF"] * 1e-12)) / 1e6)
        else:
            m_vals.append(0)

    ax.bar(x - bar_w, g_vals, bar_w, label="Geometrie", color=c_geom, edgecolor="white", zorder=3)
    ax.bar(x,         f_vals, bar_w, label="Fit",       color=c_fit,  edgecolor="white", zorder=3)
    ax.bar(x + bar_w, m_vals, bar_w, label="Messung",   color=c_meas, edgecolor="white", zorder=3)
    ax.set_ylabel("f_res [MHz]", fontsize=11)
    ax.set_title("Resonanzfrequenz f_res", fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(designs)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    for i, (gv, fv, mv) in enumerate(zip(g_vals, f_vals, m_vals)):
        ax.text(i - bar_w, gv, f"{gv:.1f}", ha="center", va="bottom", fontsize=7)
        ax.text(i,         fv, f"{fv:.1f}", ha="center", va="bottom", fontsize=7)
        ax.text(i + bar_w, mv, f"{mv:.1f}", ha="center", va="bottom", fontsize=7)

    fig1.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    out1 = output_dir / "vergleich_parameter_balken.png"
    fig1.savefig(out1, dpi=180, bbox_inches="tight")
    print(f"  [PLOT]  {out1.relative_to(_ROOT)}")

    # ======================================================================
    # Plot 2: Relativer Fehler zur Messung (Heatmap-artig)
    # ======================================================================
    fig2, ax2 = plt.subplots(figsize=(10, 5))
    fig2.suptitle(
        "Relativer Fehler zur Bode100-Messung [%]",
        fontsize=14, fontweight="bold",
    )

    param_labels = ["L [µH]", "R [Ω]", "C [pF]"]
    param_keys_g = ["L_uH", "R_dc_ohm", "C_pF"]
    param_keys_r = ["l_uH", "r_ohm",    "c_pF"]

    n_params = len(param_labels)
    bar_w2 = 0.35

    # Gruppierte Balken: je Parameter zwei Gruppen (Geom, Fit) × n_designs
    x2 = np.arange(n_params)
    offsets = np.linspace(-0.3, 0.3, n_designs * 2)

    colors_design = ["#1976D2", "#E64A19", "#388E3C"]  # D1=blau, D2=rot, D3=grün

    w_bar = 0.12
    for di, r in enumerate(results):
        dk = r["design"]
        ref = r["reference"]
        geom_errs = []
        fit_errs = []
        for gk, rk in zip(param_keys_g, param_keys_r):
            gv = r["geometry"].get(gk)
            fv = r["fit"].get(gk)
            rv = ref.get(rk)
            geom_errs.append(_pct_err(gv, rv) if gv and rv else 0)
            fit_errs.append(_pct_err(fv, rv)  if fv and rv else 0)

        offset_g = -0.2 + di * 0.15
        offset_f = offset_g + 0.07

        c_base = colors_design[di % len(colors_design)]
        bars_g = ax2.bar(x2 + offset_g, geom_errs, w_bar,
                         label=f"D{dk} Geometrie", color=c_base, alpha=0.7,
                         edgecolor="white", zorder=3)
        bars_f = ax2.bar(x2 + offset_f, fit_errs, w_bar,
                         label=f"D{dk} Fit", color=c_base, alpha=0.35,
                         edgecolor=c_base, hatch="//", zorder=3)

        # Werte auf Balken
        for bar, val in zip(bars_g, geom_errs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                     f"{val:+.1f}%", ha="center", va="bottom", fontsize=7)
        for bar, val in zip(bars_f, fit_errs):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                     f"{val:+.1f}%", ha="center", va="bottom", fontsize=7)

    ax2.axhline(0, color="black", linewidth=0.8)
    ax2.axhline(15, color="orange", linewidth=0.8, linestyle="--", alpha=0.5, label="±15% Schwelle")
    ax2.axhline(-15, color="orange", linewidth=0.8, linestyle="--", alpha=0.5)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(param_labels, fontsize=11)
    ax2.set_ylabel("Relativer Fehler [%]", fontsize=11)
    ax2.legend(fontsize=8, loc="best", ncol=2)
    ax2.grid(axis="y", alpha=0.3, zorder=0)

    fig2.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    out2 = output_dir / "vergleich_relativer_fehler.png"
    fig2.savefig(out2, dpi=180, bbox_inches="tight")
    print(f"  [PLOT]  {out2.relative_to(_ROOT)}")

    # ======================================================================
    # Plot 3: Radar-/Spiderplot – normierte Parameter pro Design
    # ======================================================================
    fig3, ax3 = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    fig3.suptitle(
        "Normierter Parametervergleich (Messung = 1.0)",
        fontsize=14, fontweight="bold",
    )

    radar_labels = ["L", "R", "C", "f_res"]
    radar_keys_g = ["L_uH", "R_dc_ohm", "C_pF", "f_res_MHz"]
    radar_keys_r = ["l_uH", "r_ohm",    "c_pF", None]

    angles = np.linspace(0, 2 * np.pi, len(radar_labels), endpoint=False).tolist()
    angles += angles[:1]  # Schließen

    for di, r in enumerate(results):
        dk = r["design"]
        ref = r["reference"]

        # f_res Referenz berechnen
        f_res_ref = None
        if ref.get("l_uH") and ref.get("c_pF"):
            f_res_ref = 1.0 / (2 * np.pi * np.sqrt(
                ref["l_uH"] * 1e-6 * ref["c_pF"] * 1e-12)) / 1e6

        # Normierte Werte (Geometrie / Messung)
        norm_geom = []
        norm_fit  = []
        for gk, rk in zip(radar_keys_g, radar_keys_r):
            gv = r["geometry"].get(gk)
            fv = r["fit"].get(gk)

            if rk is not None:
                rv = ref.get(rk)
            else:
                rv = f_res_ref

            if gv and rv and rv != 0:
                norm_geom.append(gv / rv)
            else:
                norm_geom.append(1.0)
            if fv and rv and rv != 0:
                norm_fit.append(fv / rv)
            else:
                norm_fit.append(1.0)

        norm_geom += norm_geom[:1]
        norm_fit  += norm_fit[:1]

        c = colors_design[di % len(colors_design)]
        ax3.plot(angles, norm_geom, "o-", color=c, linewidth=2,
                 label=f"D{dk} Geometrie", markersize=6)
        ax3.plot(angles, norm_fit, "s--", color=c, linewidth=1.5,
                 alpha=0.6, label=f"D{dk} Fit", markersize=5)

    # Referenzlinie (1.0)
    ref_line = [1.0] * (len(radar_labels) + 1)
    ax3.plot(angles, ref_line, "k--", linewidth=1.5, alpha=0.4, label="Messung (=1.0)")
    ax3.fill(angles, ref_line, alpha=0.05, color="gray")

    ax3.set_xticks(angles[:-1])
    ax3.set_xticklabels(radar_labels, fontsize=12, fontweight="bold")
    ax3.set_ylim(0, 2.0)
    ax3.set_yticks([0.5, 1.0, 1.5, 2.0])
    ax3.set_yticklabels(["0.5", "1.0", "1.5", "2.0"], fontsize=8)
    ax3.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=9)

    fig3.tight_layout()
    out3 = output_dir / "vergleich_radar.png"
    fig3.savefig(out3, dpi=180, bbox_inches="tight")
    print(f"  [PLOT]  {out3.relative_to(_ROOT)}")

    # ======================================================================
    # Plot 4: Induktivitäts-Aufschlüsselung (Stacked Bar)
    # ======================================================================
    fig4, (ax4a, ax4b) = plt.subplots(1, 2, figsize=(14, 6))
    fig4.suptitle(
        "Aufschlüsselung der Ersatzschaltparameter nach Beiträgen",
        fontsize=14, fontweight="bold",
    )

    # L-Aufschlüsselung
    l_self   = [r["geometry"]["l_self_uH"] for r in results]
    l_vias   = [r["geometry"]["l_vias_uH"] for r in results]
    l_mutual = [r["geometry"]["l_mutual_uH"] for r in results]

    ax4a.bar(x, l_self,   0.5, label="L_self (Rühli)", color="#2196F3", edgecolor="white", zorder=3)
    ax4a.bar(x, l_vias,   0.5, bottom=l_self, label="L_vias", color="#64B5F6", edgecolor="white", zorder=3)
    ax4a.bar(x, l_mutual, 0.5,
             bottom=[s + v for s, v in zip(l_self, l_vias)],
             label="L_mutual (PEEC)", color="#90CAF9", edgecolor="white", zorder=3)

    # Messwert als horizontale Linie
    for i, r in enumerate(results):
        m = r["reference"].get("l_uH")
        if m:
            ax4a.plot([i-0.3, i+0.3], [m, m], "r-", linewidth=2.5, zorder=5)
            if i == 0:
                ax4a.plot([], [], "r-", linewidth=2.5, label="Messung")

    ax4a.set_ylabel("L [µH]", fontsize=11)
    ax4a.set_title("Induktivität – Beiträge", fontsize=12, fontweight="bold")
    ax4a.set_xticks(x)
    ax4a.set_xticklabels(designs)
    ax4a.legend(fontsize=9)
    ax4a.grid(axis="y", alpha=0.3, zorder=0)

    # C-Aufschlüsselung
    c_coupling   = [r["geometry"]["c_coupling_pF"] for r in results]
    c_interturn  = [r["geometry"]["c_interturn_pF"] for r in results]
    c_via        = [r["geometry"]["c_via_pF"] for r in results]

    ax4b.bar(x, c_coupling,  0.5, label="C_coupling", color="#FF9800", edgecolor="white", zorder=3)
    ax4b.bar(x, c_interturn, 0.5, bottom=c_coupling, label="C_interturn", color="#FFB74D", edgecolor="white", zorder=3)
    ax4b.bar(x, c_via,       0.5,
             bottom=[c + ci for c, ci in zip(c_coupling, c_interturn)],
             label="C_via", color="#FFE0B2", edgecolor="white", zorder=3)

    for i, r in enumerate(results):
        m = r["reference"].get("c_pF")
        if m:
            ax4b.plot([i-0.3, i+0.3], [m, m], "r-", linewidth=2.5, zorder=5)
            if i == 0:
                ax4b.plot([], [], "r-", linewidth=2.5, label="Messung")

    ax4b.set_ylabel("C [pF]", fontsize=11)
    ax4b.set_title("Kapazität – Beiträge", fontsize=12, fontweight="bold")
    ax4b.set_xticks(x)
    ax4b.set_xticklabels(designs)
    ax4b.legend(fontsize=9)
    ax4b.grid(axis="y", alpha=0.3, zorder=0)

    fig4.tight_layout(rect=(0.0, 0.0, 1.0, 0.93))
    out4 = output_dir / "vergleich_aufschluesselung.png"
    fig4.savefig(out4, dpi=180, bbox_inches="tight")
    print(f"  [PLOT]  {out4.relative_to(_ROOT)}")

    # ======================================================================
    # Plot 5: Designvergleich – Tabelle als Plot (für Diplomarbeit)
    # ======================================================================
    fig5, ax5 = plt.subplots(figsize=(14, 7))
    ax5.axis("off")
    fig5.suptitle(
        "Zusammenfassung – Ersatzschaltparameter Design 1 & 2",
        fontsize=14, fontweight="bold",
    )

    # Tabellendaten aufbauen
    col_labels = ["Parameter", "Einheit"]
    for r in results:
        dk = r["design"]
        col_labels += [f"D{dk} Geom.", f"D{dk} Fit", f"D{dk} Mess.", f"D{dk} Err_G", f"D{dk} Err_F"]

    def _f(v, fmt=".4f"):
        return format(v, fmt) if v is not None else "—"

    def _e(calc, ref):
        if calc is None or ref is None or ref == 0:
            return "—"
        return f"{_pct_err(calc, ref):+.1f}%"

    table_data = []

    # L
    row = ["L", "µH"]
    for r in results:
        g, f, m = r["geometry"]["L_uH"], r["fit"]["L_uH"], r["reference"].get("l_uH")
        row += [_f(g), _f(f), _f(m), _e(g, m), _e(f, m)]
    table_data.append(row)

    # R
    row = ["R_s", "Ω"]
    for r in results:
        g, f, m = r["geometry"]["R_dc_ohm"], r["fit"]["R_dc_ohm"], r["reference"].get("r_ohm")
        row += [_f(g), _f(f), _f(m), _e(g, m), _e(f, m)]
    table_data.append(row)

    # C
    row = ["C", "pF"]
    for r in results:
        g, f, m = r["geometry"]["C_pF"], r["fit"]["C_pF"], r["reference"].get("c_pF")
        row += [_f(g), _f(f), _f(m), _e(g, m), _e(f, m)]
    table_data.append(row)

    # f_res
    row = ["f_res", "MHz"]
    for r in results:
        ref = r["reference"]
        f_res_ref = None
        if ref.get("l_uH") and ref.get("c_pF"):
            f_res_ref = 1.0 / (2 * np.pi * np.sqrt(
                ref["l_uH"] * 1e-6 * ref["c_pF"] * 1e-12)) / 1e6
        g = r["geometry"]["f_res_MHz"]
        f = r["fit"]["f_res_MHz"]
        row += [_f(g, ".3f"), _f(f, ".3f"), _f(f_res_ref, ".3f"),
                _e(g, f_res_ref), _e(f, f_res_ref)]
    table_data.append(row)

    # N_winding
    row = ["N_winding", "—"]
    for r in results:
        n = r["geometry"]["n_winding"]
        row += [str(n), "—", "—", "—", "—"]
    table_data.append(row)

    # N_return
    row = ["N_return", "—"]
    for r in results:
        n = r["geometry"]["n_return"]
        row += [str(n), "—", "—", "—", "—"]
    table_data.append(row)

    tbl = ax5.table(
        cellText=table_data,
        colLabels=col_labels,
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1.0, 1.6)

    # Header-Zeile färben
    for j in range(len(col_labels)):
        tbl[0, j].set_facecolor("#37474F")
        tbl[0, j].set_text_props(color="white", fontweight="bold")

    # Fehler-Spalten einfärben
    for i in range(1, len(table_data) + 1):
        for j in range(len(col_labels)):
            cell = tbl[i, j]
            text = cell.get_text().get_text()
            if "%" in text:
                try:
                    val = float(text.replace("%", "").replace("+", ""))
                    if abs(val) > 30:
                        cell.set_facecolor("#FFCDD2")  # rot
                    elif abs(val) > 15:
                        cell.set_facecolor("#FFF9C4")  # gelb
                    else:
                        cell.set_facecolor("#C8E6C9")  # grün
                except ValueError:
                    pass

    fig5.tight_layout()
    out5 = output_dir / "vergleich_tabelle.png"
    fig5.savefig(out5, dpi=180, bbox_inches="tight")
    print(f"  [PLOT]  {out5.relative_to(_ROOT)}")

    # Alle Plots anzeigen
    if show:
        plt.show()

    print(f"\n  Alle Plots gespeichert in: {output_dir.relative_to(_ROOT)}/")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parametervergleich aller PCB-Rogowski-Designs (Geometrie / Fit / Messung)",
    )
    parser.add_argument(
        "--designs", "-d", nargs="+", default=["1", "2"],
        help="Design-Nummern zum Vergleichen (Standard: 1 2)",
    )
    parser.add_argument(
        "--f-max", type=float, default=10e6,
        help="Obere Fit-Frequenz [Hz] (Standard: 10 MHz)",
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Plots interaktiv anzeigen (sonst nur speichern).",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path,
        default=_ROOT / "output",
        help="Ausgabeverzeichnis für Plots.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Daten sammeln (Berechnung + Fit)
    results = _collect_data(args.designs, args.f_max)

    if not results:
        print("\n  [FEHLER]  Keine Ergebnisse erzeugt.")
        return 1

    # 2. Konsolen-Zusammenfassung
    _print_summary(results)

    # 3. Plots erzeugen
    _create_plots(results, output_dir, show=args.show)

    print(f"\n{'='*80}")
    print(f"  Vergleich abgeschlossen für Designs: {', '.join(args.designs)}")
    print(f"{'='*80}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
