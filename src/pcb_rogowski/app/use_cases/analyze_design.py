"""
Use-Case: Einzeldesign vollstaendig analysieren.

Orchestriert alle Domain-Services und liefert ein konsolidiertes
Ergebnisobjekt fuer die GUI (Tab 3 + Tab 4) und CLI-Skripte.

Pipeline:
    1. Gerber laden                   -> Board
    2. Klassifikation                 -> ClassificationSpec  (+ TopologyGapFiller)
    3. TraceLayout                    -> fuer Coil-/Mutual-Services
    4. Stackup                        -> Materialparameter
    5. CoilParameterServiceImpl       -> L, R, C, f_res  (+ CalculationTrace)
    6. Via-Fenster laden (YAML)       -> ViaWindow[]
    7. MutualInductanceCalculator     -> M_prim          (+ CalculationTrace)
    8. Bode100-CSV laden + fit_bode100 -> FitResult       (optional)

Alle Formeln liegen in den Domain-Modulen -- dieser Use-Case nimmt nur
die Verdrahtung und Default-Pfade vor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from pcb_rogowski.domain.board.models import Board
from pcb_rogowski.domain.coil.fitting import (
    FitResult,
    estimate_from_data,
    fit_bode100,
    load_bode100_csv,
)
from pcb_rogowski.domain.coil.models import CoilParameters
from pcb_rogowski.domain.coil.service import CoilParameterServiceImpl
from pcb_rogowski.domain.coil.transfer_function import EquivalentCircuit
from pcb_rogowski.domain.mutual.calculator import (
    ConductorConfig,
    MutualInductanceCalculator,
)
from pcb_rogowski.domain.mutual.models import MutualInductanceResult
from pcb_rogowski.domain.stackup.models import Stackup
from pcb_rogowski.domain.trace.classifier import (
    ClassificationSpec,
    ClassifierConfig,
    FishboneClassifier,
    TopologyGapFiller,
)
from pcb_rogowski.domain.trace.models import TraceLayout, ViaWindow
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.infrastructure.stackup.loader import StackupLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eingabe / Ausgabe
# ---------------------------------------------------------------------------

@dataclass
class DesignInputs:
    """Alle Eingabepfade eines Designs (GUI-Tab 1 befuellt dieses Objekt)."""

    name: str
    gerber_dir: Path
    classification_yaml: Path | None = None
    windows_yaml: Path | None = None
    stackup_yaml: Path | None = None
    bode100_csv: Path | None = None
    defaults_yaml: Path | None = None
    temperature_celsius: float = 20.0
    method_mutual: str = "field_integral"  # "analytical" | "field_integral" | "numerical"


@dataclass
class AnalysisResult:
    """Alles, was die GUI aus einem Design anzeigt."""

    design_name: str
    board: Board
    spec: ClassificationSpec
    layout: TraceLayout
    stackup: Stackup | None

    coil: CoilParameters
    mutual: MutualInductanceResult | None
    windows: list[ViaWindow] = field(default_factory=list)
    conductor: "ConductorConfig | None" = None

    # Optional: Messung + Fit
    bode_df: pd.DataFrame | None = None
    fit: FitResult | None = None

    # Zusaetzliche Info fuer Tab 3 Tabelle
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def equivalent_circuit(self) -> EquivalentCircuit:
        """Passendes EquivalentCircuit-Objekt fuer Tab 4-Plots."""
        m_H = (self.mutual.m_total_nH * 1e-9) if self.mutual else 0.0
        return EquivalentCircuit(
            L_H=self.coil.l_total_uH * 1e-6,
            R_ohm=self.coil.r_series_ohm,
            C_F=self.coil.c_series_pF * 1e-12,
            M_H=m_H,
        )

    @property
    def equivalent_circuit_fit(self) -> EquivalentCircuit | None:
        """Ersatzschaltbild aus dem Bode100-Fit (falls vorhanden)."""
        if self.fit is None:
            return None
        return EquivalentCircuit(
            L_H=self.fit.L_uH * 1e-6,
            R_ohm=self.fit.R_dc_ohm,
            C_F=self.fit.C_pF * 1e-12,
            M_H=(self.mutual.m_total_nH * 1e-9) if self.mutual else 0.0,
        )


# ---------------------------------------------------------------------------
# Fenster-YAML laden (zentrale Kopie der Logik aus scripts/calculate_mutual.py)
# ---------------------------------------------------------------------------

def load_windows_yaml(path: Path) -> tuple[list[ViaWindow], float]:
    """Liest eine ``windows_Design_X.yaml`` und gibt (Fenster, h_via_mm) zurueck."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    h_via_mm = float(data.get("h_via_mm", 1.12268))
    windows: list[ViaWindow] = []
    for wd in data.get("windows", []):
        va = wd.get("via_a_xy")
        vb = wd.get("via_b_xy")
        windows.append(ViaWindow(
            window_id=wd["window_id"],
            x_min_mm=float(wd["x_min_mm"]),
            y_min_mm=float(wd["y_min_mm"]),
            x_max_mm=float(wd["x_max_mm"]),
            y_max_mm=float(wd["y_max_mm"]),
            sigma=int(wd.get("sigma", 1)),
            via_a_xy=tuple(va) if va else None,
            via_b_xy=tuple(vb) if vb else None,
            dist_mm=float(wd["dist_mm"]) if "dist_mm" in wd else None,
            h_via_mm=float(wd.get("h_via_mm", h_via_mm)),
        ))
    return windows, h_via_mm


def _coil_center(windows: list[ViaWindow]) -> tuple[float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for w in windows:
        for v in (w.via_a_xy, w.via_b_xy):
            if v is not None:
                xs.append(v[0])
                ys.append(v[1])
    if not xs:
        for w in windows:
            xs.append((w.x_min_mm + w.x_max_mm) / 2)
            ys.append((w.y_min_mm + w.y_max_mm) / 2)
    return (sum(xs) / len(xs) if xs else 0.0,
            (min(ys) + max(ys)) / 2.0 if ys else 0.0)


def _busbar_from_geometry_yaml(
    path: Path,
    cx: float,
    cy: float,
) -> ConductorConfig:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    bus = cfg.get("busbar", {})
    width = float(bus.get("width_mm", 10.0))
    offset = float(bus.get("center_offset_mm", 0.0))
    sep = str(bus.get("separation_axis", "y"))
    if sep == "y":
        return ConductorConfig(
            x1_mm=cx, y1_mm=cy + offset - width / 2.0,
            x2_mm=cx, y2_mm=cy + offset + width / 2.0,
        )
    return ConductorConfig(
        x1_mm=cx + offset - width / 2.0, y1_mm=cy,
        x2_mm=cx + offset + width / 2.0, y2_mm=cy,
    )


# ---------------------------------------------------------------------------
# Haupt-Use-Case
# ---------------------------------------------------------------------------

def analyze_design(
    inputs: DesignInputs,
    *,
    geometry_yaml: Path | None = None,
    progress_cb: Any = None,
) -> AnalysisResult:
    """
    Fuehrt die komplette Pipeline fuer ein Design aus.

    Args:
        inputs:        Design-Eingaben (Pfade + Parameter).
        geometry_yaml: ``configs/geometry_baseline.yaml`` fuer Busbar-Konfiguration.
        progress_cb:   Optionaler Callback ``(step: str, frac: float)`` fuer GUI.
    """
    def _prog(step: str, frac: float) -> None:
        logger.info("[analyze_design] %s", step)
        if progress_cb is not None:
            try:
                progress_cb(step, frac)
            except Exception:  # pragma: no cover
                pass

    # 1. Gerber laden
    _prog("Lade Gerber", 0.05)
    board = GerberBoardLoader().load_from_gerber(inputs.gerber_dir)

    # 2. Klassifikation
    _prog("Klassifikation", 0.20)
    if inputs.classification_yaml and inputs.classification_yaml.exists():
        spec = ClassificationSpec.from_yaml(inputs.classification_yaml)
        spec = TopologyGapFiller().fill(board, spec)
    else:
        cfg = (ClassifierConfig.from_yaml(inputs.defaults_yaml)
               if inputs.defaults_yaml and inputs.defaults_yaml.exists()
               else ClassifierConfig())
        spec = FishboneClassifier(cfg).classify(board)

    layout = spec.to_trace_layout()

    # 3. Stackup
    _prog("Lade Stackup", 0.30)
    stackup: Stackup | None = None
    if inputs.stackup_yaml and inputs.stackup_yaml.exists():
        stackup = StackupLoader.from_yaml(inputs.stackup_yaml)

    # 4. Coil-Parameter (L, R, C, f_res)  -- inkl. voller CalculationTrace
    _prog("Berechne L, R, C", 0.50)
    coil = CoilParameterServiceImpl().calculate(
        layout=layout,
        board=board,
        temperature_celsius=inputs.temperature_celsius,
    )

    # 5. Mutual (falls Fensterdefinition vorhanden)
    mutual: MutualInductanceResult | None = None
    conductor_out: ConductorConfig | None = None
    windows: list[ViaWindow] = []
    if inputs.windows_yaml and inputs.windows_yaml.exists():
        _prog("Berechne M_prim", 0.70)
        windows, h_via_mm = load_windows_yaml(inputs.windows_yaml)
        cx, cy = _coil_center(windows)
        if geometry_yaml and geometry_yaml.exists():
            conductor = _busbar_from_geometry_yaml(geometry_yaml, cx, cy)
        else:
            conductor = ConductorConfig(
                x1_mm=cx, y1_mm=cy - 11.0,
                x2_mm=cx, y2_mm=cy + 11.0,
            )
        calc = MutualInductanceCalculator(
            conductor=conductor,
            method=inputs.method_mutual,
            grid_n=50,
        )
        mutual = calc.compute(windows, h_eff_mm=h_via_mm)
        conductor_out = conductor

    # 6. Bode100 laden + fit
    bode_df = None
    fit: FitResult | None = None
    if inputs.bode100_csv and inputs.bode100_csv.exists():
        _prog("Lade Bode100 + Fit", 0.90)
        try:
            bode_df = load_bode100_csv(inputs.bode100_csv)
            l0_H, r0, c0 = estimate_from_data(bode_df)
            fit = fit_bode100(
                df=bode_df, l0_H=l0_H, r0_ohm=r0, c0_F=c0,
                f_min_hz=100.0,
                f_max_hz=float(bode_df["freq_hz"].max()),
            )
        except Exception as exc:
            logger.error("Bode100-Fit fehlgeschlagen: %s", exc)

    _prog("Fertig", 1.0)

    return AnalysisResult(
        design_name=inputs.name,
        board=board,
        spec=spec,
        layout=layout,
        stackup=stackup,
        coil=coil,
        mutual=mutual,
        windows=windows,
        conductor=conductor_out,
        bode_df=bode_df,
        fit=fit,
    )
