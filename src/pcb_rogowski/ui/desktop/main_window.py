"""
Haupt-Fenster der PCB-Rogowski-GUI.

Vier Tabs:
    1. Design-Verwaltung        (Gerber-Import)
    2. Klassifikation           (Windungen, Fenster)
    3. Analyse                  (L, R, C, M + Zwischenschritte)
    4. Auswertung               (Bode, Sprungantwort, Vergleich)
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from pcb_rogowski.ui.desktop.shared.project_state import ProjectState
from pcb_rogowski.ui.desktop.tabs.analysis_tab import AnalysisTab
from pcb_rogowski.ui.desktop.tabs.classification_tab import ClassificationTab
from pcb_rogowski.ui.desktop.tabs.design_tab import DesignTab
from pcb_rogowski.ui.desktop.tabs.output_tab import OutputTab


class MainWindow(QMainWindow):
    """Haupt-Fenster."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PCB Rogowski Analysis – v0.1.0")
        self.resize(1400, 900)

        self.state = ProjectState()

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.setCentralWidget(self.tabs)

        self.tab_design   = DesignTab(self.state)
        self.tab_classify = ClassificationTab(self.state)
        self.tab_analyze  = AnalysisTab(self.state)
        self.tab_output   = OutputTab(self.state)

        self.tabs.addTab(self.tab_design,   "1 – Design")
        self.tabs.addTab(self.tab_classify, "2 – Klassifikation")
        self.tabs.addTab(self.tab_analyze,  "3 – Analyse")
        self.tabs.addTab(self.tab_output,   "4 – Auswertung")

        self._build_menu()
        self._build_statusbar()

        self.state.designs_changed.connect(self._update_title)
        self._update_title()

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        mb = self.menuBar()
        if mb is None:  # defensive: QMainWindow garantiert keine Bar
            return

        # Projekt
        m_proj = mb.addMenu("&Projekt")
        assert m_proj is not None

        act_new = QAction("Neu", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._new_project)
        m_proj.addAction(act_new)

        act_open = QAction("Oeffnen …", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._open_project)
        m_proj.addAction(act_open)

        act_save = QAction("Speichern …", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._save_project)
        m_proj.addAction(act_save)

        m_proj.addSeparator()
        act_quit = QAction("Beenden", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        m_proj.addAction(act_quit)

        # Hilfe
        m_help = mb.addMenu("&Hilfe")
        assert m_help is not None
        act_about = QAction("Ueber", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

    def _build_statusbar(self) -> None:
        self.status_label = QLabel("Bereit")
        sb = self.statusBar()
        if sb is not None:
            sb.addWidget(self.status_label)

    # ------------------------------------------------------------------
    def _update_title(self) -> None:
        n = len(self.state.designs)
        proj = self.state.project_path.name if self.state.project_path else "unbenannt"
        self.setWindowTitle(f"PCB Rogowski Analysis – {proj} ({n} Designs)")

    # ------------------------------------------------------------------
    def _new_project(self) -> None:
        self.state = ProjectState()
        # Neu verbinden
        self.tab_design.state = self.state
        self.tab_classify.state = self.state
        self.tab_analyze.state = self.state
        self.tab_output.state = self.state
        QMessageBox.information(self, "Neues Projekt",
                                "Leeres Projekt erstellt. "
                                "Hinweis: GUI-Neustart empfohlen.")

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Projekt oeffnen", "",
            "Rogowski-Projekt (*.yaml *.rogproj.yaml)",
        )
        if not path:
            return
        try:
            self.state.load(Path(path))
            self.status_label.setText(f"Geladen: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", f"Konnte Projekt nicht laden:\n{exc}")

    def _save_project(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Projekt speichern", str(self.state.project_path or "projekt.rogproj.yaml"),
            "Rogowski-Projekt (*.rogproj.yaml *.yaml)",
        )
        if not path:
            return
        try:
            self.state.save(Path(path))
            self.status_label.setText(f"Gespeichert: {path}")
            self._update_title()
        except Exception as exc:
            QMessageBox.critical(self, "Fehler", f"Konnte Projekt nicht speichern:\n{exc}")

    def _about(self) -> None:
        QMessageBox.about(
            self, "Ueber PCB Rogowski",
            "<h3>PCB Rogowski Analysis Tool</h3>"
            "<p>Wissenschaftliche Auswertung von PCB-Rogowski-Spulen.</p>"
            "<p>Version 0.1.0</p>"
            "<p>Gerber → Klassifikation → L, R, C, M → Bode / Sprungantwort.</p>",
        )
