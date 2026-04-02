"""
Frequenzabhaengiger Serienwiderstand R(f) fuer PCB-Rogowski-Spulen.

Modell:
    R_s(f) = R_track(f) + R_via(f) + R_contact

Skin-Tiefe:
    delta(f) = sqrt(2*rho / (omega * mu0))

Effektiver Leiterquerschnitt (duenner PCB-Leiter):
    A_eff = w * t              wenn delta >= t/2   (DC-Naeherung)
    A_eff = 2*delta*(w + t)    wenn delta <  t/2   (Skin-dominiert)

Proximity-Korrektur (einfaches Potenz-Modell):
    R_track_prox(f) = R_track(f) * (1 + k_prox * sqrt(f / f0_prox))

Via-Widerstand:
    R_via = rho * h_via / A_plating_eff
    A_plating_eff = pi * d_via * min(t_plating, delta)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

_MU0    = 1.2566370614e-6   # H/m
_RHO_CU = 1.72e-8           # Ω·m  Kupfer 20°C


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

@dataclass
class SkinModelConfig:
    """Fit-Parameter fuer das frequenzabhaengige Widerstandsmodell."""

    rho_ohm_m: float = _RHO_CU     # Spez. Widerstand [Ω·m]
    k_prox: float = 0.0            # Proximity-Faktor  [Fit]
    f0_prox: float = 1e6           # Referenzfrequenz Proximity [Hz]
    r_contact_ohm: float = 0.0     # Via-Kontaktzusatz gesamt [Ω]  [Fit]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def skin_depth(f: float,
               rho: float = _RHO_CU,
               mu: float = _MU0) -> float:
    """Skin-Tiefe delta(f) [m]. Gibt inf zurueck fuer f <= 0."""
    if f <= 0.0:
        return np.inf
    return np.sqrt(2.0 * rho / (2.0 * np.pi * f * mu))


def r_segment(
    length_m: float,
    width_m: float,
    thickness_m: float,
    f: float,
    cfg: SkinModelConfig,
) -> float:
    """
    Widerstand eines einzelnen Leiterbahnstücks bei Frequenz f [Ω].

    Args:
        length_m:    Segmentlaenge [m]
        width_m:     Leiterbreite  [m]
        thickness_m: Kupferdicke   [m]
        f:           Frequenz      [Hz]
        cfg:         Modell-Konfiguration
    """
    delta = skin_depth(f, cfg.rho_ohm_m)
    w = width_m
    t = thickness_m

    if delta >= t / 2.0:
        a_eff = w * t
    else:
        a_eff = 2.0 * delta * (w + t)

    a_eff = max(a_eff, 1e-20)
    r_dc  = cfg.rho_ohm_m * length_m / a_eff

    # Proximity-Aufschlag
    r_prox = r_dc * cfg.k_prox * np.sqrt(max(f, 0.0) / cfg.f0_prox)

    return r_dc + r_prox


def r_vias(
    h_via_m: float,
    d_via_m: float,
    t_plating_m: float,
    n_vias: int,
    f: float,
    cfg: SkinModelConfig,
) -> float:
    """
    Via-Widerstand (alle Vias in Serie) bei Frequenz f [Ω].

    Args:
        h_via_m:      Via-Hoehe (= Plattendicke) [m]
        d_via_m:      Bohrungsdurchmesser [m]
        t_plating_m:  Plating-Dicke (typisch 25 µm) [m]
        n_vias:       Anzahl Vias
        f:            Frequenz [Hz]
    """
    if n_vias <= 0 or d_via_m <= 0:
        return 0.0

    delta    = skin_depth(f, cfg.rho_ohm_m)
    t_eff    = min(t_plating_m, delta)
    a_plating = np.pi * d_via_m * max(t_eff, 1e-12)

    r_one = cfg.rho_ohm_m * h_via_m / a_plating
    return r_one * n_vias + cfg.r_contact_ohm


def r_total(
    lengths_m: list[float],
    widths_m: list[float],
    thicknesses_m: list[float],
    h_via_m: float,
    d_via_m: float,
    t_plating_m: float,
    n_vias: int,
    f: float,
    cfg: SkinModelConfig,
) -> float:
    """
    Gesamtserienwiderstand R_s(f) = Σ R_track_i(f) + R_via(f) [Ω].
    """
    r = sum(
        r_segment(l, w, t, f, cfg)
        for l, w, t in zip(lengths_m, widths_m, thicknesses_m)
    )
    r += r_vias(h_via_m, d_via_m, t_plating_m, n_vias, f, cfg)
    return r
