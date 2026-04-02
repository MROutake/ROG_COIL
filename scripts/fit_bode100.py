#!/usr/bin/env python
"""
fit_bode100.py  -  PEEC-Light Modell + Bode100-Fit fuer PCB-Rogowski-Spulen.

Workflow:
    1. Gerber laden + manuelle Klassifikation aus YAML
    2. Segmente mit gamma-Gewichten extrahieren:
           winding  sigma=+1 -> gamma=+1   (aktive Windung)
           winding  sigma=-1 -> gamma=-1   (umgekehrte Wickelrichtung)
           return           -> gamma=-1   (Rueckleiterkompensation)
           connection       -> gamma= 0   (Zuleitung, kein Beitrag)
    3. PEEC:  L_eq = gamma^T * M * gamma  (mit gegenseitiger Induktivitaet)
    4. C_total = C_plane + C_fringe + C_via + C_interturn
    5. Bode100-Fit:  Z(f) = R_s(f) + j*omega*L + 1/(j*omega*C)
       Fit-Parameter: L, R_dc, k_skin, k_prox, C
       KEIN paralleler Widerstand R_p.
    6. Vergleichstabelle  Berechnung vs. Fit vs. Messung
    7. Optional: Impedanzplot (.png)

Verwendung:
    python scripts/fit_bode100.py
    python scripts/fit_bode100.py --design 3 --plot
    python scripts/fit_bode100.py --f-max 12e6 --output output/fit.json
    python scripts/fit_bode100.py --design all --plot --f-max 8e6
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# Windows: stdout auf UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer,
                                  encoding="utf-8", errors="replace")

import numpy as np

from pcb_rogowski.domain.board.models import Board, Layer, LayerType
from pcb_rogowski.domain.coil.capacitance import CapacitanceConfig, compute_capacitance
from pcb_rogowski.domain.coil.fitting import (
    FitResult, fit_bode100, load_bode100_csv, z_rlc_series,
    estimate_from_data,
)
from pcb_rogowski.domain.coil.inductance import compute_inductance
from pcb_rogowski.domain.coil.peec import Segment
from pcb_rogowski.domain.coil.skin import SkinModelConfig, r_vias as _r_vias_dc
from pcb_rogowski.domain.trace.classifier import (
    ClassificationSpec, ClassifierConfig,
    FishboneClassifier, TopologyGapFiller,
)
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.infrastructure.stackup.loader import StackupLoader

# ---------------------------------------------------------------------------
# Design-Konfiguration
# ---------------------------------------------------------------------------

_GERBER_ROOT  = _ROOT / "data_samples" / "gerber"
_BODE_ROOT    = _ROOT / "data_samples" / "Bode100"
_STACKUP_YAML = _ROOT / "configs" / "stackup_design03.yaml"
_DEFAULTS_YAML = _ROOT / "configs" / "defaults.yaml"

# Beste (vollstaendigste) CSV pro Design
_BODE_CSV: dict[str, Path] = {
    "1": _BODE_ROOT / "Desgin_01" / "Measurement_RogDual_limit_12MHz (1).csv",
    "2": _BODE_ROOT / "Desgin_02" / "Design2 (1).csv",
    "3": _BODE_ROOT / "Desgin_03" / "Design3 (1).csv",
}

# Bode100-Referenzwerte aus Einzelpunkt-Fit (anderes Analysewerkzeug)
# Modell: R_s in Serie mit L, parallel zu C  (kein R_p)
_BODE_REF: dict[str, dict] = {
    "1": dict(l_uH=2.006,    r_ohm=5.200,  c_pF=86.092),
    "2": dict(l_uH=0.398537, r_ohm=2.028,  c_pF=12.314),
    "3": dict(l_uH=0.410644, r_ohm=2.116,  c_pF=12.902),
}

_SEP  = "-" * 82
_SEP2 = "=" * 82


def _key(name: str) -> str | None:
    m = re.search(r"(\d+)", name)
    return str(int(m.group(1))) if m else None


def _pct(calc: float, meas: float) -> str:
    if meas == 0:
        return "  n/a "
    v = (calc - meas) / meas * 100.0
    sign = "+" if v >= 0 else ""
    mark = "  !!" if abs(v) > 30 else ("  !" if abs(v) > 15 else "")
    return f"{sign}{v:.1f}%{mark}"


# ---------------------------------------------------------------------------
# Segmente aus Board + Klassifikation extrahieren
# ---------------------------------------------------------------------------

_RHO_CU = 1.72e-8    # Ω·m Kupfer bei 20 °C


def _build_segments(
    board: Board,
    spec: ClassificationSpec,
    t_cu_m: float,
    layer_heights_m: dict[str, float],
) -> tuple[list[Segment], list[Segment]]:
    """
    Erzeugt PEEC-Segmente, getrennt in Windungs- und Rueckleiter-Segmente.

    Gamma-Regeln (physikalisch korrekt):
      winding  sigma=+1  -> gamma = +1.0   (Stromrichtung vorwaerts)
      winding  sigma=-1  -> gamma = -1.0   (Stromrichtung rueckwaerts)
      return   beliebig  -> gamma = -1.0   (Rueckleiter kompensiert Fluss immer,
                                            sigma wird ignoriert)
      connection/andere  -> uebersprungen  (kein Beitrag zur Induktivitaet)

    Returns:
        (winding_segs, return_segs)
        winding_segs: fuer PEEC + Kapazitaet + R_dc-Berechnung
        return_segs:  nur fuer PEEC (L-Kompensation)
    """
    entry_map = {e.feature_id: e for e in spec.entries}
    mm = 1e-3
    winding_segs: list[Segment] = []
    return_segs:  list[Segment] = []

    for layer in board.layers:
        if layer.layer_type != LayerType.COPPER:
            continue
        z = layer_heights_m.get(layer.name, 0.0)

        for feat in layer.lines:
            entry = entry_map.get(feat.feature_id)
            if entry is None:
                continue

            role = entry.role
            if role not in ("winding", "return"):
                continue  # connection / unclassified ueberspringen

            if role == "winding":
                sigma = entry.sigma if entry.sigma != 0 else 1
                gamma = float(sigma)   # +1 oder -1
            else:
                gamma = -1.0           # return immer -1, sigma irrelevant

            w = feat.width_mm * mm if feat.width_mm > 0 else 0.2 * mm

            seg = Segment(
                x1=feat.start.x_mm * mm,
                y1=feat.start.y_mm * mm,
                z1=z,
                x2=feat.end.x_mm * mm,
                y2=feat.end.y_mm * mm,
                z2=z,
                width=w,
                thickness=t_cu_m,
                gamma=gamma,
                layer=layer.name,
            )
            if role == "winding":
                winding_segs.append(seg)
            else:
                return_segs.append(seg)

    return winding_segs, return_segs


def _count_vias(board: Board) -> int:
    """Zaehlt Vias (PTH) im Board."""
    return sum(
        sum(1 for p in la.pads if p.is_via)
        for la in board.layers
    )


def _count_nearest_pairs(segs: list[Segment], threshold_m: float = 0.4e-3) -> int:
    """Segmentpaare mit Mittelpunktsabstand < threshold (Interturn-Kapazitaet)."""
    if len(segs) < 2:
        return 0
    mids = np.array([s.midpoint for s in segs])
    # Abstandsmatrix (nur oberes Dreieck)
    count = 0
    for i in range(len(mids)):
        dists = np.linalg.norm(mids[i + 1:] - mids[i], axis=1)
        count += int(np.sum(dists < threshold_m))
    return count


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def _save_plot(
    df,
    fit: FitResult,
    geom: dict,
    design_key: str,
    f_max_hz: float,
    output_dir: Path,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [PLOT]  matplotlib nicht verfuegbar - uebersprungen")
        return

    f_pl   = df["freq_hz"].to_numpy()
    z_meas = df["re_ohm"].to_numpy() + 1j * df["im_ohm"].to_numpy()
    z_fit  = z_rlc_series(f_pl, fit.L_uH * 1e-6, fit.R_dc_ohm,
                           fit.k_skin, fit.k_prox, fit.C_pF * 1e-12)
    # Geometrie-Modell: k_skin=k_prox=0 (DC-Naeherung)
    z_geom = z_rlc_series(f_pl, geom["l_uH"] * 1e-6, geom["r_dc_ohm"],
                           0.0, 0.0, geom["c_pF"] * 1e-12)

    # Layout: Plots links (col 0), Parameter rechts (col 1)
    fig = plt.figure(figsize=(15, 7))
    gs = fig.add_gridspec(2, 2, width_ratios=[3, 1.2], hspace=0.08, wspace=0.30)

    ax1 = fig.add_subplot(gs[0, 0])
    ax2 = fig.add_subplot(gs[1, 0], sharex=ax1)
    ax_info = fig.add_subplot(gs[:, 1])   # rechte Spalte fuer Parameter
    ax_info.axis("off")

    fig.suptitle(
        f"Design {design_key}  —  Messung  vs.  Fit  vs.  Geometrie-Berechnung",
        fontsize=13,
    )

    ax1.semilogx(f_pl, np.abs(z_meas), "b-",  lw=2.0, label="Messung (Bode100)")
    ax1.semilogx(f_pl, np.abs(z_fit),  "r--", lw=1.8, label="Fit (scipy)")
    ax1.semilogx(f_pl, np.abs(z_geom), "g:",  lw=1.8, label="Geometrie")
    ax1.set_ylabel("|Z| [Ohm]")
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(True, which="both", alpha=0.3)
    plt.setp(ax1.get_xticklabels(), visible=False)

    ax2.semilogx(f_pl, np.angle(z_meas, deg=True), "b-",  lw=2.0)
    ax2.semilogx(f_pl, np.angle(z_fit,  deg=True), "r--", lw=1.8)
    ax2.semilogx(f_pl, np.angle(z_geom, deg=True), "g:",  lw=1.8)
    ax2.set_ylabel("Phase [deg]")
    ax2.set_xlabel("Frequenz [Hz]")
    ax2.grid(True, which="both", alpha=0.3)

    # Parameter-Textbox rechts neben dem Plot
    info_text = (
        r"$\bf{Fit\ (scipy):}$" "\n"
        f"  L       = {fit.L_uH:.4f} µH\n"
        f"  R_dc  = {fit.R_dc_ohm:.4f} Ω\n"
        f"  C       = {fit.C_pF:.4f} pF\n"
        f"  f_res  = {fit.f_res_MHz:.3f} MHz\n"
        f"  RMSE = {fit.rmse_mag_pct:.2f} %\n"
        "\n"
        r"$\bf{Geometrie:}$" "\n"
        f"  L       = {geom['l_uH']:.4f} µH\n"
        f"  R_dc  = {geom['r_dc_ohm']:.4f} Ω\n"
        f"  C       = {geom['c_pF']:.4f} pF\n"
        f"  f_res  = {geom['f_res_mhz']:.3f} MHz"
    )
    ax_info.text(
        0.08, 0.95, info_text,
        transform=ax_info.transAxes,
        va="top", ha="left",
        fontsize=10, family="monospace",
        bbox=dict(boxstyle="round,pad=0.6", fc="#f8f8f8", ec="#cccccc",
                  alpha=0.95),
    )

    fig.subplots_adjust(left=0.07, right=0.98, top=0.92, bottom=0.09)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"fit_design_{design_key}.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  [PLOT]  Gespeichert: {out.relative_to(_ROOT)}")


# ---------------------------------------------------------------------------
# Einzelnes Design verarbeiten
# ---------------------------------------------------------------------------

def process_design(
    design_key: str,
    f_max_hz: float,
    do_plot: bool,
    output_dir: Path | None,
) -> dict:
    print(f"\n{_SEP2}")
    print(f"  Design {design_key}")
    print(_SEP2)

    # --- Pfade ---
    gerber_dir = _GERBER_ROOT / f"Desgin_0{design_key}"
    yaml_path  = gerber_dir / "classification_draft.yaml"
    bode_path  = _BODE_CSV.get(design_key)

    if not gerber_dir.exists():
        print(f"  [FEHLER]  Verzeichnis nicht gefunden: {gerber_dir}")
        return {}

    # --- Board laden ---
    board = GerberBoardLoader().load_from_gerber(gerber_dir)
    n_lines = sum(len(la.lines) for la in board.layers)
    print(f"  Board:          {n_lines} Segmente auf {len(board.layers)} Lagen")

    # --- Klassifikation ---
    if yaml_path.exists():
        spec = ClassificationSpec.from_yaml(yaml_path)
        n_manual = sum(1 for e in spec.entries
                       if e.note and e.note.startswith("manuell"))
        spec = TopologyGapFiller().fill(board, spec)
        print(f"  Klassifikation: YAML  ({n_manual} manuell)  "
              f"Rollen: {spec.role_counts()}")
    else:
        cfg  = ClassifierConfig.from_yaml(_DEFAULTS_YAML)
        spec = FishboneClassifier(cfg).classify(board)
        print(f"  Klassifikation: AUTO  Rollen: {spec.role_counts()}")

    # --- Stackup ---
    stackup = StackupLoader.from_yaml(_STACKUP_YAML) if _STACKUP_YAML.exists() \
              else None

    # Stackup-Parameter extrahieren
    if stackup:
        t_cu_m = stackup.copper_layers[0].thickness_um * 1e-6  # µm -> m
        # Layer-Hoehenkoordinate im 3-D Raum (z=0 = Top)
        layer_z: dict[str, float] = {}
        z = 0.0
        for cu in sorted(stackup.copper_layers, key=lambda c: c.index):
            layer_z[cu.name] = z
            # Naechstes Dielektrikum dahinter
            for d in stackup.dielectrics:
                if d.between_layers and cu.name == d.between_layers[0]:
                    z += d.thickness_mm * 1e-3
                    break
        eps_r = stackup.dielectrics[0].epsilon_r if stackup.dielectrics else 4.5
        h_via_m = stackup.total_thickness_mm * 1e-3
    else:
        t_cu_m  = 0.035e-3
        layer_z    = {"top_layer": 0.0, "bottom_layer": 1.6e-3}
        eps_r      = 4.5
        h_via_m    = 1.6e-3

    # --- Segmente extrahieren ---
    winding_segs, return_segs = _build_segments(board, spec, t_cu_m, layer_z)
    all_segs = winding_segs + return_segs
    print(f"  Segmente:       {len(winding_segs)} Winding  +  "
          f"{len(return_segs)} Return  =  {len(all_segs)} gesamt")

    if not all_segs:
        print("  [SKIP]  Keine aktiven Segmente.")
        return {}

    # --- Induktivitaet (Self-L + Vias, ggf. Mutual bei p/W < 8) ---
    n_vias  = _count_vias(board)
    via_pads_all = [p for la in board.layers for p in la.pads
                    if p.is_via and p.diameter_mm > 0]
    d_via_m = (sum(p.diameter_mm for p in via_pads_all) / len(via_pads_all) * 1e-3
               if via_pads_all else 0.2e-3)

    # Via-Hoehe = h_diel (Abstand benachbarter Lagen), NICHT volle Boardhoehe
    h_diel_m = next(
        (d.thickness_mm * 1e-3 for d in stackup.dielectrics),
        0.32e-3
    ) if stackup else 0.32e-3

    ind = compute_inductance(
        winding_segs=winding_segs,
        return_segs=return_segs,
        n_vias=n_vias,
        via_height_m=h_diel_m,
        via_diameter_m=d_via_m,
    )
    print(f"  Induktivitaet:  {ind.summary()}")

    # --- Kapazitaet (ohne Grundebene! C_coupling zur Innenlage dominant) ---
    n_pairs = _count_nearest_pairs(winding_segs)

    cap_cfg = CapacitanceConfig(
        eps_r=eps_r,
        gap_interturn_m=0.2e-3,   # typischer Spalt zwischen Windungszaehnen
        h_diel_m=h_diel_m,        # Abstand zur naechsten Kupferlage (0.32 mm)
        c_via_fF=30.0,
    )
    cap = compute_capacitance(
        segment_lengths_m=[s.length for s in winding_segs],
        segment_widths_m=[s.width  for s in winding_segs],
        n_vias=n_vias,
        n_interturn_pairs=n_pairs,
        cfg=cap_cfg,
    )
    print(f"  Kapazitaet:     {cap.summary()}")

    # --- Geometrische R_dc und f_res ---
    # Winding und Return liegen in Serie -> R_gesamt = R_winding + R_return
    r_dc_trace = _RHO_CU * sum(
        s.length / max(s.width * s.thickness, 1e-20)
        for s in winding_segs + return_segs
    )
    # Via-DC-Widerstand  (Plating-Dicke: Standard PCB = 25 µm)
    via_pads = [p for la in board.layers for p in la.pads if p.is_via and p.diameter_mm > 0]
    d_via_m  = (sum(p.diameter_mm for p in via_pads) / len(via_pads) * 1e-3
                if via_pads else 0.2e-3)
    r_dc_via = _r_vias_dc(
        h_via_m=h_via_m,
        d_via_m=d_via_m,
        t_plating_m=25e-6,      # Standard PCB: 1 oz Plating
        n_vias=n_vias,
        f=1.0,                  # DC-Naeherung (f sehr klein)
        cfg=SkinModelConfig(),
    )
    r_dc_geom = r_dc_trace + r_dc_via
    f_res_geom_mhz = (
        1.0 / (2.0 * np.pi * np.sqrt(
            ind.l_total_uH * 1e-6 * cap.c_total_pF * 1e-12
        )) / 1e6
        if ind.l_total_uH > 0 and cap.c_total_pF > 0 else 0.0
    )
    geom_params = dict(
        l_uH=ind.l_total_uH,
        r_dc_ohm=r_dc_geom,
        c_pF=cap.c_total_pF,
        f_res_mhz=f_res_geom_mhz,
    )
    print(f"  Geom. Params:   R_dc={r_dc_geom:.4f} Ohm  "
          f"f_res={f_res_geom_mhz:.3f} MHz")

    # --- Bode100-Fit ---
    fit: FitResult | None = None
    df_bode = None

    if bode_path and bode_path.exists():
        df_bode = load_bode100_csv(bode_path)
        print(f"  Bode100-CSV:    {bode_path.name}  ({len(df_bode)} Punkte)")

        # Startwerte direkt aus Messdaten schaetzen (unabhaengig von PEEC)
        L0, R0, C0 = estimate_from_data(df_bode)
        f_res0 = 1.0 / (2.0 * np.pi * np.sqrt(L0 * C0)) / 1e6
        print(f"  Auto-Init:      L={L0*1e6:.4f} uH  R={R0:.4f} Ohm  "
              f"C={C0*1e12:.3f} pF  f_res~{f_res0:.2f} MHz")

        # Vollen Messbereich nutzen (bis 50 MHz) fuer gute C-Sensitivitaet
        f_max_fit = float(df_bode["freq_hz"].max())
        fit = fit_bode100(
            df          = df_bode,
            l0_H        = L0,
            r0_ohm      = R0,
            c0_F        = C0,
            f_min_hz    = 100.0,
            f_max_hz    = f_max_fit,
            weight_imag = 1.0,
        )
        print(f"\n  Fit-Ergebnis:")
        print(fit.summary())

        if do_plot and df_bode is not None:
            out_dir = output_dir or (_ROOT / "output")
            _save_plot(df_bode, fit, geom_params, design_key, f_max_hz, out_dir)
    else:
        print(f"  [INFO]  Keine Bode100-CSV gefunden: {bode_path}")

    # --- Vergleichstabelle ---
    ref = _BODE_REF.get(design_key, {})
    f_res_ref = (
        1.0 / (2.0 * np.pi * np.sqrt(
            ref["l_uH"] * 1e-6 * ref["c_pF"] * 1e-12
        )) / 1e6
        if ref.get("l_uH") and ref.get("c_pF") else None
    )

    print(f"\n  {'Parameter':<14} {'Geometrie':>12} {'Fit':>12} "
          f"{'Referenz':>12} {'Err Geom':>10} {'Err Fit':>10}")
    print(f"  {'-' * 72}")

    def _row(label: str, geom_v, fit_v, ref_v, fmt: str = ".4f") -> None:
        g_s = format(geom_v, fmt) if geom_v is not None else "      ---"
        f_s = format(fit_v,  fmt) if fit_v  is not None else "      ---"
        r_s = format(ref_v,  fmt) if ref_v  is not None else "      ---"
        eg  = _pct(geom_v, ref_v) if (geom_v is not None and ref_v) else "      ---"
        ef  = _pct(fit_v,  ref_v) if (fit_v  is not None and ref_v) else "      ---"
        print(f"  {label:<14} {g_s:>12} {f_s:>12} {r_s:>12} {eg:>10} {ef:>10}")

    _row("L  [uH]",     ind.l_total_uH,
         fit.L_uH       if fit else None, ref.get("l_uH"))
    _row("C  [pF]",     cap.c_total_pF,
         fit.C_pF       if fit else None, ref.get("c_pF"))
    _row("R  [Ohm]",    r_dc_geom,
         fit.R_dc_ohm   if fit else None, ref.get("r_ohm"))
    _row("f_res [MHz]", f_res_geom_mhz,
         fit.f_res_MHz  if fit else None, f_res_ref, fmt=".3f")

    return {
        "design": design_key,
        "geometry": {
            "L_uH":          ind.l_total_uH,
            "l_self_uH":     ind.l_self_uH,
            "l_vias_uH":     ind.l_vias_uH,
            "l_mutual_uH":   ind.l_mutual_uH,
            "pitch_over_w":  ind.pitch_over_w,
            "piecewise_ok":  ind.piecewise_ok,
            "n_winding":     len(winding_segs),
            "n_return":      len(return_segs),
            "C_pF":          cap.c_total_pF,
            "c_coupling_pF": cap.c_coupling_pF,
            "c_interturn_pF": cap.c_interturn_pF,
            "c_layer_pF":    0.0,  # removed (no ground plane)
            "c_via_pF":      cap.c_via_pF,
            "R_dc_ohm":      r_dc_geom,
            "f_res_MHz":     f_res_geom_mhz,
        },
        "fit": {
            "L_uH":          fit.L_uH if fit else None,
            "R_dc_ohm":      fit.R_dc_ohm if fit else None,
            "k_skin":        fit.k_skin if fit else None,
            "k_prox":        fit.k_prox if fit else None,
            "C_pF":          fit.C_pF if fit else None,
            "f_res_MHz":     fit.f_res_MHz if fit else None,
            "rmse_mag_pct":  fit.rmse_mag_pct if fit else None,
        },
        "measured": ref,
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="PEEC-Light + Bode100-RLC-Serienfit fuer PCB-Rogowski-Spulen"
    )
    parser.add_argument(
        "--design", default="all",
        help="Design-Nummer: 1, 2, 3 oder 'all'  (default: all)",
    )
    parser.add_argument(
        "--f-max", type=float, default=10e6,
        help="Obere Fit-Frequenz [Hz]  (default: 10 MHz)",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Impedanzplot als PNG speichern (output/fit_design_X.png)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Ergebnisse als JSON speichern",
    )
    args = parser.parse_args()

    keys = ["1", "2", "3"] if args.design == "all" else [args.design]
    out_dir = Path(args.output).parent if args.output else None

    all_results = []
    for k in keys:
        try:
            r = process_design(k, args.f_max, args.plot, out_dir)
            if r:
                all_results.append(r)
        except Exception as exc:
            import traceback
            print(f"\n  [FEHLER] Design {k}: {exc}")
            traceback.print_exc()

    if args.output and all_results:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(all_results, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  [JSON]  {p}")

    print(f"\n{_SEP2}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
