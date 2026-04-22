"""
Baumdarstellung eines ``CalculationTrace`` mit Formel- und Eingabeanzeige.

Links: Liste aller ``TraceStep`` -- rechts: Detail-Panel mit Formel + Inputs.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pcb_rogowski.domain.common.trace import CalculationTrace, TraceStep
from pcb_rogowski.ui.desktop.shared.formula_box import FormulaBox


class CalculationTraceView(QWidget):
    """Zweigeteilter Viewer fuer eine ``CalculationTrace``.

    Links steht die Liste aller ``TraceStep``-Objekte, rechts ein
    Detail-Panel mit der Formel (read-only aus der zentralen
    :mod:`pcb_rogowski.domain.formulas`-Registry), den Eingangsgroessen
    und dem Ergebnis.

    Die Formeln sind bewusst nicht im GUI anpassbar -- alle Aenderungen
    erfolgen zentral in ``src/pcb_rogowski/domain/formulas.py`` + der
    zugehoerigen Python-Implementierung.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current: list[TraceStep] = []
        self._active_step: TraceStep | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- Links: Tree ---
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Rechenschritt", "Ergebnis"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_selected)
        self.tree.setColumnWidth(0, 280)

        # --- Rechts: Detail-Panel ---
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)

        self.lbl_name = QLabel("-")
        self.lbl_name.setObjectName("sectionTitle")
        rl.addWidget(self.lbl_name)

        rl.addWidget(QLabel("Formel:"))
        self.formula_box = FormulaBox(height=70)
        rl.addWidget(self.formula_box)

        rl.addWidget(QLabel("Eingaben:"))
        self.tbl_inputs = QTableWidget(0, 2)
        self.tbl_inputs.setHorizontalHeaderLabels(["Groesse", "Wert"])
        vh = self.tbl_inputs.verticalHeader()
        if vh is not None:
            vh.setVisible(False)
        hh = self.tbl_inputs.horizontalHeader()
        if hh is not None:
            hh.setStretchLastSection(True)
        rl.addWidget(self.tbl_inputs, 1)

        self.lbl_output = QLabel("-")
        self.lbl_output.setObjectName("value")
        rl.addWidget(self.lbl_output)

        self.lbl_note = QLabel()
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setObjectName("hint")
        rl.addWidget(self.lbl_note)

        splitter.addWidget(self.tree)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(splitter)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def set_trace(self, trace: CalculationTrace | None) -> None:
        self.tree.clear()
        self._current = list(trace.steps) if trace else []
        if trace is None:
            self._show_step(None)
            return

        for i, s in enumerate(trace.steps):
            item = QTreeWidgetItem([s.name, f"{s.output:.4g} {s.unit}"])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self.tree.addTopLevelItem(item)

        if trace.warnings:
            warn = QTreeWidgetItem([f"Warnungen ({len(trace.warnings)})", ""])
            warn.setForeground(0, Qt.GlobalColor.darkYellow)
            for w in trace.warnings:
                warn.addChild(QTreeWidgetItem([w, ""]))
            self.tree.addTopLevelItem(warn)
            warn.setExpanded(True)

        if self._current:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    # ------------------------------------------------------------------

    def _on_selected(self, current, _previous) -> None:  # type: ignore[no-untyped-def]
        if current is None:
            return
        idx = current.data(0, Qt.ItemDataRole.UserRole)
        if idx is None or idx >= len(self._current):
            self._show_step(None)
            return
        self._show_step(self._current[idx])

    def _show_step(self, step: TraceStep | None) -> None:
        self._active_step = step
        if step is None:
            self.lbl_name.setText("-")
            self.formula_box.clear()
            self.tbl_inputs.setRowCount(0)
            self.lbl_output.setText("-")
            self.lbl_note.setText("")
            return

        self.lbl_name.setText(step.name)

        # Formel aus der zentralen Registry (via TraceStep.formula) -- read-only.
        self.formula_box.set_formula(step.formula)

        self.tbl_inputs.setRowCount(len(step.inputs))
        for r, (k, v) in enumerate(step.inputs.items()):
            self.tbl_inputs.setItem(r, 0, QTableWidgetItem(str(k)))
            txt = f"{v:.6g}" if isinstance(v, float) else str(v)
            self.tbl_inputs.setItem(r, 1, QTableWidgetItem(txt))

        self.lbl_output.setText(f"→ {step.output:.6g} {step.unit}")
        self.lbl_note.setText(step.note or "")
