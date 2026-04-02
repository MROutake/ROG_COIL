"""
Parasitaere Kapazitaet C_total fuer PCB-Rogowski-Spulen (ohne Grundebene).

C_total = C_coupling + C_interturn + C_via

C_coupling  = Kopplung jedes Windungssegments zur benachbarten Innenlage
              (Return-Ring / andere Windungen) durch Dielektrikum:
              C = eps0*eps_r * Sigma_i (w_i * l_i / H_diel)
              H_diel = Abstand zur naechsten Kupferlage (0.32 mm),
              NICHT volle Boardhoehe!

C_interturn = Kapazitaet zwischen benachbarten Windungszaehnen
              auf derselben Lage (Parallelplatten + Randfeld):
              C_pair = eps0*eps_r * l * (w/g + 1/pi * ln(1 + 2w/g))

C_via       = N_via · c_via      Via-Kapazitaet (Zylinderkondensator)

KEIN C_plane!  Diese Designs haben keine Grundebene / Masseschirm.
Die Kapazitaet zwischen den Leitern (Interturn) dominiert.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

_EPS0 = 8.8541878128e-12  # F/m


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class CapacitanceConfig:
    """Materialkonstanten und geometrische Parameter fuer das Kapazitaetsmodell."""

    eps_r: float = 4.8              # Relative Permittivitaet FR4
    gap_interturn_m: float = 0.2e-3 # Spalt zwischen benachbarten Windungszaehnen [m]
    h_diel_m: float = 0.32e-3       # Abstand zur naechsten Kupferlage [m] (H_diel)
    c_via_fF: float = 30.0          # Kapazitaet pro Via [fF]


# ---------------------------------------------------------------------------
# Ergebnis
# ---------------------------------------------------------------------------

@dataclass
class CapacitanceResult:
    c_coupling_pF: float    # Dominant: Kopplung zur benachbarten Innenlage
    c_interturn_pF: float   # Leiter ↔ Leiter auf gleicher Lage
    c_via_pF: float         # Via-Kapazitaet
    c_total_pF: float

    def summary(self) -> str:
        return (
            f"C_coupling={self.c_coupling_pF:.3f}  "
            f"C_interturn={self.c_interturn_pF:.3f}  "
            f"C_via={self.c_via_pF:.3f}  "
            f"C_total={self.c_total_pF:.3f} pF"
        )


# ---------------------------------------------------------------------------
# Einzelformeln
# ---------------------------------------------------------------------------

def _c_interturn_pair(
    length_m: float,
    width_m: float,
    gap_m: float,
    eps_r: float,
) -> float:
    """
    Kapazitaet zwischen zwei benachbarten parallelen Leitern [F].

    Parallelplatten-Anteil + Randfeld-Korrektur (konformal):
        C = eps0·eps_r · l · (w/g + 1/π · ln(1 + 2w/g))

    Args:
        length_m:  Gemeinsame Kopplungslaenge [m]
        width_m:   Leiterbreite [m]
        gap_m:     Spalt zwischen den Leitern [m]
        eps_r:     Relative Permittivitaet
    """
    g = max(gap_m, 1e-9)
    w = max(width_m, 1e-9)
    eps = _EPS0 * eps_r
    # Parallelplatten + Randfeld
    return eps * length_m * (w / g + (1.0 / np.pi) * np.log(1.0 + 2.0 * w / g))


def _c_layer_contribution(
    length_m: float,
    width_m: float,
    h_m: float,
    eps_r: float,
) -> float:
    """
    Kapazitaet Top ↔ Bottom Leiter durch Dielektrikum [F].

    Einfache Parallelplatten-Naeherung:
        C = eps0·eps_r · w·l / h
    """
    return _EPS0 * eps_r * width_m * length_m / max(h_m, 1e-9)


# ---------------------------------------------------------------------------
# Berechnung
# ---------------------------------------------------------------------------

def compute_capacitance(
    segment_lengths_m: list[float],
    segment_widths_m: list[float],
    n_vias: int,
    n_interturn_pairs: int,
    cfg: CapacitanceConfig,
    *,
    avg_coupling_length_m: float | None = None,
) -> CapacitanceResult:
    """
    Berechnet alle Kapazitaetsbeitraege (ohne Grundebene).

    Args:
        segment_lengths_m:      Laenge jedes Windungssegments [m]
        segment_widths_m:       Breite jedes Windungssegments [m]
        n_vias:                 Anzahl Vias
        n_interturn_pairs:      Anzahl benachbarter Windungszahn-Paare
        cfg:                    Modell-Konfiguration
        avg_coupling_length_m:  Durchschnittliche Kopplungslaenge pro Paar [m].
                               Wenn None, wird der Median der Segmentlaengen verwendet.
    """
    # --- C_coupling (dominant!) ---
    # Jedes Windungssegment koppelt durch H_diel zur benachbarten Innenlage
    # (Return-Ring / andere Windungen).  Kein Faktor 0.5 — jedes Segment
    # hat einen Koppelpartner auf der naechsten Kupferlage.
    c_coupling = sum(
        _c_layer_contribution(l, w, cfg.h_diel_m, cfg.eps_r)
        for l, w in zip(segment_lengths_m, segment_widths_m)
    )

    # --- C_interturn (Nachbarzaehne auf gleicher Lage) ---
    if avg_coupling_length_m is None:
        avg_coupling_length_m = float(np.median(segment_lengths_m)) \
            if segment_lengths_m else 0.0
    avg_width_m = float(np.mean(segment_widths_m)) if segment_widths_m else 0.2e-3

    c_interturn = n_interturn_pairs * _c_interturn_pair(
        length_m=avg_coupling_length_m,
        width_m=avg_width_m,
        gap_m=cfg.gap_interturn_m,
        eps_r=cfg.eps_r,
    )

    # --- C_via ---
    c_via = n_vias * cfg.c_via_fF * 1e-15

    # --- C_total ---
    c_total = c_coupling + c_interturn + c_via

    return CapacitanceResult(
        c_coupling_pF=c_coupling * 1e12,
        c_interturn_pF=c_interturn * 1e12,
        c_via_pF=c_via * 1e12,
        c_total_pF=c_total * 1e12,
    )
