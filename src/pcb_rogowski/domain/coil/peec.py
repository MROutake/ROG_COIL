"""
PEEC-Light: Partielle Induktivitaetsmatrix fuer PCB-Rogowski-Spulen.

Modell:
    L_eq = gamma^T * M * gamma
         = sum_i sum_j  gamma_i * gamma_j * M_ij

    M_ii  = Selbstinduktivitaet Segment i  (Neumann-Naeherung nach Lorenz/Ruehli)
    M_ij  = Gegenseitige Induktivitaet     (2x2 Gauss-Quadratur des Neumann-Integrals)

    gamma_i : Wirksamkeitsfaktor pro Segment
              +1  aktive Windung (winding, sigma=+1)
              -1  Windung mit umgekehrter Wickelrichtung (sigma=-1)
              -1  Rückleiter  (return) → kompensiert Fluss
               0  Zuleitung   (connection/lead) → kein Beitrag

Referenz:
    Ruehli, A.E. (1972): "Inductance Calculations in a Complex Integrated
    Circuit Environment", IBM Journal of Research & Development.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

_MU0: float = 1.2566370614e-6  # H/m


# ---------------------------------------------------------------------------
# Segment-Datenklasse
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """Ein gerades Leiterbahnstück im 3-D Raum."""

    x1: float   # Startpunkt x [m]
    y1: float   # Startpunkt y [m]
    z1: float   # Startpunkt z [m]
    x2: float   # Endpunkt x [m]
    y2: float   # Endpunkt y [m]
    z2: float   # Endpunkt z [m]
    width: float        # Leiterbreite [m]
    thickness: float    # Kupferdicke  [m]
    gamma: float = 1.0  # Wirksamkeitsfaktor  ∈ [-1, +1]
    layer: str = ""

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self._vec))

    @property
    def _vec(self) -> np.ndarray:
        return np.array([self.x2 - self.x1,
                         self.y2 - self.y1,
                         self.z2 - self.z1])

    @property
    def unit(self) -> np.ndarray:
        v = self._vec
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-15 else np.zeros(3)

    @property
    def midpoint(self) -> np.ndarray:
        return np.array([(self.x1 + self.x2) / 2,
                         (self.y1 + self.y2) / 2,
                         (self.z1 + self.z2) / 2])


# ---------------------------------------------------------------------------
# Induktivitäts-Formeln
# ---------------------------------------------------------------------------

def _self_inductance(seg: Segment) -> float:
    """
    Selbstinduktivitaet eines rechteckigen Leiters [H].

    Ruehli 1972 / Lorenz 1879:
        L_ii = µ0*l/(2π) * [ln(2l/(w+t)) + 0.5 + 0.2235*(w+t)/l]
    """
    l = seg.length
    if l < 1e-12:
        return 0.0
    wt = seg.width + seg.thickness
    return (_MU0 * l / (2.0 * np.pi)) * (
        np.log(2.0 * l / max(wt, 1e-12))
        + 0.5
        + 0.2235 * wt / l
    )


def _mutual_inductance(si: Segment, sj: Segment) -> float:
    """
    Gegenseitige Induktivitaet zweier gerader Segmente [H].

    Neumann-Integral, ausgewertet mit 2×2 Gauss-Legendre-Quadratur:
        M_ij = µ0/(4π) ∫_li ∫_lj  (t̂_i · t̂_j) / |r_i - r_j|  dl_i dl_j

    Segmente orthogonal zueinander (dot ≈ 0) → M_ij ≈ 0 (übersprungen).
    """
    dot = float(np.dot(si.unit, sj.unit))
    if abs(dot) < 1e-6:
        return 0.0

    # 2-Punkt Gauss-Legendre auf [0, 1]
    gpts = np.array([0.5 - 1.0 / (2.0 * np.sqrt(3.0)),
                     0.5 + 1.0 / (2.0 * np.sqrt(3.0))])

    pi = np.array([si.x1, si.y1, si.z1])
    pj = np.array([sj.x1, sj.y1, sj.z1])
    vi = np.array([si.x2 - si.x1, si.y2 - si.y1, si.z2 - si.z1])
    vj = np.array([sj.x2 - sj.x1, sj.y2 - sj.y1, sj.z2 - sj.z1])
    li = si.length
    lj = sj.length

    integral = 0.0
    for ui in gpts:
        ri = pi + ui * vi
        for uj in gpts:
            rj = pj + uj * vj
            d = float(np.linalg.norm(ri - rj))
            # Nahbereich-Regularisierung: minimum Abstand = halbe Leiterbreite
            d = max(d, 0.5 * max(si.width, sj.width, 1e-9))
            integral += 1.0 / d

    # Jacobi: jeder Punkt hat Gewicht 0.5 * li  resp. 0.5 * lj
    integral *= (li * 0.5) * (lj * 0.5)
    return (_MU0 / (4.0 * np.pi)) * dot * integral


# ---------------------------------------------------------------------------
# Ergebnis-Container
# ---------------------------------------------------------------------------

@dataclass
class PEECResult:
    l_self_uH: float    # Summe Selbstinduktivitaeten [µH]
    l_mutual_uH: float  # Kreuzterme  2*Σ γ_i γ_j M_ij  [µH]
    l_total_uH: float   # L_eq = L_self + L_mutual [µH]
    n_segments: int
    M_matrix: np.ndarray  # Vollstaendige M-Matrix [H]  shape (n, n)
    gammas: np.ndarray    # Wirksamkeitsvektor


# ---------------------------------------------------------------------------
# Rechner
# ---------------------------------------------------------------------------

class PEECInductanceCalculator:
    """
    Berechnet  L_eq = γ^T M γ  fuer eine Liste von Segmenten.

    Args:
        max_distance_m:  Kopplungsreichweite [m]. Segmente mit groesserem
                         Mittelpunktsabstand werden nicht gekoppelt (Bandlimitierung).
                         Typisch: 5 mm genügt fuer PCB-Rogowski.
    """

    def __init__(self, max_distance_m: float = 5e-3) -> None:
        self.max_distance_m = max_distance_m

    def compute(self, segments: Sequence[Segment]) -> PEECResult:
        segs = list(segments)
        n = len(segs)

        M = np.zeros((n, n))
        gammas = np.array([s.gamma for s in segs])

        # Mittelpunkte fuer Abstandsfilter
        mids = np.array([s.midpoint for s in segs])

        # Diagonale: Selbstinduktivitaeten
        for i, s in enumerate(segs):
            M[i, i] = _self_inductance(s)

        # Obere Dreiecksmatrix: Gegeninduktivitaeten
        for i in range(n):
            for j in range(i + 1, n):
                if np.linalg.norm(mids[i] - mids[j]) > self.max_distance_m:
                    continue
                mij = _mutual_inductance(segs[i], segs[j])
                M[i, j] = mij
                M[j, i] = mij

        l_total  = float(gammas @ M @ gammas)
        l_self   = float(np.dot(gammas ** 2, np.diag(M)))
        l_mutual = l_total - l_self

        return PEECResult(
            l_self_uH=l_self * 1e6,
            l_mutual_uH=l_mutual * 1e6,
            l_total_uH=l_total * 1e6,
            n_segments=n,
            M_matrix=M,
            gammas=gammas,
        )
