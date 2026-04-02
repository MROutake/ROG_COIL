"""
Induktivitaet L_C fuer PCB-Rogowski-Spulen.

Modell (aus Vorlesung / Lorenz 1879 / Ruehli 1972):
    L_C = L_self + L_vias [+ L_mutual  (nur wenn p/W < 8)]

    L_self  = Σ_i  L_self,i    Freiraum-Eigeninduktivitaet (Ruehli/Lorenz)
    L_vias  = N * µ0·h/(2π) · (1 + ln(4h/d))
    L_mutual = γᵀMγ - Σ γ²·M_ii   (PEEC Kreuzterme, nur Nahfeld)

Pitch-Kriterium:
    p/W ≥ 8   → piecewise Modell (kein Mutual) genuegt
    p/W <  8   → PEEC Mutuals mit max_dist ≈ pitch hinzufuegen

Validierung gegen Bode100-Referenz:
    D2: -4.1%   D3: -5.4%   D1: -8.7%   (Self-L + L_vias, h=H_diel)

Referenzen:
    Ruehli, A.E. (1972): "Inductance Calculations in a Complex Integrated
    Circuit Environment", IBM Journal of Research & Development.
    Lorenz, L. (1879): Wied. Ann. Bd. VII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from pcb_rogowski.domain.coil.peec import (
    PEECInductanceCalculator,
    Segment,
    _self_inductance,
)

_MU0: float = 1.2566370614e-6  # H/m


# ---------------------------------------------------------------------------
# Ergebnis
# ---------------------------------------------------------------------------

@dataclass
class InductanceResult:
    """Aufschluesselung der berechneten Induktivitaet."""

    l_self_uH: float        # Eigeninduktivitaet Winding + Return  [µH]
    l_vias_uH: float        # Via-Induktivitaet                     [µH]
    l_mutual_uH: float      # PEEC-Mutual-Korrektur (0 wenn p/W>=8) [µH]
    l_total_uH: float       # L_self + L_vias + L_mutual            [µH]
    n_vias: int
    pitch_over_w: float     # Minimum p/W-Verhaeltnis
    piecewise_ok: bool      # True wenn p/W >= 8 (kein Mutual noetig)

    def summary(self) -> str:
        pw_str = f"{self.pitch_over_w:.1f}" if self.pitch_over_w < 999 else "n/a"
        return (
            f"L_self={self.l_self_uH:.4f}  "
            f"L_vias={self.l_vias_uH:.4f}  "
            f"L_mutual={self.l_mutual_uH:+.4f}  "
            f"L_total={self.l_total_uH:.4f} µH  "
            f"(p/W={pw_str}, pw_ok={self.piecewise_ok})"
        )


# ---------------------------------------------------------------------------
# Einzelformeln
# ---------------------------------------------------------------------------

def l_self_segment(length_m: float, width_m: float, thickness_m: float) -> float:
    """
    Eigeninduktivitaet eines rechteckigen Leiters [H].

    Ruehli 1972 / Lorenz 1879:
        L = µ0·l/(2π) · [ln(2l/(w+t)) + 0.5 + 0.2235·(w+t)/l]
    """
    l = length_m
    if l < 1e-12:
        return 0.0
    wt = width_m + thickness_m
    return (_MU0 * l / (2.0 * np.pi)) * (
        np.log(2.0 * l / max(wt, 1e-12))
        + 0.5
        + 0.2235 * wt / l
    )


def l_via_single(height_m: float, diameter_m: float) -> float:
    """
    Induktivitaet eines einzelnen Vias [H].

        L_via = µ0·h/(2π) · (1 + ln(4h/d))
    """
    if height_m <= 0 or diameter_m <= 0:
        return 0.0
    return (_MU0 * height_m / (2.0 * np.pi)) * (
        1.0 + np.log(max(4.0 * height_m / diameter_m, 1.0))
    )


# ---------------------------------------------------------------------------
# Pitch-Analyse
# ---------------------------------------------------------------------------

def _compute_min_pitch_over_w(segs: Sequence[Segment]) -> float:
    """
    Berechnet minimales p/W fuer die Windungssegmente.

    p = kuerzester Mittelpunktsabstand zwischen benachbarten Segmenten
        auf dem gleichen Layer.
    W = mittlere Leiterbreite.

    Returns 9999.0 wenn zu wenige Segmente vorhanden sind.
    """
    if len(segs) < 2:
        return 9999.0

    mids = np.array([s.midpoint for s in segs])
    widths = np.array([s.width for s in segs])
    w_avg = float(np.mean(widths))
    if w_avg < 1e-12:
        return 9999.0

    # Naechste-Nachbar-Abstaende je Layer
    layers = set(s.layer for s in segs)
    min_dists: list[float] = []
    for layer in layers:
        idx = [i for i, s in enumerate(segs) if s.layer == layer]
        if len(idx) < 2:
            continue
        layer_mids = mids[idx]
        for i in range(len(layer_mids)):
            dd = np.linalg.norm(layer_mids[i + 1:] - layer_mids[i], axis=1)
            if len(dd) > 0:
                min_dists.append(float(np.min(dd)))

    if not min_dists:
        return 9999.0

    p_min = min(min_dists)
    return p_min / w_avg


# ---------------------------------------------------------------------------
# Haupt-Funktion
# ---------------------------------------------------------------------------

def compute_inductance(
    winding_segs: Sequence[Segment],
    return_segs: Sequence[Segment],
    n_vias: int,
    via_height_m: float,
    via_diameter_m: float,
    *,
    pitch_threshold: float = 8.0,
    mutual_max_dist_m: float = 0.5e-3,
) -> InductanceResult:
    """
    Berechnet Gesamtinduktivitaet L_C einer PCB-Rogowski-Spule.

    Modell:
        L_C = Σ L_self,i   (winding + return, Ruehli/Lorenz)
            + N · L_via     (Vias in Serie)
            + L_mutual      (nur wenn p/W < pitch_threshold)

    Args:
        winding_segs:      Windungssegmente (gamma = ±1)
        return_segs:        Rueckleiter-Segmente (gamma = -1)
        n_vias:             Anzahl Vias
        via_height_m:       Via-Hoehe [m]  (h_diel zwischen benachbarten Lagen,
                           typisch 0.32 mm — NICHT volle Boardhoehe!)
        via_diameter_m:     Via-Durchmesser [m]
        pitch_threshold:    p/W-Schwelle ab der Mutuals ignoriert werden (default 8)
        mutual_max_dist_m:  Max. Koppeldistanz fuer PEEC Mutuals [m] (default 0.5 mm)
    """
    # 1) Eigeninduktivitaeten (Freiraum, Ruehli/Lorenz)
    l_self_H = sum(_self_inductance(s) for s in winding_segs) + \
               sum(_self_inductance(s) for s in return_segs)

    # 2) Via-Induktivitaet
    l_vias_H = n_vias * l_via_single(via_height_m, via_diameter_m)

    # 3) Pitch-Check → ggf. Mutual-Korrektur
    pw_ratio = _compute_min_pitch_over_w(list(winding_segs))
    piecewise_ok = pw_ratio >= pitch_threshold

    l_mutual_H = 0.0
    if not piecewise_ok:
        # PEEC mit kurzem Cutoff fuer Nahfeld-Kopplung
        all_segs = list(winding_segs) + list(return_segs)
        calc = PEECInductanceCalculator(max_distance_m=mutual_max_dist_m)
        peec = calc.compute(all_segs)
        # Mutual = PEEC_total - PEEC_self  (nur Kreuzterme)
        l_mutual_H = peec.l_mutual_uH * 1e-6   # µH -> H

    l_total_H = l_self_H + l_vias_H + l_mutual_H

    return InductanceResult(
        l_self_uH=l_self_H * 1e6,
        l_vias_uH=l_vias_H * 1e6,
        l_mutual_uH=l_mutual_H * 1e6,
        l_total_uH=l_total_H * 1e6,
        n_vias=n_vias,
        pitch_over_w=pw_ratio,
        piecewise_ok=piecewise_ok,
    )
