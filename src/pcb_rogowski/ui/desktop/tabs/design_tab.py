"""
Tab 1 -- Design-Verwaltung & Gerber-Preview.

Links (schmal): Tabelle aller Designs + Aktionen.
Rechts (breit): grosse PCB-Preview des aktuellen Designs.

Die detaillierte Pfad-Konfiguration entfaellt -- Designs werden ueber
"+ Design" (Gerber-Ordner) geladen, restliche Pfade (Klassifikation,
Fenster, Stackup, Messung) werden via Buttons ueber der Preview
zugeordnet bzw. stammen aus der Projekt-YAML.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pcb_rogowski.app.use_cases.analyze_design import DesignInputs
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.ui.desktop.shared.board_viewer import BoardViewer
from pcb_rogowski.ui.desktop.shared.project_state import ProjectState


def _status_icon(design: DesignInputs) -> str:
    parts = []
    parts.append("●" if Path(design.gerber_dir).exists() else "○")
    parts.append("C" if design.classification_yaml and design.classification_yaml.exists() else "·")
    parts.append("W" if design.windows_yaml and design.windows_yaml.exists() else "·")
    parts.append("M" if design.bode100_csv and design.bode100_csv.exists() else "·")
    return " ".join(parts)


class DesignTab(QWidget):
    """Design-Liste + grosse Gerber-Preview."""

    def __init__(self, state: ProjectState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._current_row = -1
        self._build_ui()
        self.state.designs_changed.connect(self._refresh_table)
        self.state.selection_changed.connect(self._on_state_selection)
        self._refresh_table()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # --- LEFT: Liste + Buttons -------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel("Designs")
        lbl.setObjectName("sectionTitle")
        ll.addWidget(lbl)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Name", "Status"])
        hdr = self.tbl.horizontalHeader()
        if hdr is not None:
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        vhdr = self.tbl.verticalHeader()
        if vhdr is not None:
            vhdr.setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.itemSelectionChanged.connect(self._on_row_changed)
        ll.addWidget(self.tbl, 1)

        hint = QLabel("Status: ● Gerber  C Klassifikation  W Fenster  M Messung")
        hint.setObjectName("hint")
        ll.addWidget(hint)

        btns = QHBoxLayout()
        self.btn_add = QPushButton("+ Design")
        self.btn_add.setProperty("accent", True)
        self.btn_add.clicked.connect(self._add_design)
        self.btn_dup = QPushButton("Duplizieren")
        self.btn_dup.clicked.connect(self._duplicate_design)
        self.btn_del = QPushButton("Entfernen")
        self.btn_del.clicked.connect(self._remove_design)
        btns.addWidget(self.btn_add)
        btns.addWidget(self.btn_dup)
        btns.addWidget(self.btn_del)
        ll.addLayout(btns)

        # --- RIGHT: Info-Leiste + grosse Preview -----------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        self.lbl_name = QLabel("–")
        self.lbl_name.setObjectName("sectionTitle")
        title_row.addWidget(self.lbl_name, 1)

        # Kompakte Attach-Buttons
        self.btn_class = QToolButton(); self.btn_class.setText("Klassifikation …")
        self.btn_class.clicked.connect(lambda: self._attach_file("classification_yaml",
                                       "Klassifikation (YAML)", "YAML (*.yaml *.yml)"))
        self.btn_win = QToolButton(); self.btn_win.setText("Fenster …")
        self.btn_win.clicked.connect(lambda: self._attach_file("windows_yaml",
                                       "Fenster (YAML)", "YAML (*.yaml *.yml)"))
        self.btn_stack = QToolButton(); self.btn_stack.setText("Stackup …")
        self.btn_stack.clicked.connect(lambda: self._attach_file("stackup_yaml",
                                       "Stackup (YAML)", "YAML (*.yaml *.yml)"))
        self.btn_bode = QToolButton(); self.btn_bode.setText("Messung …")
        self.btn_bode.clicked.connect(lambda: self._attach_file("bode100_csv",
                                       "Bode100 CSV", "CSV (*.csv)"))
        for b in (self.btn_class, self.btn_win, self.btn_stack, self.btn_bode):
            title_row.addWidget(b)
        rl.addLayout(title_row)

        self.lbl_info = QLabel("Kein Design ausgewaehlt.")
        self.lbl_info.setObjectName("hint")
        rl.addWidget(self.lbl_info)

        self.viewer = BoardViewer()
        rl.addWidget(self.viewer, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 1200])

    # ------------------------------------------------------------------
    # Tabellen-Sync
    # ------------------------------------------------------------------
    def _refresh_table(self) -> None:
        self.tbl.blockSignals(True)
        self.tbl.setRowCount(len(self.state.designs))
        for i, d in enumerate(self.state.designs):
            name_item = QTableWidgetItem(d.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item = QTableWidgetItem(_status_icon(d))
            self.tbl.setItem(i, 0, name_item)
            self.tbl.setItem(i, 1, status_item)
        self.tbl.blockSignals(False)
        cur = self.state.current_index
        if 0 <= cur < self.tbl.rowCount():
            self.tbl.selectRow(cur)
            self._show_design(self.state.designs[cur])
        else:
            self._show_design(None)

    def _on_row_changed(self) -> None:
        sm = self.tbl.selectionModel()
        if sm is None:
            return
        rows = sm.selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        self._current_row = idx
        self.state.set_current(idx)

    def _on_state_selection(self, idx: int) -> None:
        if 0 <= idx < len(self.state.designs):
            if idx != self._current_row:
                self._current_row = idx
                self.tbl.selectRow(idx)
            self._show_design(self.state.designs[idx])
        else:
            self._show_design(None)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------
    def _show_design(self, d: DesignInputs | None) -> None:
        if d is None:
            self.lbl_name.setText("–")
            self.lbl_info.setText("Kein Design ausgewaehlt.")
            self.viewer.render(None)
            return
        self.lbl_name.setText(d.name)
        info = [f"Gerber: {d.gerber_dir}"]
        for attr, tag in [("classification_yaml", "Klassifikation"),
                          ("windows_yaml", "Fenster"),
                          ("stackup_yaml", "Stackup"),
                          ("bode100_csv", "Messung")]:
            p = getattr(d, attr)
            info.append(f"{tag}: {p.name if p else '–'}")
        self.lbl_info.setText("  ·  ".join(info))
        try:
            board = GerberBoardLoader().load_from_gerber(Path(d.gerber_dir))
            self.viewer.render(board, title=f"{d.name}")
        except Exception as exc:  # pragma: no cover
            self.viewer.clear()
            self.viewer.figure.text(0.5, 0.5, f"Gerber-Fehler: {exc}",
                                    ha="center", va="center", color="#f07178")
            self.viewer.redraw()

    # ------------------------------------------------------------------
    # Attach-Buttons
    # ------------------------------------------------------------------
    def _attach_file(self, attr: str, caption: str, filter_: str) -> None:
        d = self.state.current_design
        if d is None:
            return
        current = getattr(d, attr)
        p, _ = QFileDialog.getOpenFileName(
            self, caption,
            str(current) if current else str(d.gerber_dir), filter_,
        )
        if not p:
            return
        kwargs = {attr: Path(p)}
        new = _replace_dataclass(d, **kwargs)
        self.state.update_design(self._current_row, new)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _add_design(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Gerber-Verzeichnis waehlen", "")
        if not path:
            return
        p = Path(path)
        classification = p / "classification_draft.yaml"
        new = DesignInputs(
            name=p.name,
            gerber_dir=p,
            classification_yaml=classification if classification.exists() else None,
        )
        idx = self.state.add_design(new)
        self.state.set_current(idx)

    def _duplicate_design(self) -> None:
        cur = self.state.current_design
        if cur is None:
            return
        new = _replace_dataclass(cur, name=f"{cur.name} (Kopie)")
        idx = self.state.add_design(new)
        self.state.set_current(idx)

    def _remove_design(self) -> None:
        idx = self.state.current_index
        if idx < 0:
            return
        ret = QMessageBox.question(
            self, "Design entfernen",
            f"Design '{self.state.designs[idx].name}' entfernen?",
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.state.remove_design(idx)


# ---------------------------------------------------------------------------
def _replace_dataclass(d: DesignInputs, **kwargs) -> DesignInputs:  # type: ignore[no-untyped-def]
    import copy
    if hasattr(copy, "replace"):
        return copy.replace(d, **kwargs)  # type: ignore[attr-defined]
    base = {k: v for k, v in d.__dict__.items()}
    base.update(kwargs)
    return DesignInputs(**base)
