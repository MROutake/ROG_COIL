"""
Tab 2 -- Interaktive Klassifikation + Via-Fenster-Editor.

Portiert die bewaehrten Bedienmuster aus ``scripts/classify_board.py``
und ``scripts/define_windows.py``:

* Navigieren (Zoom/Pan) vs Auswaehlen (Klick-Selektion) -- explizite
  Umschaltung, damit die Matplotlib-Toolbar nicht mit dem Picking
  kollidiert.
* Sub-Modi:
    - **Leiter**: Lot-Picking, Shift+Klick Multi-Select, Hover-Highlight,
      W/R/C Hotkeys, Sigma +/-, Undo (Ctrl+Z), Ansicht Rolle/Sigma,
      Layer-Sichtbarkeit.
    - **Via-Fenster**: Vias werden nummeriert angezeigt; zwei Klicks
      definieren ein rechteckiges Fenster; Sigma-Toggle fuer das
      *naechste* Fenster, Undo letztes Fenster.
* Persistenz: In-Memory-Puffer im ``ProjectState`` + YAML-Export.
"""

from __future__ import annotations

import copy as _copy
import math
from pathlib import Path

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pcb_rogowski.app.use_cases.analyze_design import load_windows_yaml
from pcb_rogowski.domain.trace.classifier import (
    ClassificationEntry,
    ClassificationSpec,
    ClassifierConfig,
    FishboneClassifier,
    TopologyGapFiller,
)
from pcb_rogowski.domain.trace.models import ViaWindow
from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader
from pcb_rogowski.ui.desktop.shared.classify_canvas import ClassifyCanvas
from pcb_rogowski.ui.desktop.shared.project_state import ProjectState


# ---------------------------------------------------------------------------
# Stackup-Default fuer h_via (Fallback)
# ---------------------------------------------------------------------------

def _load_default_h_via() -> float:
    root = Path(__file__).resolve().parents[4]
    for candidate in ("stackup_design03.yaml", "defaults.yaml"):
        p = root / "configs" / candidate
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            v = (data.get("stackup", {}) or {}).get("total_thickness_mm")
            if v is not None:
                return float(v)
        except Exception:
            pass
    return 1.12268


# ---------------------------------------------------------------------------
# Tab
# ---------------------------------------------------------------------------

class ClassificationTab(QWidget):
    """Interaktive Klassifikation + Via-Fenster-Editor."""

    def __init__(self, state: ProjectState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self._board = None
        self._spec: ClassificationSpec | None = None
        self._windows: list[ViaWindow] = []
        self._h_via_mm: float = 0.0

        self._selected_ids: set[str] = set()
        self._selected_via_ids: list[str] = []
        self._active_role: str = "winding"
        self._next_sigma: int = +1

        self._undo_stack: list[tuple[
            dict[str, ClassificationEntry], list[ViaWindow]
        ]] = []

        self._build_ui()
        self._install_shortcuts()
        self.state.selection_changed.connect(lambda _: self._reload())
        self.state.designs_changed.connect(self._reload)

    # ==================================================================
    # UI
    # ==================================================================
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # --- LEFT: Canvas ---
        self.canvas = ClassifyCanvas()
        self.canvas.segment_clicked.connect(self._on_segment_clicked)
        self.canvas.via_clicked.connect(self._on_via_clicked)
        self.canvas.hover_changed.connect(self._on_hover_changed)

        # --- RIGHT: Control panel ---
        right = self._build_right_panel()

        splitter.addWidget(self.canvas)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1000, 360])

    def _build_right_panel(self) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setMinimumWidth(330)
        area.setMaximumWidth(440)
        area.setStyleSheet("QScrollArea { border: none; }")

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        title = QLabel("Klassifikation")
        title.setObjectName("sectionTitle")
        lay.addWidget(title)

        self.lbl_info = QLabel("Kein Design ausgewaehlt.")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setObjectName("hint")
        lay.addWidget(self.lbl_info)

        # --- Sub-Modus (Leiter / Vias) ---
        grp_mode = QGroupBox("Arbeits-Modus")
        ml = QHBoxLayout(grp_mode)
        self.btn_mode_leiter = QPushButton("Leiter klassifizieren")
        self.btn_mode_leiter.setCheckable(True)
        self.btn_mode_leiter.setChecked(True)
        self.btn_mode_leiter.clicked.connect(lambda: self._set_mode("leiter"))
        self.btn_mode_vias = QPushButton("Via-Fenster setzen")
        self.btn_mode_vias.setCheckable(True)
        self.btn_mode_vias.clicked.connect(lambda: self._set_mode("vias"))
        ml.addWidget(self.btn_mode_leiter)
        ml.addWidget(self.btn_mode_vias)
        lay.addWidget(grp_mode)

        # --- Interaktion (Navigate / Select) ---
        grp_int = QGroupBox("Interaktion")
        il = QVBoxLayout(grp_int)
        self.rb_navigate = QRadioButton("Navigieren  (Zoom / Pan)")
        self.rb_select = QRadioButton("Auswaehlen  (Klick / Shift+Klick)")
        self.rb_navigate.setChecked(True)
        self.rb_navigate.toggled.connect(
            lambda c: c and self.canvas.set_interact_mode("navigate"))
        self.rb_select.toggled.connect(
            lambda c: c and self.canvas.set_interact_mode("select"))
        il.addWidget(self.rb_navigate)
        il.addWidget(self.rb_select)
        lay.addWidget(grp_int)

        # --- Ansicht (Rolle / Sigma) ---
        grp_view = QGroupBox("Ansicht")
        vl = QVBoxLayout(grp_view)
        self.rb_view_role = QRadioButton("Rolle")
        self.rb_view_sigma = QRadioButton("Sigma (Windungen)")
        self.rb_view_role.setChecked(True)
        self.rb_view_role.toggled.connect(
            lambda c: c and self.canvas.set_view("role"))
        self.rb_view_sigma.toggled.connect(
            lambda c: c and self.canvas.set_view("sigma"))
        vl.addWidget(self.rb_view_role)
        vl.addWidget(self.rb_view_sigma)
        lay.addWidget(grp_view)

        # --- Layer-Sichtbarkeit ---
        self._layer_group = QGroupBox("Layer-Sichtbarkeit")
        self._layer_vl = QVBoxLayout(self._layer_group)
        self._layer_checks: dict[str, QCheckBox] = {}
        lay.addWidget(self._layer_group)

        # --- Leiter-Panel ---
        self.grp_leiter = QGroupBox("Rolle zuweisen  [W / R / C]")
        rl = QVBoxLayout(self.grp_leiter)
        btn_w = QPushButton("[W]  Windung")
        btn_w.setProperty("role", "W")
        btn_w.clicked.connect(lambda: self._apply_role("winding"))
        btn_r = QPushButton("[R]  Rueckleiter")
        btn_r.setProperty("role", "R")
        btn_r.clicked.connect(lambda: self._apply_role("return"))
        btn_c = QPushButton("[C]  Verbindung")
        btn_c.setProperty("role", "C")
        btn_c.clicked.connect(lambda: self._apply_role("connection"))
        rl.addWidget(btn_w)
        rl.addWidget(btn_r)
        rl.addWidget(btn_c)

        sig_row = QHBoxLayout()
        btn_sp = QPushButton("sigma = +1")
        btn_sp.clicked.connect(lambda: self._apply_sigma(+1))
        btn_sn = QPushButton("sigma = -1")
        btn_sn.clicked.connect(lambda: self._apply_sigma(-1))
        sig_row.addWidget(btn_sp)
        sig_row.addWidget(btn_sn)
        rl.addLayout(sig_row)

        sel_row = QHBoxLayout()
        btn_clr = QPushButton("Auswahl leeren (Esc)")
        btn_clr.clicked.connect(self._clear_selection)
        btn_undo = QPushButton("Undo (Ctrl+Z)")
        btn_undo.clicked.connect(self._undo)
        sel_row.addWidget(btn_clr)
        sel_row.addWidget(btn_undo)
        rl.addLayout(sel_row)

        self.lbl_selection = QLabel("Keine Auswahl.")
        self.lbl_selection.setObjectName("value")
        self.lbl_selection.setWordWrap(True)
        rl.addWidget(self.lbl_selection)

        auto_row = QHBoxLayout()
        btn_auto = QPushButton("Auto-Klassifikation")
        btn_auto.clicked.connect(self._auto_classify)
        btn_fill = QPushButton("Gap-Fill (Rest)")
        btn_fill.clicked.connect(self._gap_fill)
        auto_row.addWidget(btn_auto)
        auto_row.addWidget(btn_fill)
        rl.addLayout(auto_row)
        lay.addWidget(self.grp_leiter)

        # --- Via-Panel ---
        self.grp_vias = QGroupBox("Via-Fenster")
        wl = QVBoxLayout(self.grp_vias)

        self.lbl_via_h = QLabel("h_via = -")
        self.lbl_via_h.setObjectName("value")
        wl.addWidget(self.lbl_via_h)

        sig_box = QHBoxLayout()
        self.lbl_next_sigma = QLabel("sigma fuer naechstes Fenster: +1")
        self.lbl_next_sigma.setObjectName("value")
        self.btn_toggle_sigma = QPushButton("sigma umschalten")
        self.btn_toggle_sigma.clicked.connect(self._toggle_next_sigma)
        sig_box.addWidget(self.lbl_next_sigma, 1)
        sig_box.addWidget(self.btn_toggle_sigma)
        wl.addLayout(sig_box)

        hint = QLabel(
            "Zwei Vias anklicken -> neues Fenster wird automatisch erzeugt "
            "(sigma entsprechend aktueller Einstellung).\n"
            "'u' Undo letztes Fenster, '+/-' sigma umschalten.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        wl.addWidget(hint)

        self.tbl_windows = QTableWidget(0, 4)
        self.tbl_windows.setHorizontalHeaderLabels(
            ["ID", "sigma", "L [mm]", "Flaeche [mm^2]"])
        vh = self.tbl_windows.verticalHeader()
        if vh is not None:
            vh.setVisible(False)
        hh = self.tbl_windows.horizontalHeader()
        if hh is not None:
            hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_windows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_windows.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_windows.setAlternatingRowColors(True)
        wl.addWidget(self.tbl_windows)

        win_row = QHBoxLayout()
        btn_del = QPushButton("Ausgewaehltes loeschen")
        btn_del.clicked.connect(self._delete_window)
        btn_undo_w = QPushButton("Letztes Undo")
        btn_undo_w.clicked.connect(self._undo_last_window)
        win_row.addWidget(btn_del)
        win_row.addWidget(btn_undo_w)
        wl.addLayout(win_row)

        lay.addWidget(self.grp_vias)

        # --- Anzeige-Optionen ---
        grp_vis = QGroupBox("Anzeige")
        gvl = QVBoxLayout(grp_vis)
        self.cb_show_windows = QCheckBox("Via-Fenster einblenden")
        self.cb_show_windows.setChecked(True)
        self.cb_show_windows.toggled.connect(
            lambda c: self.canvas.set_show_windows(bool(c)))
        self.cb_show_via_labels = QCheckBox("Via-Nummern einblenden")
        self.cb_show_via_labels.setChecked(True)
        self.cb_show_via_labels.toggled.connect(
            lambda c: self.canvas.set_show_via_labels(bool(c)))
        gvl.addWidget(self.cb_show_windows)
        gvl.addWidget(self.cb_show_via_labels)
        lay.addWidget(grp_vis)

        # --- Statistik ---
        self.lbl_stats = QLabel("-")
        self.lbl_stats.setObjectName("value")
        lay.addWidget(self.lbl_stats)

        # --- Reset ---
        self.btn_reset = QToolButton()
        self.btn_reset.setText("Zuruecksetzen")
        self.btn_reset.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        rmenu = QMenu(self.btn_reset)
        rmenu.addAction("Nur Rollen", self._clear_roles)
        rmenu.addAction("Nur Fenster", self._clear_windows)
        rmenu.addAction("Alles", self._clear_all)
        self.btn_reset.setMenu(rmenu)

        # --- Bestaetigen / Speichern ---
        act_row = QHBoxLayout()
        btn_confirm = QPushButton("Bestaetigen")
        btn_confirm.setToolTip(
            "Aktuellen Stand in den Puffer uebernehmen und Tab 3 "
            "benachrichtigen (ohne auf Platte zu speichern).")
        btn_confirm.clicked.connect(self._confirm)
        btn_save = QPushButton("Speichern (Ctrl+S)")
        btn_save.setProperty("accent", True)
        btn_save.clicked.connect(self._save)
        act_row.addWidget(self.btn_reset)
        act_row.addWidget(btn_confirm)
        act_row.addWidget(btn_save)
        lay.addLayout(act_row)

        lay.addStretch(1)
        area.setWidget(w)
        return area

    def _install_shortcuts(self) -> None:
        bindings: list[tuple[str, object]] = [
            ("W",      lambda: self._apply_role("winding")),
            ("R",      lambda: self._apply_role("return")),
            ("C",      lambda: self._apply_role("connection")),
            ("+",      lambda: self._apply_sigma(+1)),
            ("=",      lambda: self._apply_sigma(+1)),
            ("-",      lambda: self._apply_sigma(-1)),
            ("Esc",    self._clear_selection),
            ("Ctrl+Z", self._undo),
            ("Ctrl+S", self._save),
            ("U",      self._undo_last_window),
            ("V",      self._toggle_view),
        ]
        for key, cb in bindings:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(cb)  # type: ignore[arg-type]

    # ==================================================================
    # Reload
    # ==================================================================
    def _reload(self) -> None:
        d = self.state.current_design
        idx = self.state.current_index

        # Layer-Checkboxen raeumen
        while self._layer_vl.count():
            item = self._layer_vl.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
        self._layer_checks.clear()

        if d is None:
            self._board = None
            self._spec = None
            self._windows = []
            self._undo_stack.clear()
            self.lbl_info.setText("Kein Design ausgewaehlt.")
            self.lbl_stats.setText("-")
            self.lbl_via_h.setText("h_via = -")
            self.tbl_windows.setRowCount(0)
            self.canvas.set_board(None)
            return

        try:
            self._board = GerberBoardLoader().load_from_gerber(Path(d.gerber_dir))
        except Exception as exc:
            self.lbl_info.setText(f"Gerber-Fehler: {exc}")
            self.canvas.set_board(None)
            return

        # Spec: Buffer > YAML > leer
        buffered_spec = self.state.get_spec(idx)
        if isinstance(buffered_spec, ClassificationSpec):
            self._spec = buffered_spec
            src = "Puffer"
        elif d.classification_yaml and Path(d.classification_yaml).exists():
            self._spec = ClassificationSpec.from_yaml(Path(d.classification_yaml))
            src = f"YAML ({Path(d.classification_yaml).name})"
        else:
            self._spec = ClassificationSpec(
                board_name=self._board.name,
                source_gerber=str(d.gerber_dir),
                entries=[])
            src = "leer"
        self.state.set_spec(idx, self._spec)

        # Fenster: Buffer > YAML > leer
        buffered_win = self.state.get_windows(idx)
        if isinstance(buffered_win, tuple) and len(buffered_win) == 2:
            self._windows, self._h_via_mm = buffered_win  # type: ignore[misc]
        elif d.windows_yaml and Path(d.windows_yaml).exists():
            self._windows, self._h_via_mm = load_windows_yaml(Path(d.windows_yaml))
        else:
            self._windows = []
            self._h_via_mm = _load_default_h_via()
        self.state.set_windows(idx, (self._windows, self._h_via_mm))

        self._undo_stack.clear()

        # Canvas befuellen
        self.canvas.set_board(self._board)
        self._push_to_canvas()
        self.canvas.reset_view()

        # Layer-Checkboxen neu anlegen
        for la in self._board.copper_layers:
            cb = QCheckBox(la.name)
            cb.setChecked(True)
            cb.toggled.connect(
                lambda v, n=la.name: self.canvas.set_layer_visible(n, bool(v)))
            self._layer_vl.addWidget(cb)
            self._layer_checks[la.name] = cb

        self.lbl_info.setText(
            f"Design: {d.name}  |  {self._board.name}  "
            f"({len(self._board.copper_layers)} Cu-Lagen, "
            f"{self.canvas.via_count()} Vias)  |  Quelle: {src}"
        )
        self._refresh_stats()
        self._refresh_windows_table()
        self._refresh_selection_label()

    # ==================================================================
    # Push Roles/Sigmas/Windows/Selection -> Canvas
    # ==================================================================
    def _push_to_canvas(self) -> None:
        if self._spec is None:
            self.canvas.set_roles({}, {})
        else:
            roles = {e.feature_id: e.role for e in self._spec.entries}
            sigmas = {e.feature_id: int(e.sigma) for e in self._spec.entries}
            self.canvas.set_roles(roles, sigmas)
        self.canvas.set_windows(self._windows)
        self.canvas.set_selection(self._selected_ids, self._selected_via_ids)

    def _push_buffer(self) -> None:
        idx = self.state.current_index
        if idx < 0:
            return
        self.state.set_spec(idx, self._spec)
        self.state.set_windows(idx, (self._windows, self._h_via_mm))

    # ==================================================================
    # Mode / View
    # ==================================================================
    def _set_mode(self, mode: str) -> None:
        self.btn_mode_leiter.setChecked(mode == "leiter")
        self.btn_mode_vias.setChecked(mode == "vias")
        self.grp_leiter.setEnabled(mode == "leiter")
        self.grp_vias.setEnabled(mode == "vias")
        self._selected_ids.clear()
        self._selected_via_ids.clear()
        self.canvas.set_mode(mode)
        self.canvas.set_selection(self._selected_ids, self._selected_via_ids)
        if mode == "vias":
            self.rb_select.setChecked(True)
        self._refresh_selection_label()

    def _toggle_view(self) -> None:
        if self.rb_view_role.isChecked():
            self.rb_view_sigma.setChecked(True)
        else:
            self.rb_view_role.setChecked(True)

    # ==================================================================
    # Click-Handler (Canvas-Signale)
    # ==================================================================
    def _on_segment_clicked(self, fid: str, shift: bool) -> None:
        if not shift:
            if fid in self._selected_ids and len(self._selected_ids) == 1:
                self._selected_ids.clear()
            else:
                self._selected_ids = {fid}
        else:
            if fid in self._selected_ids:
                self._selected_ids.discard(fid)
            else:
                self._selected_ids.add(fid)
        self.canvas.set_selection(self._selected_ids, self._selected_via_ids)
        self._refresh_selection_label()

    def _on_via_clicked(self, via_id: str, x: float, y: float,
                        shift: bool) -> None:
        if via_id in self._selected_via_ids:
            self._selected_via_ids.remove(via_id)
        else:
            self._selected_via_ids.append(via_id)

        if len(self._selected_via_ids) >= 2:
            a_id, b_id = self._selected_via_ids[:2]
            pa = self.canvas.via_position(a_id)
            pb = self.canvas.via_position(b_id)
            if pa is not None and pb is not None:
                self._create_window(a_id, pa, b_id, pb)
                self._selected_via_ids.clear()

        self.canvas.set_selection(self._selected_ids, self._selected_via_ids)
        self._refresh_selection_label()

    def _on_hover_changed(self, _fid: str) -> None:
        pass

    # ==================================================================
    # Leiter: Rolle / Sigma
    # ==================================================================
    def _snapshot(self) -> None:
        if self._spec is None:
            return
        snap_entries = {e.feature_id: _copy.copy(e) for e in self._spec.entries}
        snap_windows = list(self._windows)
        self._undo_stack.append((snap_entries, snap_windows))
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)

    def _apply_role(self, role: str) -> None:
        if self._board is None or self._spec is None or not self._selected_ids:
            return
        self._snapshot()
        for fid in list(self._selected_ids):
            self._assign_role(fid, role)
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()

    def _apply_sigma(self, sigma: int) -> None:
        if self.btn_mode_vias.isChecked():
            self._next_sigma = +1 if sigma >= 0 else -1
            self.lbl_next_sigma.setText(
                f"sigma fuer naechstes Fenster: "
                f"{'+1' if self._next_sigma > 0 else '-1'}"
            )
            return
        if self._spec is None or not self._selected_ids:
            return
        self._snapshot()
        by_id = {e.feature_id: e for e in self._spec.entries}
        for fid in self._selected_ids:
            if fid in by_id:
                by_id[fid].sigma = int(sigma)
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()

    def _assign_role(self, fid: str, role: str) -> None:
        if self._board is None or self._spec is None:
            return
        layer_name: str | None = None
        for layer in self._board.layers:
            for ln in layer.lines:
                if ln.feature_id == fid:
                    layer_name = layer.name
                    break
            if layer_name:
                break
        if layer_name is None:
            return
        by_id = {e.feature_id: e for e in self._spec.entries}
        if fid in by_id:
            e = by_id[fid]
            e.role = role
            e.note = "manuell"
        else:
            self._spec.entries.append(ClassificationEntry(
                feature_id=fid,
                layer_name=layer_name,
                role=role,
                sigma=0,
                note="manuell"))

    def _clear_selection(self) -> None:
        self._selected_ids.clear()
        self._selected_via_ids.clear()
        self.canvas.set_selection(self._selected_ids, self._selected_via_ids)
        self._refresh_selection_label()

    def _undo(self) -> None:
        if not self._undo_stack or self._spec is None:
            return
        entries, wins = self._undo_stack.pop()
        self._spec.entries = list(entries.values())
        self._windows = list(wins)
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()
        self._refresh_windows_table()

    # ==================================================================
    # Via-Fenster
    # ==================================================================
    def _toggle_next_sigma(self) -> None:
        self._next_sigma *= -1
        self.lbl_next_sigma.setText(
            f"sigma fuer naechstes Fenster: "
            f"{'+1' if self._next_sigma > 0 else '-1'}"
        )

    def _create_window(self, _a_id: str, pa: tuple[float, float],
                       _b_id: str, pb: tuple[float, float]) -> None:
        self._snapshot()
        xs = sorted([pa[0], pb[0]])
        ys = sorted([pa[1], pb[1]])
        win_id = f"W{len(self._windows) + 1:02d}"
        dist = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        w = ViaWindow(
            window_id=win_id,
            x_min_mm=xs[0], y_min_mm=ys[0],
            x_max_mm=xs[1], y_max_mm=ys[1],
            sigma=self._next_sigma,
            via_a_xy=pa, via_b_xy=pb,
            dist_mm=dist,
            h_via_mm=self._h_via_mm or None,
        )
        self._windows.append(w)
        self._push_buffer()
        self.canvas.set_windows(self._windows)
        self._refresh_windows_table()

    def _delete_window(self) -> None:
        sm = self.tbl_windows.selectionModel()
        rows = sm.selectedRows() if sm is not None else []
        if not rows:
            return
        self._snapshot()
        idx = rows[0].row()
        if 0 <= idx < len(self._windows):
            del self._windows[idx]
            self._push_buffer()
            self.canvas.set_windows(self._windows)
            self._refresh_windows_table()

    def _undo_last_window(self) -> None:
        if not self._windows:
            return
        self._snapshot()
        removed = self._windows.pop()
        self._push_buffer()
        self.canvas.set_windows(self._windows)
        self._refresh_windows_table()
        self.lbl_info.setText(f"Fenster {removed.window_id} entfernt.")

    # ==================================================================
    # Auto / GapFill / Clear
    # ==================================================================
    def _auto_classify(self) -> None:
        if self._board is None:
            return
        self._snapshot()
        self._spec = FishboneClassifier(ClassifierConfig()).classify(self._board)
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()

    def _gap_fill(self) -> None:
        if self._board is None or self._spec is None:
            return
        self._snapshot()
        self._spec = TopologyGapFiller().fill(self._board, self._spec)
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()

    def _clear_roles(self) -> None:
        if self._spec is None or self._board is None:
            return
        self._snapshot()
        d = self.state.current_design
        board_name = self._board.name
        src = str(d.gerber_dir) if d is not None else ""
        self._spec = ClassificationSpec(
            board_name=board_name, source_gerber=src, entries=[])
        self._push_buffer()
        self._push_to_canvas()
        self._refresh_stats()

    def _clear_windows(self) -> None:
        self._snapshot()
        self._windows = []
        self._push_buffer()
        self.canvas.set_windows(self._windows)
        self._refresh_windows_table()

    def _clear_all(self) -> None:
        ret = QMessageBox.question(
            self, "Alles zuruecksetzen",
            "Rollen UND Fenster verwerfen?")
        if ret == QMessageBox.StandardButton.Yes:
            self._clear_roles()
            self._clear_windows()

    # ==================================================================
    # Anzeige-Refresh
    # ==================================================================
    def _refresh_selection_label(self) -> None:
        parts = []
        if self._selected_ids:
            parts.append(f"{len(self._selected_ids)} Leiter")
        if self._selected_via_ids:
            parts.append(f"{len(self._selected_via_ids)} Via(s)")
        self.lbl_selection.setText(
            " | ".join(parts) if parts else "Keine Auswahl.")

    def _refresh_stats(self) -> None:
        if self._spec is None or self._board is None:
            self.lbl_stats.setText("-")
            return
        counts = self._spec.role_counts()
        total = sum(1 for layer in self._board.layers for _ in layer.lines)
        classified = len(self._spec.entries)
        self.lbl_stats.setText(
            f"Klassifiziert: {classified}/{total}  "
            f"W={counts.get('winding', 0)}  "
            f"R={counts.get('return', 0)}  "
            f"C={counts.get('connection', 0)}"
        )

    def _refresh_windows_table(self) -> None:
        self.lbl_via_h.setText(
            f"h_via = {self._h_via_mm:.4f} mm" if self._h_via_mm > 0
            else "h_via = -"
        )
        self.tbl_windows.setRowCount(len(self._windows))
        for i, w in enumerate(self._windows):
            self.tbl_windows.setItem(i, 0, QTableWidgetItem(w.window_id))
            s_item = QTableWidgetItem(f"{w.sigma:+d}")
            s_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_windows.setItem(i, 1, s_item)
            dist = w.dist_mm or 0.0
            self.tbl_windows.setItem(
                i, 2, QTableWidgetItem(f"{dist:.3f}"))
            a_item = QTableWidgetItem(f"{w.area_mm2:.3f}")
            a_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_windows.setItem(i, 3, a_item)

    # ==================================================================
    # Confirm / Save
    # ==================================================================
    def _confirm(self) -> None:
        if self._spec is None:
            QMessageBox.information(
                self, "Nichts zu bestaetigen",
                "Bitte zuerst ein Design auswaehlen und Rollen zuweisen.")
            return
        self._push_buffer()
        self.state.designs_changed.emit()
        QMessageBox.information(
            self, "Bestaetigt",
            f"Klassifikation + {len(self._windows)} Fenster in den "
            "Arbeitsspeicher uebernommen.\n"
            "Tab 3 -> 'Berechnen' nutzt nun diesen Stand.")

    def _save(self) -> None:
        d = self.state.current_design
        if d is None or self._spec is None:
            return

        target = d.classification_yaml
        if target is None:
            p, _ = QFileDialog.getSaveFileName(
                self, "Klassifikation speichern",
                str(Path(d.gerber_dir) / "classification_draft.yaml"),
                "YAML (*.yaml *.yml)")
            if not p:
                return
            target = Path(p)
            d2 = (_copy.replace(d, classification_yaml=target)
                  if hasattr(_copy, "replace")
                  else type(d)(**{**d.__dict__, "classification_yaml": target}))
            self.state.update_design(self.state.current_index, d2)
        try:
            self._spec.to_yaml(Path(target))
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", f"Klassifikation: {exc}")
            return

        win_target = d.windows_yaml
        if self._windows:
            if win_target is None:
                p2, _ = QFileDialog.getSaveFileName(
                    self, "Fenster speichern",
                    str(Path(d.gerber_dir).parent.parent
                        / f"configs/windows_{d.name}.yaml"),
                    "YAML (*.yaml *.yml)")
                if p2:
                    win_target = Path(p2)
                    d3 = (_copy.replace(d, windows_yaml=win_target)
                          if hasattr(_copy, "replace")
                          else type(d)(**{**d.__dict__, "windows_yaml": win_target}))
                    self.state.update_design(self.state.current_index, d3)
            if win_target is not None:
                try:
                    _save_windows_yaml(
                        Path(win_target), self._windows, self._h_via_mm)
                except Exception as exc:
                    QMessageBox.critical(self, "Fehler", f"Fenster: {exc}")
                    return

        QMessageBox.information(
            self, "Gespeichert",
            f"Klassifikation: {target}\n"
            + (f"Fenster: {win_target}" if win_target else ""))


# ---------------------------------------------------------------------------
# YAML-Helper
# ---------------------------------------------------------------------------

def _save_windows_yaml(path: Path, windows: list[ViaWindow],
                       h_via_mm: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "h_via_mm": float(h_via_mm),
        "windows": [
            {
                "window_id": w.window_id,
                "x_min_mm": float(w.x_min_mm),
                "y_min_mm": float(w.y_min_mm),
                "x_max_mm": float(w.x_max_mm),
                "y_max_mm": float(w.y_max_mm),
                "sigma": int(w.sigma),
                **({"via_a_xy": list(w.via_a_xy)} if w.via_a_xy else {}),
                **({"via_b_xy": list(w.via_b_xy)} if w.via_b_xy else {}),
                **({"dist_mm": float(w.dist_mm)} if w.dist_mm is not None else {}),
                **({"h_via_mm": float(w.h_via_mm)} if w.h_via_mm is not None else {}),
            }
            for w in windows
        ],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
