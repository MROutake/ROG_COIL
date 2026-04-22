"""
CoilParameterServiceImpl: Berechnung aller elektrischen Parameter einer
PCB-Rogowski-Spule.

Implementiert das CoilParameterService-Protocol aus dem App-Layer.

Berechnete Größen (mit vollständigem CalculationTrace je Schritt):
    L_track  Induktivität der Windungsleiter  [µH]
    L_vias   Induktivität der Vias            [µH]
    L_trace  Induktivität der Anschlussleitung[µH]
    L_C      Gesamtinduktivität = Summe       [µH]
    R_C      Ohmscher Serienwiderstand (temp.)[Ω]
    C_C      Parasitische Kapazität           [pF]
    f_res    Eigenresonanzfrequenz            [MHz]

L_track-Formeln (wählbar über ``mode``):
    "simplified" (Standard):
        L_track = µ₀·l / (2π) · ln(5.98·H / (0.8·W + T))

    "microstrip" (vollständig):
        W_eff → Z (Mikrostreifen) → P_delay → L_track = Z · P_delay · l
"""

from __future__ import annotations

import math
from datetime import datetime

from pcb_rogowski.domain.board.models import Board
from pcb_rogowski.domain.coil.geometry import GeometryExtractor, GeometryParameters
from pcb_rogowski.domain.coil.models import CoilParameters
from pcb_rogowski.domain.common.trace import CalculationTrace, QualityStatus, TraceStep
from pcb_rogowski.domain.formulas import FORMULAS
from pcb_rogowski.domain.stackup.models import MaterialSet
from pcb_rogowski.domain.trace.models import TraceLayout

# Physikalische Konstanten (SI)
_MU_0: float = 1.2566370614e-6    # H/m
_EPS_0: float = 8.8541878128e-12  # F/m


class CoilParameterServiceImpl:
    """
    Berechnet alle elektrischen Parameter einer PCB-Rogowski-Spule.

    Berechnungsmodell:
        L_track  Selbstinduktivität der Windungssegmente (Ruehli/Lorenz)
        L_vias   Via-Induktivität
        L_trace  Anschlussleitung (Ruehli/Lorenz)
        C_C      Interleiter-Kapazität (zwischen den Windungsleitern)

    Args:
        materials: Materialkonstanten. Standard: Kupfer bei 20 °C.
        extractor: GeometryExtractor-Instanz. Standard: GeometryExtractor().
    """

    def __init__(
        self,
        materials: MaterialSet | None = None,
        extractor: GeometryExtractor | None = None,
        *,
        mode: str | None = None,   # veraltet, wird ignoriert
    ) -> None:
        if mode is not None:
            import warnings
            warnings.warn(
                "Parameter 'mode' ist veraltet und wird ignoriert. "
                "L_track wird jetzt immer per Selbstinduktivität (Ruehli/Lorenz) berechnet.",
                DeprecationWarning,
                stacklevel=2,
            )
        self._materials = materials or MaterialSet()
        self._extractor = extractor or GeometryExtractor()

    # ------------------------------------------------------------------
    # Öffentliche API (CoilParameterService Protocol)
    # ------------------------------------------------------------------

    def calculate(
        self,
        layout: TraceLayout,
        board: Board,
        temperature_celsius: float = 20.0,
        geometry: GeometryParameters | None = None,
    ) -> CoilParameters:
        """
        Berechnet CoilParameters aus klassifiziertem TraceLayout und Board.

        Args:
            layout:              Klassifiziertes TraceLayout.
            board:               Geladenes Board-Domainobjekt.
            temperature_celsius: Betriebstemperatur für R_C-Korrektur [°C].
            geometry:            Vorberechnete GeometryParameters (optional).
                                 Falls None, wird der GeometryExtractor aufgerufen.

        Returns:
            CoilParameters mit allen elektrischen Größen und CalculationTrace.
        """
        if geometry is None:
            geometry = self._extractor.extract(layout, board)

        steps: list[TraceStep] = []
        warnings: list[str] = []

        # Geometrie-Schritt dokumentieren
        steps.append(TraceStep(
            name="Geometrie-Parameter",
            formula=FORMULAS["geometry_extract"].latex,
            inputs={
                "W_mm": geometry.W_mm,
                "H_mm": geometry.H_mm,
                "T_mm": geometry.T_mm,
                "l_track_mm": geometry.l_track_mm,
                "h_via_mm": geometry.h_via_mm,
                "d_via_mm": geometry.d_via_mm,
                "n_vias": float(geometry.n_vias),
                "l_trace_mm": geometry.l_trace_mm,
                "eps_r": geometry.epsilon_r,
                "N_turns": float(geometry.N_turns),
                "p_mm": geometry.p_mm,
            },
            output=float(geometry.N_turns),
            unit="–",
            note=f"Winding-Lage: {geometry.winding_layer}",
        ))

        # --- L_track ---
        l_track_H = self._calc_l_track(geometry, steps, warnings)

        # --- L_vias ---
        l_vias_H = self._calc_l_vias(geometry, steps, warnings)

        # --- L_trace ---
        l_trace_H = self._calc_l_trace(geometry, steps, warnings)

        # --- L_C = Summe ---
        l_total_H = l_track_H + l_vias_H + l_trace_H
        steps.append(TraceStep(
            name="L_C – Gesamtinduktivität",
            formula=FORMULAS["L_total"].latex,
            inputs={
                "L_track_uH": l_track_H * 1e6,
                "L_vias_uH": l_vias_H * 1e6,
                "L_trace_uH": l_trace_H * 1e6,
            },
            output=l_total_H * 1e6,
            unit="µH",
        ))

        # --- R_C ---
        r_series_ohm = self._calc_r_series(geometry, temperature_celsius, steps, warnings)

        # --- C_C ---
        c_series_F = self._calc_c_series(geometry, steps, warnings)

        # --- f_res ---
        if l_total_H > 0.0 and c_series_F > 0.0:
            f_res_hz = 1.0 / (2.0 * math.pi * math.sqrt(l_total_H * c_series_F))
        else:
            f_res_hz = 0.0
            warnings.append("L_C oder C_C ist 0 – Eigenresonanzfrequenz nicht berechenbar.")

        steps.append(TraceStep(
            name="f_res – Eigenresonanzfrequenz",
            formula=FORMULAS["f_res"].latex,
            inputs={"L_C_uH": l_total_H * 1e6, "C_C_pF": c_series_F * 1e12},
            output=f_res_hz * 1e-6,
            unit="MHz",
            note=f"ω_r = 1/√(L_C·C_C) = {1.0/math.sqrt(max(l_total_H * c_series_F, 1e-30)):.3e} rad/s" if l_total_H > 0 and c_series_F > 0 else None,
        ))

        # Qualitätsstatus
        status = QualityStatus.WARNING if warnings else QualityStatus.OK
        if l_total_H <= 0.0 or r_series_ohm <= 0.0:
            status = QualityStatus.ERROR

        trace = CalculationTrace(
            calculation_name="CoilParameterService",
            steps=tuple(steps),
            warnings=tuple(warnings),
            quality_status=status,
            source_files=(board.source_file,),
            config_versions={"l_track_model": "self_inductance_ruehli"},
            timestamp=datetime.now().isoformat(),
        )

        return CoilParameters(
            l_track_uH=l_track_H * 1e6,
            l_vias_uH=l_vias_H * 1e6,
            l_trace_uH=l_trace_H * 1e6,
            l_total_uH=l_total_H * 1e6,
            r_series_ohm=r_series_ohm,
            c_series_pF=c_series_F * 1e12,
            resonance_mhz=f_res_hz * 1e-6,
            trace=trace,
        )

    # ------------------------------------------------------------------
    # L_track  (Selbstinduktivität nach Ruehli/Lorenz, pro Segment)
    # ------------------------------------------------------------------

    def _calc_l_track(
        self,
        g: GeometryParameters,
        steps: list[TraceStep],
        warnings: list[str],
    ) -> float:
        """Selbstinduktivität der Windungssegmente [H].

        Registry-Key
        ------------
        ``L_track_self_segment``  (siehe :mod:`pcb_rogowski.domain.formulas`).

        Physik
        ------
        Jedes Kupfersegment wird einzeln als gerader Rechteckleiter im
        Freiraum modelliert (Ruehli/Lorenz, IBM 1972)::

            L_self,i = µ₀·l_i / (2π) · [ln(2·l_i/(w+t)) + 0.5 + 0.2235·(w+t)/l_i]

        Die Gesamtlänge der WINDING-Segmente wird gleichmäßig auf
        ``n_seg = 2·N_turns`` Segmente aufgeteilt (je Windung ein Top-
        und ein Bottom-Segment, Fishbone-Topologie)::

            L_track = Σ L_self,i = n_seg · L_self(l_track / n_seg)

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * Keine durchgehende GND-Plane (sonst wäre ein Mikrostreifen-
          Modell nötig -- L wäre um Faktor 2-5 kleiner).
        * Gegeninduktivitäten zwischen benachbarten Segmenten werden
          vernachlässigt (OK bei Fishbone mit p ≳ 2·W).
        * Freiraum-Näherung: gilt für ``l_i ≫ (w+t)``  (typ. l_i/w > 5).

        Sanity-Zahl
        -----------
        Design 03 (N=40, l_track ≈ 320 mm, W=0.25 mm, T=35 µm):
        L_track ≈ 0.38 µH. Abweichungen > 10 % deuten auf falsche
        Geometrie-Extraktion (Fishbone-Segmente nicht erkannt).

        Anpassung
        ---------
        Wenn diese Formel geändert wird:

        1. Neuen LaTeX-String in ``FORMULAS['L_track_self_segment'].latex``
           eintragen (GUI/Reports).
        2. Python-Code unten (`l_self_i = ...`) synchron anpassen.
        3. Herleitung in ``docs/berechnungen.md §L_track`` ergänzen.
        4. Konsistenz-Checks: ``pytest tests/unit/test_formula_registry.py``
           und ``pytest tests/golden_cases`` laufen lassen.

        Siehe auch
        ----------
        ``docs/FORMELN-ANPASSEN.md``  -- vollständiger Konsistenz-Workflow.
        """
        l_total = g.l_track_mm * 1e-3   # Gesamtlänge aller Winding-Segmente [m]
        W = g.W_mm * 1e-3
        T = g.T_mm * 1e-3
        wt = W + T

        if l_total <= 0.0:
            warnings.append("l_track = 0 mm – keine WINDING-Segmente im TraceLayout.")
            return 0.0
        if wt <= 0.0:
            warnings.append("W + T ≤ 0 – L_track-Berechnung nicht möglich.")
            return 0.0

        # Anzahl Segmente: 2 pro Windung (Top + Bottom)
        n_seg = max(2 * g.N_turns, 1)
        l_i = l_total / n_seg  # mittlere Segmentlänge [m]

        # Selbstinduktivität pro Segment (Ruehli/Lorenz)
        l_self_i = (_MU_0 * l_i / (2.0 * math.pi)) * (
            math.log(2.0 * l_i / max(wt, 1e-12))
            + 0.5
            + 0.2235 * wt / l_i
        )

        # Summe über alle Segmente
        l_track_H = n_seg * l_self_i

        steps.append(TraceStep(
            name="L_track – Selbstinduktivität (Ruehli/Lorenz, pro Segment)",
            formula=FORMULAS["L_track_self_segment"].latex,
            inputs={
                "l_track_mm": g.l_track_mm,
                "n_seg": float(n_seg),
                "l_i_mm": l_i * 1e3,
                "W_mm": g.W_mm,
                "T_mm": g.T_mm,
                "w_plus_t_mm": wt * 1e3,
                "L_self_i_nH": l_self_i * 1e9,
            },
            output=l_track_H * 1e6,
            unit="µH",
            note=(
                f"Ruehli/Lorenz Freiraum-Selbstinduktivität, "
                f"{n_seg} Segmente à {l_i*1e3:.3f} mm. "
                f"Kein Mikrostreifen-Modell (keine GND-Plane)."
            ),
        ))
        return l_track_H

    # ------------------------------------------------------------------
    # L_vias
    # ------------------------------------------------------------------

    def _calc_l_vias(
        self,
        g: GeometryParameters,
        steps: list[TraceStep],
        warnings: list[str],
    ) -> float:
        """Induktivität aller Vias im Windungspfad [H].

        Registry-Key
        ------------
        ``L_vias``  (siehe :mod:`pcb_rogowski.domain.formulas`).

        Physik
        ------
        Zylindrischer Einzeldraht (Goldfarb & Pucel 1991)::

            L_via  = µ₀·h / (2π) · (1 + ln(4·h/d))
            L_vias = n_vias · L_via    (Serienschaltung entlang Pfad)

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * ``4h/d > 1`` erforderlich (sonst ln < 0 → unphysikalisch);
          wird per ``max(ratio, 1.0001)`` abgefangen.
        * Keine Skin-Effekt-Korrektur (bei f < 10 MHz vernachlässigbar
          für typ. h=1.6 mm-Vias).
        * Gegeninduktivität zwischen benachbarten Vias vernachlässigt
          (valid für Pitch > 3·d).

        Sanity-Zahl
        -----------
        Standard 1.6 mm-Via mit d=0.3 mm: L_via ≈ 1.0 nH. 80 Vias
        → L_vias ≈ 80 nH. Bei 4-Layer-PCB (h=0.4 mm) entsprechend
        L_via ≈ 0.23 nH.

        Anpassung
        ---------
        Alternative Modelle (z. B. mit Via-Barrel-Kopplung, Wheeler-
        Näherung, Koaxial-Formel bei GND-Ring) können hier eingesetzt
        werden. Workflow: ``docs/FORMELN-ANPASSEN.md``.
        """
        h = g.h_via_mm * 1e-3
        d = g.d_via_mm * 1e-3
        n = g.n_vias

        if h <= 0.0 or d <= 0.0:
            warnings.append("h_via oder d_via = 0 – L_vias = 0.")
            return 0.0
        if n == 0:
            warnings.append("n_vias = 0 – Via-Anzahl aus Bohrlage prüfen; L_vias = 0.")
            return 0.0

        ratio = 4.0 * h / d
        l_single_H = (_MU_0 * h / (2.0 * math.pi)) * (1.0 + math.log(max(ratio, 1.0001)))
        l_vias_H = n * l_single_H

        steps.append(TraceStep(
            name="L_vias – Induktivität der Vias",
            formula=FORMULAS["L_vias"].latex,
            inputs={
                "h_via_mm": g.h_via_mm,
                "d_via_mm": g.d_via_mm,
                "n_vias": float(n),
                "L_single_nH": l_single_H * 1e9,
            },
            output=l_vias_H * 1e9,
            unit="nH",
        ))
        return l_vias_H

    # ------------------------------------------------------------------
    # L_trace
    # ------------------------------------------------------------------

    def _calc_l_trace(
        self,
        g: GeometryParameters,
        steps: list[TraceStep],
        warnings: list[str],
    ) -> float:
        """Induktivität der Anschlussleitung (CONNECTION-Segmente) [H].

        Registry-Key
        ------------
        ``L_trace``  (siehe :mod:`pcb_rogowski.domain.formulas`).

        Physik
        ------
        Identische Ruehli/Lorenz-Formel wie ``_calc_l_track``, aber auf
        die als CONNECTION klassifizierten Segmente angewendet (Leitung
        vom Spulenanfang zum Anschlusspunkt)::

            L_trace = µ₀·l / (2π) · (ln(2l/w) + 0.5 + 0.2235·w/l)

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * Single-ended Leitung im Freiraum.
        * Keine Kopplung zur Spule selbst (meist OK, weil CONNECTION
          außerhalb des Windungsbereichs liegt).
        * ``l > w`` für logarithmische Konvergenz.

        Sanity-Zahl
        -----------
        Typ. l=30 mm, w=0.5 mm: L_trace ≈ 28 nH. Größenordnung der
        L_vias und damit nicht vernachlässigbar!

        Anpassung
        ---------
        Siehe ``docs/FORMELN-ANPASSEN.md``. Dieselbe Formel wie
        ``_calc_l_track`` -- bei Änderungen beide synchron halten
        (oder eine gemeinsame Helper-Funktion extrahieren).
        """
        l = g.l_trace_mm * 1e-3
        w = g.w_trace_mm * 1e-3

        if l <= 0.0 or w <= 0.0:
            # Keine Anschlussleitung klassifiziert → kein Fehler, nur Info
            return 0.0

        l_trace_H = (_MU_0 * l / (2.0 * math.pi)) * (
            math.log(2.0 * l / max(w, 1e-9)) + 0.5 + 0.2235 * (w / l)
        )
        steps.append(TraceStep(
            name="L_trace – Induktivität der Anschlussleitung",
            formula=FORMULAS["L_trace"].latex,
            inputs={"l_trace_mm": g.l_trace_mm, "w_trace_mm": g.w_trace_mm},
            output=l_trace_H * 1e9,
            unit="nH",
        ))
        return l_trace_H

    # ------------------------------------------------------------------
    # R_C
    # ------------------------------------------------------------------

    def _calc_r_series(
        self,
        g: GeometryParameters,
        temperature_celsius: float,
        steps: list[TraceStep],
        warnings: list[str],
    ) -> float:
        """Temperaturbehafteter DC-Serienwiderstand [Ω].

        Registry-Key
        ------------
        ``R_series``  (siehe :mod:`pcb_rogowski.domain.formulas`).

        Physik
        ------
        DC-Näherung mit linearem Temperatur-Koeffizient::

            ρ(T) = ρ₂₀ · (1 + α·(T − 20 °C))
            R_C  = ρ(T) · l_total / (W · T_cu)

        mit ``l_total = l_track + l_trace`` und ``A = W·T_cu``.

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * DC / niederfrequent (kein Skin-Effekt -- bei f < ca. 1 MHz OK,
          bei höheren Frequenzen separat ``skin.r_ac(freq)`` nutzen).
        * Konstante Temperatur über die gesamte Länge.
        * Via-Widerstand vernachlässigt (Via-Barrel Cu-plating
          ≈ 25 µm, typ. < 5 mΩ pro Via, vs. Track ~ 100 mΩ).

        Sanity-Zahl
        -----------
        Cu @ 25 °C, l=350 mm, W=0.25 mm, T=35 µm:
        R_C ≈ 1.72e-8 · 0.35 / (2.5e-4 · 3.5e-5) ≈ 0.69 Ω.

        Anpassung
        ---------
        Für frequenzabhängige Modelle siehe ``domain/coil/skin.py``;
        die Registry behält die DC-Formel. Workflow bei Änderungen:
        ``docs/FORMELN-ANPASSEN.md``.
        """
        rho_20 = self._materials.rho_cu_ohm_m
        alpha = self._materials.temperature_coefficient_cu
        rho_T = rho_20 * (1.0 + alpha * (temperature_celsius - 20.0))

        W = g.W_mm * 1e-3
        T_cu = g.T_mm * 1e-3
        l_total = (g.l_track_mm + g.l_trace_mm) * 1e-3
        A = W * T_cu

        if A <= 0.0 or l_total <= 0.0:
            warnings.append("Querschnittsfläche A oder l_total = 0 – R_C nicht berechenbar.")
            return 0.0

        r_ohm = rho_T * l_total / A
        steps.append(TraceStep(
            name="R_C – Serienwiderstand (temperaturkorrigiert)",
            formula=FORMULAS["R_series"].latex,
            inputs={
                "rho_20_nΩm": rho_20 * 1e9,
                "alpha_1_K": alpha,
                "T_celsius": temperature_celsius,
                "l_total_mm": g.l_track_mm + g.l_trace_mm,
                "W_mm": g.W_mm,
                "T_cu_mm": g.T_mm,
                "A_mm2": A * 1e6,
            },
            output=r_ohm,
            unit="Ω",
        ))
        return r_ohm

    # ------------------------------------------------------------------
    # C_C  (Interleiter-Kapazität)
    # ------------------------------------------------------------------

    def _calc_c_series(
        self,
        g: GeometryParameters,
        steps: list[TraceStep],
        warnings: list[str],
    ) -> float:
        """Interleiter-Kapazität zwischen benachbarten Windungszähnen [F].

        Registry-Key
        ------------
        ``C_interturn_cps``  (siehe :mod:`pcb_rogowski.domain.formulas`).

        Modell
        ------
        Koplanare Streifen (CPS) *ohne* Grundebene. Die Windungszähne
        liegen als parallele Leiter auf der PCB-Oberfläche -- da keine
        durchgehende Massefläche existiert, dominiert die Kante-zu-
        Kante-Kapazität über die Kapazität gegen GND.

        Kapazitätsbelag pro benachbartem Leiterpaar::

            C'_CPS = ε₀ · ε_eff · K(k') / K(k)    [F/m]

        mit::

            s     = p - W                  (Lücke Kante-zu-Kante)
            k     = s / (s + 2·W)          (CPS-Modulparameter)
            k'    = √(1 - k²)
            ε_eff = (1 + εr) / 2           (halb Substrat, halb Luft)

        ``K(k)/K(k')`` wird per Hilberg-Näherung approximiert
        (max. Fehler 3e-6 über gesamtem k-Bereich).

        Gesamtkapazität::

            C_C     = C'_CPS · l_seg · N_pairs
            N_pairs = 2 · (N - 1)           (je Seite ein Nachbarpaar)
            l_seg   = l_track / (2 · N)     (mittlere Zahnlänge)

        Annahmen / Gültigkeitsbereich
        -----------------------------
        * Keine GND-Plane auf benachbarter Lage (sonst dominiert C_gnd
          und das CPS-Modell unterschätzt um Faktor 5-20).
        * p > W  (sonst s ≤ 0 → Windungen überlappen sich).
        * N ≥ 2  (mindestens ein Paar).
        * Quasi-statische Näherung (gilt bis Wellenlänge ≫ l_seg,
          d. h. f < ~1 GHz für typ. 50 mm-Zähne).

        Sanity-Zahl
        -----------
        FR-4, εr=4.4, W=0.25 mm, p=0.6 mm, N=40, l_track=320 mm:
        → s=0.35 mm, k≈0.41, K(k)/K(k')≈0.78,
           C'_CPS ≈ 24 pF/m, l_seg=4 mm, N_pairs=78
           → C_C ≈ 7.5 pF. Bei Abweichungen > 20 % zum Bode100-Fit
           ist meist ein verstecktes GND-Pad auf der Gegenlage der
           Übeltater.

        Anpassung
        ---------
        Alternative Modelle:
        * Mit GND: ``ε_eff = ε_r`` und Mikrostreifen-Kapazität.
        * Exakte Elliptic Integrals statt Hilberg: ``scipy.special.ellipk``.
        Siehe ``docs/FORMELN-ANPASSEN.md``.
        """
        W = g.W_mm * 1e-3        # Spurenbreite [m]
        p = g.p_mm * 1e-3        # Pitch (Mitte-Mitte) [m]
        l = g.l_track_mm * 1e-3  # Gesamtlänge Windungsleiter [m]
        eps_r = g.epsilon_r
        N = g.N_turns

        s = p - W   # Kante-zu-Kante Abstand [m]

        if s <= 0.0 or W <= 0.0 or l <= 0.0 or N < 2:
            if s <= 0.0:
                warnings.append(
                    f"Pitch ({g.p_mm:.3f} mm) ≤ Spurenbreite ({g.W_mm:.3f} mm) "
                    f"– C_C nicht berechenbar."
                )
            return 0.0

        # CPS-Modulparameter
        k = s / (s + 2.0 * W)
        k_sq = k * k
        kp = math.sqrt(1.0 - k_sq)   # k'

        # Hilberg-Näherung für K(k)/K(k')
        inv_sqrt2 = 1.0 / math.sqrt(2.0)
        if k <= inv_sqrt2:
            # K(k)/K(k') ≈ π / ln(2·(1+√k')/(1-√k'))
            sqrt_kp = math.sqrt(kp)
            ratio_KK = math.pi / math.log(2.0 * (1.0 + sqrt_kp) / max(1.0 - sqrt_kp, 1e-15))
        else:
            # K(k)/K(k') ≈ (1/π) · ln(2·(1+√k)/(1-√k))
            sqrt_k = math.sqrt(k)
            ratio_KK = (1.0 / math.pi) * math.log(2.0 * (1.0 + sqrt_k) / max(1.0 - sqrt_k, 1e-15))

        # K(k')/K(k) = Kehrwert
        ratio_KpK = 1.0 / max(ratio_KK, 1e-15)

        # Effektive Permittivität (CPS ohne Grundebene: halb Substrat, halb Luft)
        eps_eff = (1.0 + eps_r) / 2.0

        # Kapazitätsbelag [F/m] pro Leiterpaar
        c_prime = _EPS_0 * eps_eff * ratio_KpK

        # Kopplungslänge und Paare
        n_pairs = 2 * (N - 1)             # Top- und Bottom-Paare
        l_seg = l / max(2 * N, 1)          # mittlere Segmentlänge [m]
        c_F = c_prime * l_seg * n_pairs

        steps.append(TraceStep(
            name="C_C – Interleiter-Kapazität (CPS-Modell)",
            formula=FORMULAS["C_interturn_cps"].latex,
            inputs={
                "eps_r": eps_r,
                "eps_eff": eps_eff,
                "W_mm": g.W_mm,
                "p_mm": g.p_mm,
                "s_mm": s * 1e3,
                "k": k,
                "kp": kp,
                "K(k)/K(k')": ratio_KK,
                "C'_CPS_pF_m": c_prime * 1e12,
                "l_seg_mm": l_seg * 1e3,
                "N_pairs": float(n_pairs),
            },
            output=c_F * 1e12,
            unit="pF",
            note=(
                "Koplanare Streifen (CPS) ohne Grundebene. "
                "Kapazität zwischen benachbarten Windungsleitern."
            ),
        ))
        return c_F
