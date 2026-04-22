"""
Tab 3 -- Berechnung des Ersatzschaltbildes.

Aufbau
------
Oben:    KPI-Leiste (L, R, C, f_res, M) + Run-Button + Progressbar.
Mitte:   Unter-Tabs
         - "Ersatzschaltbild"  : Schema L/R/C/M
         - "Windungsfenster"   : h_via x Laenge schematisch
         - "B-Feld"            : XY-Schnitt mit Leitern + Fenstern
Unten:   Trace-Tabs (Coil / Mutual) mit LaTeX-Formelanzeige.

Die Rechenmethode fuer M ist fest auf ``field_integral`` gesetzt --
Temperatur kommt aus dem Design.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pcb_rogowski.app.use_cases.analyze_design import AnalysisResult, analyze_design
from pcb_rogowski.ui.desktop.shared.analysis_vis import (
    BFieldCanvas, SchematicCanvas, TransferFunctionCanvas, WindowGeometryCanvas,
)
from pcb_rogowski.ui.desktop.shared.kpi_card import KpiCard
from pcb_rogowski.ui.desktop.shared.project_state import ProjectState
from pcb_rogowski.ui.desktop.shared.trace_view import CalculationTraceView
from pcb_rogowski.ui.desktop.shared.worker import Worker


class AnalysisTab(QWidget):
    """Berechnungs-Tab mit KPI-Karten, Visualisierungen und Trace."""

    def __init__(self, state: ProjectState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._result: AnalysisResult | None = None
        self._build_ui()
        self.state.selection_changed.connect(lambda _: self._on_result_changed())
        self.state.analysis_updated.connect(self._on_analysis_updated)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # === Zeile 1: Aktion + KPIs =====================================
        row_top = QHBoxLayout()

        self.btn_run = QPushButton("▶  Berechnen")
        self.btn_run.setProperty("accent", True)
        self.btn_run.setMinimumWidth(140)
        self.btn_run.clicked.connect(self._run)
        row_top.addWidget(self.btn_run)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumWidth(180)
        self.progress.setMaximumWidth(260)
        self.progress.setTextVisible(True)
        row_top.addWidget(self.progress)

        row_top.addSpacing(12)

        self.kpi_L = KpiCard("Induktivitaet L", "µH")
        self.kpi_R = KpiCard("Widerstand R",    "Ω")
        self.kpi_C = KpiCard("Kapazitaet C",    "pF")
        self.kpi_f = KpiCard("Resonanz f_res",  "MHz")
        self.kpi_M = KpiCard("Gegenind. M",     "nH")
        for k in (self.kpi_L, self.kpi_R, self.kpi_C, self.kpi_f, self.kpi_M):
            row_top.addWidget(k, 1)

        outer.addLayout(row_top)

        # === Zeile 2: Inhalt – vertikal geteilt: links Traces, rechts Plots ==
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- LINKS: Trace-Views (Coil / Mutual) --------------------------
        trace_tabs = QTabWidget()
        self.trace_coil = CalculationTraceView()
        self.trace_mutual = CalculationTraceView()
        trace_tabs.addTab(self.trace_coil, "L, R, C (Spule)")
        trace_tabs.addTab(self.trace_mutual, "M (Mutual)")

        # --- RECHTS: Visualisierungen ------------------------------------
        self.vis_tabs = QTabWidget()

        self.schem = SchematicCanvas()
        self.vis_tabs.addTab(self.schem, "Ersatzschaltbild")

        win_w = QWidget()
        wl = QHBoxLayout(win_w)
        wl.setContentsMargins(4, 4, 4, 4)
        left_w = QWidget()
        lwl = QVBoxLayout(left_w)
        lwl.addWidget(QLabel("Fenster:"))
        self.cb_window = QComboBox()
        self.cb_window.currentIndexChanged.connect(self._on_window_changed)
        lwl.addWidget(self.cb_window)
        lwl.addStretch(1)
        wl.addWidget(left_w, 0)
        self.win_canvas = WindowGeometryCanvas()
        wl.addWidget(self.win_canvas, 1)
        self.vis_tabs.addTab(win_w, "Windungsfenster")

        self.bfield = BFieldCanvas()
        bf_wrap = QWidget()
        bfl = QVBoxLayout(bf_wrap)
        bfl.setContentsMargins(4, 4, 4, 4)
        bf_ctrl = QHBoxLayout()
        self.cb_bf_traces = QCheckBox("Leiterbahnen")
        self.cb_bf_traces.setChecked(True)
        self.cb_bf_traces.toggled.connect(self._on_bfield_options)
        self.cb_bf_windows = QCheckBox("Fenster einblenden")
        self.cb_bf_windows.setChecked(False)
        self.cb_bf_windows.toggled.connect(self._on_bfield_options)
        bf_ctrl.addWidget(self.cb_bf_traces)
        bf_ctrl.addWidget(self.cb_bf_windows)
        bf_ctrl.addStretch(1)
        bfl.addLayout(bf_ctrl)
        bfl.addWidget(self.bfield, 1)
        self.vis_tabs.addTab(bf_wrap, "B-Feld XY")

        # --- Uebertragungsfunktion (neuer Sub-Tab) ----------------------
        self.tf_canvas = TransferFunctionCanvas()
        tf_wrap = QWidget()
        tfl = QVBoxLayout(tf_wrap)
        tfl.setContentsMargins(4, 4, 4, 4)
        tf_ctrl = QHBoxLayout()
        tf_ctrl.addWidget(QLabel("Uebertragungsfunktion:"))
        self.rb_tf_primary = QRadioButton("V_out / I_prim  (H)")
        self.rb_tf_primary.setChecked(True)
        self.rb_tf_primary.toggled.connect(self._on_tf_mode)
        self.rb_tf_z = QRadioButton("Klemmenimpedanz  Z")
        self.rb_tf_z.toggled.connect(self._on_tf_mode)
        tf_ctrl.addWidget(self.rb_tf_primary)
        tf_ctrl.addWidget(self.rb_tf_z)
        tf_ctrl.addStretch(1)
        tfl.addLayout(tf_ctrl)
        tfl.addWidget(self.tf_canvas, 1)
        self.vis_tabs.addTab(tf_wrap, "Uebertragungsfunktion")

        splitter.addWidget(trace_tabs)
        splitter.addWidget(self.vis_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 700])
        outer.addWidget(splitter, 1)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _run(self) -> None:
        d = self.state.current_design
        if d is None:
            return

        # Methode fest auf field_integral -------------------------------
        import copy
        d2 = (copy.replace(d, method_mutual="field_integral")
              if hasattr(copy, "replace")
              else type(d)(**{**d.__dict__, "method_mutual": "field_integral"}))
        idx = self.state.current_index
        self.state.update_design(idx, d2)

        from pathlib import Path
        root = Path(__file__).resolve().parents[5]
        geom = root / "configs" / "geometry_baseline.yaml"

        self.btn_run.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setFormat("Starte …")

        worker = Worker(analyze_design, d2,
                        geometry_yaml=geom if geom.exists() else None)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.result.connect(lambda r: self._on_done(idx, r))
        worker.signals.error.connect(self._on_error)
        worker.signals.finished.connect(lambda: self.btn_run.setEnabled(True))
        pool = QThreadPool.globalInstance()
        if pool is not None:
            pool.start(worker)

    def _on_progress(self, label: str, frac: float) -> None:
        self.progress.setValue(int(frac * 100))
        self.progress.setFormat(f"{label} – %p%")

    def _on_done(self, idx: int, result: AnalysisResult) -> None:
        self.state.store_result(idx, result)
        self.progress.setValue(100)
        self.progress.setFormat("Fertig")

    def _on_error(self, msg: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        self.progress.setFormat("Fehler")
        QMessageBox.critical(self, "Fehler", msg[:2000])

    # ------------------------------------------------------------------
    def _on_analysis_updated(self, idx: int) -> None:
        if idx != self.state.current_index:
            return
        self._on_result_changed()

    def _on_result_changed(self) -> None:
        self._result = self.state.current_result()
        self._refresh(self._result)

    # ------------------------------------------------------------------
    def _refresh(self, r: AnalysisResult | None) -> None:
        if r is None:
            for k in (self.kpi_L, self.kpi_R, self.kpi_C,
                      self.kpi_f, self.kpi_M):
                k.set_value("–")
            self.schem.draw(None)
            self.win_canvas.draw(None)
            self.bfield.set_board(None)
            self.bfield.set_classification(None)
            self.bfield.draw(None)
            self.tf_canvas.draw(None)
            self.cb_window.clear()
            self.trace_coil.set_trace(None)
            self.trace_mutual.set_trace(None)
            return

        # KPIs
        self.kpi_L.set_value(f"{r.coil.l_total_uH:.3f}")
        self.kpi_R.set_value(f"{r.coil.r_series_ohm:.3f}")
        self.kpi_C.set_value(f"{r.coil.c_series_pF:.2f}")
        self.kpi_f.set_value(f"{r.coil.resonance_mhz:.2f}")
        self.kpi_M.set_value(
            f"{r.mutual.m_total_nH:.3f}" if r.mutual else "–"
        )

        # Schematic
        self.schem.draw(r.equivalent_circuit)

        # Windows
        self.cb_window.blockSignals(True)
        self.cb_window.clear()
        if r.windows:
            self.cb_window.addItems([w.window_id for w in r.windows])
        self.cb_window.blockSignals(False)
        self._on_window_changed(0)

        # B-Feld mit Leiterbahn-Overlay
        self.bfield.set_board(r.board)
        self.bfield.set_classification(r.spec)
        self.bfield.set_show_traces(self.cb_bf_traces.isChecked())
        self.bfield.set_show_windows(self.cb_bf_windows.isChecked())
        self.bfield.draw(r.conductor, r.windows)

        # Uebertragungsfunktion (Bode)
        self.tf_canvas.draw(r.equivalent_circuit)

        # Traces (read-only -- Formeln stammen aus domain.formulas)
        self.trace_coil.set_trace(r.coil.trace)
        self.trace_mutual.set_trace(r.mutual.trace if r.mutual else None)

    def _on_window_changed(self, idx: int) -> None:
        r = self._result
        if r is None or not r.windows:
            self.win_canvas.draw(None)
            return
        if idx < 0 or idx >= len(r.windows):
            idx = 0
        w = r.windows[idx]
        self.win_canvas.draw(w, h_via_mm=w.h_via_mm)

    # ------------------------------------------------------------------
    # Optionen fuer B-Feld-Overlay
    # ------------------------------------------------------------------
    def _on_bfield_options(self, _checked: bool = False) -> None:
        """Re-render B-field whenever trace/window checkbox toggled."""
        r = self._result
        if r is None:
            return
        self.bfield.set_show_traces(self.cb_bf_traces.isChecked())
        self.bfield.set_show_windows(self.cb_bf_windows.isChecked())
        self.bfield.draw(r.conductor, r.windows)

    # ------------------------------------------------------------------
    # Umschaltung Uebertragungsfunktion
    # ------------------------------------------------------------------
    def _on_tf_mode(self, _checked: bool = False) -> None:
        mode = "impedance" if self.rb_tf_z.isChecked() else "primary"
        self.tf_canvas.set_mode(mode)
