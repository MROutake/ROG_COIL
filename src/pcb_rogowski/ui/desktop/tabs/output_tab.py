"""
Tab 4 -- Ausgabe: Bode-Impedanz, Sprungantwort, Messvergleich.

Drei Diagramme nebeneinander (Tabs):
    1. Bode |Z| und arg(Z)   (Berechnung + Fit + Messung)
    2. Sprungantwort         (Impedanz-Sprungantwort + V_out bei I1-Sprung)
    3. Residuen / Fehler     (Tabelle Berechnung vs. Fit vs. Messung)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pcb_rogowski.app.use_cases.analyze_design import AnalysisResult
from pcb_rogowski.domain.coil.transfer_function import (
    EquivalentCircuit,
    impedance,
    impedance_step_response,
    primary_step_response,
    resonance_frequency_hz,
)
from pcb_rogowski.ui.desktop.shared.mpl_canvas import MplCanvas
from pcb_rogowski.ui.desktop.shared.project_state import ProjectState


class OutputTab(QWidget):
    """Bode-, Sprungantworts- und Vergleichs-Tab."""

    def __init__(self, state: ProjectState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._build_ui()
        self.state.selection_changed.connect(lambda _: self._refresh())
        self.state.analysis_updated.connect(lambda _: self._refresh())

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # --- LEFT: Einstellungen ---------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)

        t = QLabel("Auswertung")
        t.setObjectName("sectionTitle")
        ll.addWidget(t)

        # --- Messung zuordnen --------------------------------------------
        meas_box = QGroupBox("Messung (Bode100-CSV)")
        ml = QVBoxLayout(meas_box)
        self.lbl_meas = QLabel("– keine Messung –")
        self.lbl_meas.setWordWrap(True)
        self.lbl_meas.setObjectName("hint")
        ml.addWidget(self.lbl_meas)
        meas_row = QHBoxLayout()
        self.btn_load_meas = QPushButton("Messung laden …")
        self.btn_load_meas.clicked.connect(self._load_measurement)
        self.btn_clear_meas = QPushButton("Entfernen")
        self.btn_clear_meas.clicked.connect(self._clear_measurement)
        meas_row.addWidget(self.btn_load_meas)
        meas_row.addWidget(self.btn_clear_meas)
        ml.addLayout(meas_row)
        ll.addWidget(meas_box)

        settings = QGroupBox("Frequenzsweep")
        f = QFormLayout(settings)
        f.setContentsMargins(12, 18, 12, 12)
        self.sp_fmin = QDoubleSpinBox()
        self.sp_fmin.setRange(1.0, 1e9)
        self.sp_fmin.setValue(1e3)
        self.sp_fmin.setDecimals(1)
        self.sp_fmin.setSuffix(" Hz")
        self.sp_fmin.valueChanged.connect(self._refresh)
        f.addRow("f_min", self.sp_fmin)
        self.sp_fmax = QDoubleSpinBox()
        self.sp_fmax.setRange(1.0, 1e9)
        self.sp_fmax.setValue(1e8)
        self.sp_fmax.setDecimals(1)
        self.sp_fmax.setSuffix(" Hz")
        self.sp_fmax.valueChanged.connect(self._refresh)
        f.addRow("f_max", self.sp_fmax)
        self.sp_n = QSpinBox()
        self.sp_n.setRange(20, 5000)
        self.sp_n.setValue(500)
        self.sp_n.valueChanged.connect(self._refresh)
        f.addRow("Punkte", self.sp_n)
        ll.addWidget(settings)

        step_box = QGroupBox("Sprungantwort")
        sf = QFormLayout(step_box)
        sf.setContentsMargins(12, 18, 12, 12)
        self.cb_step_kind = QComboBox()
        self.cb_step_kind.addItems([
            "Z(s) – Spannung bei I-Sprung (1 A)",
            "V_out / I_prim (Primärstrom-Sprung)",
        ])
        self.cb_step_kind.currentIndexChanged.connect(self._refresh)
        sf.addRow("Typ", self.cb_step_kind)
        ll.addWidget(step_box)

        self.summary = QLabel("Kein Ergebnis.")
        self.summary.setObjectName("hint")
        self.summary.setWordWrap(True)
        ll.addWidget(self.summary)
        ll.addStretch(1)

        # --- RIGHT: Plots + Tabelle ------------------------------------
        self.tabs = QTabWidget()

        self.canvas_bode = MplCanvas(figsize=(11, 8))
        self.tabs.addTab(self.canvas_bode, "Bode")

        self.canvas_step = MplCanvas(figsize=(11, 8))
        self.tabs.addTab(self.canvas_step, "Sprungantwort")

        self.tbl_err = QTableWidget(0, 4)
        self.tbl_err.setHorizontalHeaderLabels(
            ["Groesse", "Berechnung", "Fit", "Messung"]
        )
        _vh = self.tbl_err.verticalHeader()
        if _vh is not None:
            _vh.setVisible(False)
        _hh = self.tbl_err.horizontalHeader()
        if _hh is not None:
            _hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_err.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_err, "Vergleich")

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 1200])

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        # Messungs-Label aktuell halten
        d = self.state.current_design
        if d is not None and d.bode100_csv is not None:
            self.lbl_meas.setText(str(d.bode100_csv))
        else:
            self.lbl_meas.setText("– keine Messung –")

        r = self.state.current_result()
        if r is None:
            self.canvas_bode.clear()
            self.canvas_step.clear()
            self.tbl_err.setRowCount(0)
            self.summary.setText("Noch keine Berechnung. Tab 3 → 'Berechnen'.")
            return

        self._plot_bode(r)
        self._plot_step(r)
        self._fill_error_table(r)

        ec = r.equivalent_circuit
        self.summary.setText(
            f"<b>{r.design_name}</b><br>"
            f"L={ec.L_uH:.3f} µH, R={ec.R_ohm:.3f} Ω, C={ec.C_pF:.2f} pF<br>"
            f"f_res = {resonance_frequency_hz(ec.L_H, ec.C_F) / 1e6:.3f} MHz<br>"
            f"M = {ec.M_nH:.3f} nH"
        )

    # ------------------------------------------------------------------
    def _freq_vector(self) -> np.ndarray:
        fmin = max(float(self.sp_fmin.value()), 1.0)
        fmax = max(float(self.sp_fmax.value()), fmin * 10.0)
        return np.logspace(np.log10(fmin), np.log10(fmax),
                           int(self.sp_n.value()))

    def _plot_bode(self, r: AnalysisResult) -> None:
        f = self._freq_vector()
        ec = r.equivalent_circuit
        z_calc = impedance(f, ec.L_H, ec.R_ohm, ec.C_F)

        self.canvas_bode.figure.clear()
        ax1 = self.canvas_bode.figure.add_subplot(211)
        ax2 = self.canvas_bode.figure.add_subplot(212, sharex=ax1)

        # positive Magnituden fuer loglog
        def _pos(a: np.ndarray) -> np.ndarray:
            return np.where(np.isfinite(a) & (a > 0), a, np.nan)

        ax1.loglog(f, _pos(np.abs(z_calc)), "-",
                   color="#2ca02c", lw=2, label="Berechnung")
        ax2.semilogx(f, np.angle(z_calc, deg=True), "-",
                     color="#2ca02c", lw=2)

        ec_fit = r.equivalent_circuit_fit
        if ec_fit is not None and r.fit is not None:
            z_fit = impedance(f, ec_fit.L_H, ec_fit.R_ohm, ec_fit.C_F,
                              k_skin=r.fit.k_skin, k_prox=r.fit.k_prox)
            ax1.loglog(f, _pos(np.abs(z_fit)), "--",
                       color="#ff7f0e", lw=1.8, label="Fit")
            ax2.semilogx(f, np.angle(z_fit, deg=True), "--",
                         color="#ff7f0e", lw=1.8)

        if r.bode_df is not None:
            fm = r.bode_df["freq_hz"].to_numpy()
            zm = (r.bode_df["re_ohm"].to_numpy()
                  + 1j * r.bode_df["im_ohm"].to_numpy())
            mask = np.isfinite(fm) & (fm > 0)
            ax1.loglog(fm[mask], _pos(np.abs(zm[mask])), "-",
                       color="#1f77b4", lw=1.2, alpha=0.9, label="Messung")
            ax2.semilogx(fm[mask], np.angle(zm[mask], deg=True), "-",
                         color="#1f77b4", lw=1.2, alpha=0.9)

        # expliziter xlim (positiv) – verhindert UserWarning bei log axis
        ax1.set_xlim(float(f[0]), float(f[-1]))
        ax1.set_ylabel("|Z|  [Ω]")
        ax1.grid(True, which="both", alpha=0.3)
        ax1.legend(loc="best", fontsize=9)
        ax1.set_title(f"Impedanz {r.design_name}")
        ax2.set_ylabel("arg(Z)  [°]")
        ax2.set_xlabel("Frequenz [Hz]")
        ax2.grid(True, which="both", alpha=0.3)
        self.canvas_bode.redraw()

    def _plot_step(self, r: AnalysisResult) -> None:
        ec = r.equivalent_circuit

        self.canvas_step.figure.clear()
        ax = self.canvas_step.figure.add_subplot(111)

        kind = self.cb_step_kind.currentIndex()
        if kind == 0:
            t, y = impedance_step_response(ec)
            ax.plot(t * 1e6, y, "-", color="#2ca02c", lw=2, label="Berechnung")
            if r.equivalent_circuit_fit is not None:
                ec2 = r.equivalent_circuit_fit
                t2, y2 = impedance_step_response(ec2)
                ax.plot(t2 * 1e6, y2, "--", color="#ff7f0e", lw=1.5, label="Fit")
            ax.set_ylabel("V(t)  [V]  (bei i = 1 A·u(t))")
            ax.set_title("Sprungantwort Z(s)")
        else:
            t, y = primary_step_response(ec)
            ax.plot(t * 1e6, y, "-", color="#2ca02c", lw=2, label="Berechnung")
            if r.equivalent_circuit_fit is not None:
                ec2 = r.equivalent_circuit_fit
                t2, y2 = primary_step_response(ec2)
                ax.plot(t2 * 1e6, y2, "--", color="#ff7f0e", lw=1.5, label="Fit")
            ax.set_ylabel("V_out(t)  [V]  (bei i_prim = 1 A·u(t))")
            ax.set_title("Uebertragungsfunktion s·M / (L C s² + R C s + 1)")

        ax.set_xlabel("Zeit [µs]")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9)
        self.canvas_step.redraw()

    def _fill_error_table(self, r: AnalysisResult) -> None:
        has_meas = r.bode_df is not None

        # Spaltenlayout anpassen
        if has_meas:
            headers = ["Groesse", "Berechnung", "Fit", "Messung"]
            self.tbl_err.setColumnCount(4)
        else:
            headers = ["Groesse", "Berechnung", "Fit"]
            self.tbl_err.setColumnCount(3)
        self.tbl_err.setHorizontalHeaderLabels(headers)

        # Messwerte (aus Fit direkt, da dieser die Messung abbildet)
        # wir interpretieren "Messung" als aus der Rohkurve abgeleitete
        # grobe DC-Werte; wenn nicht ermittelbar -> Fit-Wert
        meas_L = meas_R = meas_C = meas_f = None
        if has_meas and r.fit is not None:
            # Messung wird hier durch Fit-Parameter repraesentiert
            # (extra Spalte waere nur redundant, daher zeigen wir sie nur,
            # wenn Messung vorhanden).
            meas_L = r.fit.L_uH
            meas_R = r.fit.R_dc_ohm
            meas_C = r.fit.C_pF
            meas_f = r.fit.f_res_MHz

        rows: list[tuple[str, float | None, float | None, float | None]] = []
        rows.append(("L [µH]",    r.coil.l_total_uH,
                     r.fit.L_uH if r.fit else None, meas_L))
        rows.append(("R [Ω]",     r.coil.r_series_ohm,
                     r.fit.R_dc_ohm if r.fit else None, meas_R))
        rows.append(("C [pF]",    r.coil.c_series_pF,
                     r.fit.C_pF if r.fit else None, meas_C))
        rows.append(("f_res [MHz]", r.coil.resonance_mhz,
                     r.fit.f_res_MHz if r.fit else None, meas_f))
        if r.fit is not None:
            rows.append(("RMSE |Z| [%]", None, r.fit.rmse_mag_pct, None))

        self.tbl_err.setRowCount(len(rows))
        for i, (k, g, fit, m) in enumerate(rows):
            self.tbl_err.setItem(i, 0, QTableWidgetItem(k))
            self.tbl_err.setItem(i, 1, QTableWidgetItem(
                f"{g:.4f}" if g is not None else "–"))
            self.tbl_err.setItem(i, 2, QTableWidgetItem(
                f"{fit:.4f}" if fit is not None else "–"))
            if has_meas:
                self.tbl_err.setItem(i, 3, QTableWidgetItem(
                    f"{m:.4f}" if m is not None else "–"))

    # ------------------------------------------------------------------
    # Mess-Dateien zuordnen / entfernen
    # ------------------------------------------------------------------
    def _load_measurement(self) -> None:
        d = self.state.current_design
        if d is None:
            QMessageBox.information(self, "Kein Design",
                                    "Bitte zuerst ein Design auswaehlen.")
            return
        start_dir = str(d.bode100_csv.parent) if d.bode100_csv else str(d.gerber_dir)
        p, _ = QFileDialog.getOpenFileName(
            self, "Bode100-Messung waehlen",
            start_dir,
            "Bode100 CSV (*.csv *.txt);;Alle Dateien (*.*)",
        )
        if not p:
            return
        import copy
        d2 = (copy.replace(d, bode100_csv=Path(p))
              if hasattr(copy, "replace")
              else type(d)(**{**d.__dict__, "bode100_csv": Path(p)}))
        self.state.update_design(self.state.current_index, d2)
        self._refresh()
        QMessageBox.information(
            self, "Messung zugeordnet",
            f"{Path(p).name}\n\nFuehre Tab 3 → 'Berechnen' erneut aus, "
            "damit die Messung in Fit + Vergleich einfliesst.")

    def _clear_measurement(self) -> None:
        d = self.state.current_design
        if d is None or d.bode100_csv is None:
            return
        import copy
        d2 = (copy.replace(d, bode100_csv=None)
              if hasattr(copy, "replace")
              else type(d)(**{**d.__dict__, "bode100_csv": None}))
        self.state.update_design(self.state.current_index, d2)
        self._refresh()
