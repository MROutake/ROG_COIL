r"""
Uebertragungsfunktion und Zeitbereichsantwort des Rogowski-Ersatzschaltbildes.

Ersatzschaltbild
----------------
Serieller R-L-Zweig parallel zu parasitaerer Kapazitaet C
(Standard-Modell fuer eine PCB-Rogowski-Spule, vgl. ``fitting.py``)::

        R_s     L_s
    +--/\/\/--UUUU--+
    |               |
    +------||-------+      C_s (parallel)

Ports: Zweipol mit Klemmenimpedanz ::

    Z(s) = (R_s + s L) / (1 + s R_s C + s^2 L C)

Fuer Rogowski-Anwendungen kann der Sensor zusaetzlich mit
Gegeninduktivitaet M gegen den Primaerleiter eingebunden werden.
Dann gilt mit Primaerstrom I_1(s)::

    V_out(s) / I_1(s) = s M * Z_load(s) / (Z_coil(s) + Z_load(s))

Fuer den Leerlauf (Z_load -> inf) vereinfacht sich das zur ``ideal``-Variante::

    V_out(s) / I_1(s) = s M                      (ideal, keine parasitaer.)
    V_out(s) / I_1(s) = s M / (1 + s R_s C + s^2 L C)   (mit Parasitaeren)

Alle Formeln sind zentral in diesem Modul definiert und werden von
GUI (Tab 4) wie auch CLI-Skripten genutzt -- bei Modellaenderungen
nur hier editieren.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal


_MU_0: float = 1.2566370614e-6  # H/m


# ---------------------------------------------------------------------------
# Klemmenimpedanz Z(f) -- wrapper um fitting.z_coil (konsistent halten!)
# ---------------------------------------------------------------------------

def impedance(
    freq_hz: np.ndarray,
    l_H: float,
    r_dc_ohm: float,
    c_F: float,
    k_skin: float = 0.0,
    k_prox: float = 0.0,
    f0_prox_hz: float = 1e6,
) -> np.ndarray:
    r"""
    Komplexe Klemmenimpedanz Z(f) der Rogowski-Spule.

    .. math::

       Z(f) = \frac{R_s(f) + j\omega L}{1 - \omega^2 L C + j\omega R_s(f) C}

    mit :math:`R_s(f) = R_{dc} + k_{skin}\sqrt{f} + k_{prox}\,f/f_0`.

    Siehe auch :func:`pcb_rogowski.domain.coil.fitting.z_coil`.
    """
    from pcb_rogowski.domain.coil.fitting import z_coil
    return z_coil(np.asarray(freq_hz, dtype=float), l_H, r_dc_ohm,
                  k_skin, k_prox, c_F, f0=f0_prox_hz)


def resonance_frequency_hz(l_H: float, c_F: float) -> float:
    r"""Eigenresonanz :math:`f_{res} = 1 / (2\pi \sqrt{LC})`."""
    if l_H <= 0.0 or c_F <= 0.0:
        return 0.0
    return 1.0 / (2.0 * math.pi * math.sqrt(l_H * c_F))


# ---------------------------------------------------------------------------
# LTI-Systeme des Ersatzschaltbildes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EquivalentCircuit:
    """Passive Parameter des Rogowski-Ersatzschaltbildes (SI-Einheiten)."""

    L_H: float
    R_ohm: float
    C_F: float
    M_H: float = 0.0

    # ---- Convenience: Anzeige in Engineering-Einheiten ----
    @property
    def L_uH(self) -> float: return self.L_H * 1e6
    @property
    def C_pF(self) -> float: return self.C_F * 1e12
    @property
    def M_nH(self) -> float: return self.M_H * 1e9


def impedance_tf(ec: EquivalentCircuit) -> signal.TransferFunction:
    r"""
    Bildet die Klemmenimpedanz als ``scipy.signal.TransferFunction``.

    .. math::

       Z(s) = \frac{L\,s + R}{L C\,s^2 + R C\,s + 1}

    Einheit: :math:`\Omega`.
    """
    num = [ec.L_H, ec.R_ohm]
    den = [ec.L_H * ec.C_F, ec.R_ohm * ec.C_F, 1.0]
    return signal.TransferFunction(num, den)


def voltage_from_primary_tf(ec: EquivalentCircuit) -> signal.TransferFunction:
    r"""
    Uebertragungsfunktion :math:`V_{out}(s) / I_1(s)` (Leerlauf).

    .. math::

       H(s) = \frac{s\,M}{L C\,s^2 + R C\,s + 1}

    Einheit: :math:`\Omega` (Volt pro Ampere), daher als TF nutzbar.
    """
    if ec.M_H == 0.0:
        # Minimal-TF 0, damit step()/bode() nicht scheitert
        return signal.TransferFunction([0.0, 0.0], [1.0])
    num = [ec.M_H, 0.0]
    den = [ec.L_H * ec.C_F, ec.R_ohm * ec.C_F, 1.0]
    return signal.TransferFunction(num, den)


# ---------------------------------------------------------------------------
# Zeitbereichsantworten
# ---------------------------------------------------------------------------

def impedance_step_response(
    ec: EquivalentCircuit,
    t_end_s: float | None = None,
    n_points: int = 2000,
) -> tuple[np.ndarray, np.ndarray]:
    r"""
    Sprungantwort der Klemmenimpedanz (Stromsprung :math:`i(t)=u(t)`).

    Liefert die Klemmenspannung :math:`v(t) = \mathcal{L}^{-1}\{Z(s)/s\}`.

    Args:
        ec:       Ersatzschaltbild-Parameter.
        t_end_s:  Simulationsende [s]. Default: :math:`20 / \omega_0` bei
                  :math:`\omega_0 = 1/\sqrt{LC}`.
        n_points: Anzahl Zeitpunkte.

    Returns:
        ``(t, v)`` -- Zeitvektor [s] und Spannungsantwort [V].
    """
    if ec.L_H <= 0.0 or ec.C_F <= 0.0:
        return np.zeros(2), np.zeros(2)
    if t_end_s is None:
        w0 = 1.0 / math.sqrt(ec.L_H * ec.C_F)
        t_end_s = 20.0 / w0
    t = np.linspace(0.0, t_end_s, n_points)
    tf = impedance_tf(ec)
    _, y = signal.step(tf, T=t)
    return t, y


def primary_step_response(
    ec: EquivalentCircuit,
    t_end_s: float | None = None,
    n_points: int = 2000,
) -> tuple[np.ndarray, np.ndarray]:
    r"""
    Sprungantwort der Spulenspannung auf einen Primaerstrom-Sprung.

    Ausgang :math:`v_{out}(t)` fuer :math:`i_1(t) = u(t)` (Amp-Sprung).

    Returns:
        ``(t, v_out)`` -- Zeit [s], Spannung [V] (bei 1 A Primaersprung).
    """
    if ec.L_H <= 0.0 or ec.C_F <= 0.0 or ec.M_H == 0.0:
        t = np.linspace(0.0, max(t_end_s or 1e-6, 1e-9), n_points)
        return t, np.zeros_like(t)
    if t_end_s is None:
        w0 = 1.0 / math.sqrt(ec.L_H * ec.C_F)
        t_end_s = 20.0 / w0
    t = np.linspace(0.0, t_end_s, n_points)
    tf = voltage_from_primary_tf(ec)
    _, y = signal.step(tf, T=t)
    return t, y
