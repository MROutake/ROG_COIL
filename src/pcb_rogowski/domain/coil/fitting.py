r"""
Bode100-CSV-Laden und Modellfit fuer PCB-Rogowski-Spulen.

Ersatzschaltbild: Spule mit parasitaerer Parallelkapazitaet  (KEIN R_p)

           R_s(f)   L_s
    +--+--/\/\/--UUUUU--+
    |  |               |
    |  +------||-------+    C_s (parallel zur Spule)
    |  |               |
    +--+---------------+

Impedanz (Parallelmodell):
    Z(f) = (R_s(f) + j*omega*L) || (1 / (j*omega*C))
         = (R_s + j*omega*L) / (1 - omega^2*L*C + j*omega*R_s*C)

Physikalisches Verhalten:
    f << f_res:  Z ~ R_s + j*omega*L     (induktiv, Phasenwinkel ~ +90 deg)
    f = f_res:   |Z| maximal             (parallele Resonanz)
    f >> f_res:  Z ~ 1/(j*omega*C)       (kapazitiv)

Frequenzabhaengiger Widerstand:
    R_s(f) = R_dc + k_skin*sqrt(f) + k_prox*f/f0

Fit-Parameter  (scipy.optimize.least_squares, Methode TRF):
    [L_H, R_dc, k_skin, k_prox, C_F]
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares


# ---------------------------------------------------------------------------
# CSV-Laden
# ---------------------------------------------------------------------------

def load_bode100_csv(path: Path) -> pd.DataFrame:
    """
    Laedt eine Bode100-CSV-Datei (Semikolon-Trennzeichen, Punkt als Dezimal).

    Erwartet Spaltennamen (Bode100-Export-Standard):
        Frequency (Hz)
        Trace 1: Impedance: Real (Ω)
        Trace 1: Impedance: Imaginary (Ω)
        Trace 1: Impedance: Magnitude (Ω)
        Trace 2: Impedance: Phase (°)

    Gibt DataFrame mit Spalten zurück:
        freq_hz, re_ohm, im_ohm, mag_ohm, phase_deg
    """
    df = pd.read_csv(path, sep=";", decimal=".", comment="#", engine="python")
    df.columns = [c.strip() for c in df.columns]

    col_map: dict[str, str] = {}
    for c in df.columns:
        cl = c.lower()
        if "frequency" in cl:
            col_map[c] = "freq_hz"
        elif "real" in cl and "trace 1" in cl:
            col_map[c] = "re_ohm"
        elif "imaginary" in cl and "trace 1" in cl:
            col_map[c] = "im_ohm"
        elif "magnitude" in cl and "trace 1" in cl:
            col_map[c] = "mag_ohm"
        elif "phase" in cl and "trace 2" in cl:
            col_map[c] = "phase_deg"

    df = df.rename(columns=col_map)

    required = {"freq_hz", "re_ohm", "im_ohm"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Fehlende Spalten in {path.name}: {missing}\n"
            f"Vorhandene Spalten: {list(df.columns)}"
        )

    for col in ["freq_hz", "re_ohm", "im_ohm", "mag_ohm", "phase_deg"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["freq_hz", "re_ohm", "im_ohm"])
    df = df.sort_values("freq_hz").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Automatische Parameterabschaetzung aus Messdaten
# ---------------------------------------------------------------------------

def estimate_from_data(
    df: pd.DataFrame,
    f_low_max_hz: float = 2e6,
) -> tuple[float, float, float]:
    r"""
    Schaetzt Anfangswerte fuer L, R_dc, C direkt aus Bode100-Messdaten.

    Physikalisches Modell:  Z = (R + jomegaL) || (1/jomegaC)

    Algorithmus:
    1. L:  Median von Im(Z)/(2*pi*f)  bei f <= f_low_max_hz
           (Unterhalb der Resonanz gilt Im(Z) ~ omega*L)

    2. R:  Median von Re(Z) bei f <= f_low_max_hz

    3. C:  Zwei Methoden, je nach Datenlage:
       a) Im(Z)-Nulldurchgang im Messdatenbereich:
             Im(Z) wechselt bei f_res das Vorzeichen (pos -> neg).
             Aus f_res und L folgt:  C = 1 / (4*pi^2 * f_res^2 * L)
       b) Hochfrequenz-Verstaerkungsformel (wenn kein Nulldurchgang):
             Unterhalb der Resonanz gilt naeherungsweise:
             Im(Z) ~ omega*L / (1 - omega^2*L*C)
             -> C = (1 - omega*L/Im(Z)) / (omega^2 * L)   bei hohen f

    Args:
        df:           Bode100 DataFrame (aus load_bode100_csv)
        f_low_max_hz: Obere Frequenzgrenze fuer L/R-Schaetzung [Hz]

    Returns:
        (L_H, R_ohm, C_F)  Startwerte fuer den Fit
    """
    freqs = df["freq_hz"].to_numpy()
    re    = df["re_ohm"].to_numpy()
    im    = df["im_ohm"].to_numpy()

    # --- L und R aus Niedrigfrequenzbereich ---
    low = freqs <= f_low_max_hz
    if np.sum(low) < 3:
        low = np.ones(len(freqs), dtype=bool)
    omega_low = 2.0 * np.pi * freqs[low]
    L_est = float(np.median(im[low] / omega_low))
    R_est = float(np.median(np.abs(re[low])))
    L_est = max(abs(L_est), 1e-9)
    R_est = max(R_est, 1e-4)

    # --- C: Methode A — Im(Z)-Nulldurchgang (wenn Resonanz im Messbereich) ---
    C_est: float | None = None
    zero_crossings = np.where((im[:-1] > 0) & (im[1:] <= 0))[0]
    if len(zero_crossings) > 0:
        i0 = zero_crossings[0]
        f1, f2 = freqs[i0], freqs[i0 + 1]
        im1, im2 = im[i0], im[i0 + 1]
        # Linear interpolierte Nullstelle
        f_res_est = float(f1 + (f2 - f1) * (-im1) / (im2 - im1)) if (im2 - im1) != 0 else float(f1)
        C_est = 1.0 / (4.0 * np.pi**2 * max(f_res_est, 1.0)**2 * L_est)

    # --- C: Methode B — Hochfrequenz-Verstaerkungsformel ---
    if C_est is None or C_est <= 0:
        # Nutze die oberen 30% der Frequenzachse
        f_high_min = freqs[-1] * 0.70
        high = freqs >= f_high_min
        if np.sum(high) < 3:
            high_idx = np.arange(max(0, len(freqs) - 10), len(freqs))
            high = np.zeros(len(freqs), dtype=bool)
            high[high_idx] = True

        omega_hi = 2.0 * np.pi * freqs[high]
        im_hi    = im[high]
        # Berechne Verstaerkung: a = omega*L / Im(Z)  (sollte 0 < a < 1 sein)
        # Dann: C = (1 - a) / (omega^2 * L)
        a = omega_hi * L_est / np.where(im_hi > 1e-9, im_hi, 1e-9)
        valid = (a > 0.01) & (a < 0.98)   # Nur wenn Verstaerkung messbar
        if np.sum(valid) >= 2:
            C_candidates = (1.0 - a[valid]) / (omega_hi[valid]**2 * L_est)
            C_est = float(np.median(C_candidates[C_candidates > 0]))

    if C_est is None or C_est <= 0:
        # Fallback: 20 pF (typisch fuer 2-4-Lagen PCB-Spule)
        C_est = 20e-12

    C_est = max(abs(C_est), 0.1e-12)
    return L_est, R_est, C_est


# ---------------------------------------------------------------------------
# Impedanzmodell  (Parallelmodell, kein R_p)
# ---------------------------------------------------------------------------

def z_coil(
    freq_hz: np.ndarray,
    L_H: float,
    R_dc: float,
    k_skin: float,
    k_prox: float,
    C_F: float,
    f0: float = 1e6,
) -> np.ndarray:
    r"""
    Komplexe Impedanz einer PCB-Spule mit parasitaerer Kapazitaet (parallel).

    Modell:
        R_s(f) = R_dc + k_skin*sqrt(f) + k_prox*(f/f0)
        Z_RL   = R_s(f) + j*omega*L
        Z_C    = 1 / (j*omega*C)
        Z(f)   = Z_RL || Z_C = Z_RL * Z_C / (Z_RL + Z_C)

    Vereinfacht:
        Z(f) = (R_s + j*omega*L) / (1 - omega^2*L*C + j*omega*R_s*C)

    Physikalisch korrekt:
    - f << f_res:  Z ~ R_s + j*omega*L         (induktiv)
    - f = f_res:   |Z| = L / (R_s*C)           (Impedanzmaximum)
    - f >> f_res:  Z ~ 1 / (j*omega*C)         (kapazitiv)

    Args:
        freq_hz:  Frequenzvektor [Hz]
        L_H:      Induktivitaet [H]
        R_dc:     Gleichstromwiderstand [Ohm]
        k_skin:   Skin-Koeffizient  [Ohm/sqrt(Hz)]
        k_prox:   Proximity-Koeffizient  (dimensionslos, bezogen auf f0)
        C_F:      Parallelkapazitaet [F]
        f0:       Normierungsfrequenz fuer k_prox [Hz]

    Returns:
        Komplexes ndarray der Impedanz [Ohm]
    """
    omega = 2.0 * np.pi * freq_hz

    r_s  = R_dc + k_skin * np.sqrt(np.maximum(freq_hz, 0.0)) \
                + k_prox * freq_hz / f0
    z_rl = r_s + 1j * omega * L_H
    # Kapazitive Impedanz  (kleines eps verhindert Division durch 0)
    z_c  = 1.0 / (1j * omega * np.maximum(C_F, 1e-30))
    return z_rl * z_c / (z_rl + z_c)


# Alias fuer Rueckwaertskompatibilitaet
z_rlc_series = z_coil


# ---------------------------------------------------------------------------
# Fitresultat
# ---------------------------------------------------------------------------

@dataclass
class FitResult:
    """Ergebnis des Bode100-Fits."""

    L_uH: float
    R_dc_ohm: float
    k_skin: float       # [Ω / sqrt(Hz)]
    k_prox: float       # [Ω / Hz * f0]
    C_pF: float
    f_res_MHz: float

    rmse_re_ohm: float      # RMSE des Realteils
    rmse_im_ohm: float      # RMSE des Imaginaerteils
    rmse_mag_pct: float     # RMSE |Z| relativ zum Max-|Z|

    success: bool
    message: str

    def summary(self) -> str:
        lines = [
            f"  L          = {self.L_uH:.5f} uH",
            f"  R_dc       = {self.R_dc_ohm:.5f} Ohm",
            f"  k_skin     = {self.k_skin:.4e}  [Ohm/sqrt(Hz)]",
            f"  k_prox     = {self.k_prox:.4e}  [dimensionslos*f0]",
            f"  C          = {self.C_pF:.4f} pF",
            f"  f_res      = {self.f_res_MHz:.3f} MHz",
            f"  RMSE Re(Z) = {self.rmse_re_ohm:.4f} Ohm",
            f"  RMSE Im(Z) = {self.rmse_im_ohm:.4f} Ohm",
            f"  RMSE |Z|   = {self.rmse_mag_pct:.3f} %",
            f"  Konvergenz = {'OK' if self.success else 'NICHT konvergiert'}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fit-Funktion
# ---------------------------------------------------------------------------

def fit_bode100(
    df: pd.DataFrame,
    l0_H: float,
    r0_ohm: float,
    c0_F: float,
    f_min_hz: float = 1e3,
    f_max_hz: float = 10e6,
    weight_imag: float = 1.0,
    f0_prox: float = 1e6,
) -> FitResult:
    """
    Fittet das serielle RLC-Modell an Bode100-Messdaten.

    Modell:  Z(f) = (R_s(f) + j*2pi*f*L) || (1/(j*2pi*f*C))  -- Parallelmodell
    Kein paralleler Widerstand R_p.

    Residuum:
        [Re(Z_mod) - Re(Z_meas)] +  weight_imag * [Im(Z_mod) - Im(Z_meas)]

    Args:
        df:           Bode100 DataFrame (aus load_bode100_csv)
        l0_H:         Startwert Induktivitaet [H]
        r0_ohm:       Startwert Widerstand [Ω]
        c0_F:         Startwert Kapazitaet [F]
        f_min_hz:     Untere Fit-Grenzfrequenz [Hz]
        f_max_hz:     Obere  Fit-Grenzfrequenz [Hz]
        weight_imag:  Gewichtung des Imaginaerteils im Residuum (1.0 = gleich)
        f0_prox:      Normierungsfrequenz fuer k_prox [Hz]

    Returns:
        FitResult mit gefitteten Parametern und Guete-Metriken
    """
    # --- Frequenzbereich einschraenken ---
    mask   = (df["freq_hz"] >= f_min_hz) & (df["freq_hz"] <= f_max_hz)
    df_fit = df[mask].reset_index(drop=True)

    if len(df_fit) < 10:
        _empty = FitResult(
            L_uH=l0_H * 1e6, R_dc_ohm=r0_ohm, k_skin=0.0, k_prox=0.0,
            C_pF=c0_F * 1e12,
            f_res_MHz=_f_res(l0_H, c0_F),
            rmse_re_ohm=np.nan, rmse_im_ohm=np.nan, rmse_mag_pct=np.nan,
            success=False,
            message="Zu wenige Datenpunkte im Frequenzbereich",
        )
        return _empty

    freqs   = df_fit["freq_hz"].to_numpy()
    re_meas = df_fit["re_ohm"].to_numpy()
    im_meas = df_fit["im_ohm"].to_numpy()
    z_meas  = re_meas + 1j * im_meas
    mag_meas_full = np.abs(z_meas)
    mag_max = float(np.max(mag_meas_full))

    # Log-Betrag und Phase der Messung (fuer log+phase Residuum)
    logmag_meas = np.log(np.maximum(mag_meas_full, 1e-9))
    phase_meas  = np.angle(z_meas)     # in Rad, Bereich [-pi, pi]

    # --- Startvektor und Grenzen ---
    # x = [L_H, R_dc, k_skin, k_prox, C_F]
    x0 = [l0_H, r0_ohm, 0.0, 0.0, c0_F]

    # Physikalisch motivierte Grenzen:
    # - L:      [5 % .. 1000 %] des Startwertes
    # - R_dc:   [0.01 mOhm .. 500 Ohm]
    # - k_skin: [0 .. 0.05 Ohm/sqrt(Hz)]  -- realistisch fuer PCB-Kupfer
    # - k_prox: [0 .. 0.2]                -- klein gegenueber R_dc/f0
    # - C:      [0.1 pF .. 10 nF]
    bounds_lo = [l0_H * 0.05,   1e-4,  0.0,   0.0,   0.1e-12]
    bounds_hi = [l0_H * 10.0,  500.0,  0.05,  0.2,   10e-9]

    def residuals(x: np.ndarray) -> np.ndarray:
        L, R_dc, k_skin, k_prox, C = x
        z_mod = z_coil(freqs, L, R_dc, k_skin, k_prox, C, f0_prox)

        # --- Residuum: log|Z| + Phase ---
        # Vorteil: skalenunabhaengig ueber alle Frequenzdekaden,
        # physikalisch interpretierbar, robust gegenueber Parameter-Kopplung.
        logmag_mod = np.log(np.maximum(np.abs(z_mod), 1e-9))
        phase_mod  = np.angle(z_mod)

        res_logmag = logmag_mod - logmag_meas                          # log-Betrag
        # Phasendifferenz in [-pi, pi] wickeln
        d_phase    = phase_mod - phase_meas
        d_phase    = (d_phase + np.pi) % (2 * np.pi) - np.pi          # wrapping
        res_phase  = d_phase * weight_imag

        return np.concatenate([res_logmag, res_phase])

    try:
        opt = least_squares(
            residuals, x0,
            bounds=(bounds_lo, bounds_hi),
            method="trf",
            # x_scale normiert jeden Parameter auf seine charakteristische Groesse,
            # damit numerische Gradienten korrekt berechnet werden (L~1e-6, C~1e-12!)
            x_scale=[l0_H, max(r0_ohm, 0.1), 1e-4, 0.1, c0_F],
            diff_step=1e-4,      # relative Schrittweite fuer Jacobi-Approximation
            ftol=1e-10, xtol=1e-10, gtol=1e-10,
            max_nfev=30_000,
        )
        L, R_dc, k_skin, k_prox, C = opt.x
        success = bool(opt.success) or (opt.cost < 1e-6)
        msg     = opt.message
    except Exception as exc:
        L, R_dc, k_skin, k_prox, C = x0
        success = False
        msg     = str(exc)

    # --- Guete-Metriken ---
    z_fit = z_coil(freqs, L, R_dc, k_skin, k_prox, C, f0_prox)
    rmse_re  = float(np.sqrt(np.mean((np.real(z_fit) - re_meas) ** 2)))
    rmse_im  = float(np.sqrt(np.mean((np.imag(z_fit) - im_meas) ** 2)))
    mag_fit  = np.abs(z_fit)
    mag_meas = np.abs(re_meas + 1j * im_meas)
    rmse_mag = float(
        np.sqrt(np.mean(((mag_fit - mag_meas) / max(mag_max, 1e-9)) ** 2)) * 100
    )

    return FitResult(
        L_uH=L * 1e6,
        R_dc_ohm=R_dc,
        k_skin=k_skin,
        k_prox=k_prox,
        C_pF=C * 1e12,
        f_res_MHz=_f_res(L, C),
        rmse_re_ohm=rmse_re,
        rmse_im_ohm=rmse_im,
        rmse_mag_pct=rmse_mag,
        success=success,
        message=msg,
    )


def _f_res(L_H: float, C_F: float) -> float:
    """Resonanzfrequenz f_res = 1/(2π√LC) [MHz]."""
    if L_H > 0 and C_F > 0:
        return 1.0 / (2.0 * np.pi * np.sqrt(L_H * C_F)) / 1e6
    return 0.0
