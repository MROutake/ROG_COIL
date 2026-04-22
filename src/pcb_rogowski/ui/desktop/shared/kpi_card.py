"""
KPI-Karte: grosses Label fuer numerische Kernkennwerte.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class KpiCard(QFrame):
    """Kleine Karte mit Label, Wert und Einheit."""

    def __init__(self, label: str, unit: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setObjectName("kpiLabel")
        self._val = QLabel("–")
        self._val.setObjectName("kpiValue")
        self._val.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._unit = QLabel(unit)
        self._unit.setObjectName("kpiUnit")

        lay.addWidget(self._lbl)
        lay.addWidget(self._val)
        lay.addWidget(self._unit)

    def set_value(self, value: str, unit: str | None = None) -> None:
        self._val.setText(value)
        if unit is not None:
            self._unit.setText(unit)
