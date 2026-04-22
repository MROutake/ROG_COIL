"""
main.py -- Einstiegspunkt fuer das PCB Rogowski Tool.

* ``pcb-rogowski``        -> GUI (Default) bzw. CLI mit Argumenten
* ``pcb-rogowski-gui``    -> GUI direkt
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_application() -> None:
    """Initialisiert Logging und laedt Defaults."""
    from pcb_rogowski.infrastructure.logging.setup import setup_logging

    try:
        import yaml
        cfg_path = ROOT / "configs" / "defaults.yaml"
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as fh:
                defaults = yaml.safe_load(fh) or {}
            log_cfg = defaults.get("logging", {})
            log_file = ROOT / log_cfg.get("log_file", "output/logs/pcb_rogowski.log")
            setup_logging(
                level=log_cfg.get("level", "INFO"),
                log_file=log_file if log_cfg.get("log_to_file", False) else None,
            )
        else:
            setup_logging()
    except ImportError:
        setup_logging()
        logger.warning("PyYAML nicht installiert - Defaults nicht geladen.")


# ---------------------------------------------------------------------------
# GUI-Bootstrap
# ---------------------------------------------------------------------------

def _bootstrap_sample_designs(state) -> None:  # type: ignore[no-untyped-def]
    """Legt die drei Beispiel-Designs an, sofern die Daten vorhanden sind."""
    from pcb_rogowski.app.use_cases.analyze_design import DesignInputs

    gerber_root = ROOT / "data_samples" / "gerber"
    bode_root = ROOT / "data_samples" / "Bode100"
    stackup = ROOT / "configs" / "stackup_design03.yaml"

    bode_map = {
        "1": bode_root / "Desgin_01" / "Measurement_RogDual_limit_12MHz (1).csv",
        "2": bode_root / "Desgin_02" / "Design2 (1).csv",
        "3": bode_root / "Desgin_03" / "Design3 (1).csv",
    }
    windows_map = {
        "2": ROOT / "configs" / "windows_Design_2.yaml",
        "3": ROOT / "configs" / "windows_Design_3.yaml",
    }

    added = False
    for k in ("1", "2", "3"):
        d = gerber_root / f"Desgin_0{k}"
        if not d.exists():
            continue
        cls = d / "classification_draft.yaml"
        bode = bode_map.get(k)
        win = windows_map.get(k)
        state.add_design(DesignInputs(
            name=f"Design {k}",
            gerber_dir=d,
            classification_yaml=cls if cls.exists() else None,
            windows_yaml=win if (win and win.exists()) else None,
            stackup_yaml=stackup if stackup.exists() else None,
            bode100_csv=bode if (bode and bode.exists()) else None,
            defaults_yaml=ROOT / "configs" / "defaults.yaml",
        ))
        added = True

    if added:
        state.set_current(0)


def run_gui(*, load_samples: bool = True) -> int:
    """Startet die Qt-GUI."""
    from PyQt6.QtWidgets import QApplication

    from pcb_rogowski.ui.desktop.main_window import MainWindow
    from pcb_rogowski.ui.desktop.shared.theme import apply_theme

    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    win = MainWindow()
    if load_samples:
        _bootstrap_sample_designs(win.state)
    win.show()
    return app.exec()


# ---------------------------------------------------------------------------
# Entry Points
# ---------------------------------------------------------------------------

def main_gui() -> int:
    """Direkter GUI-Entrypoint (``pcb-rogowski-gui``)."""
    setup_application()
    return run_gui(load_samples=True)


def main() -> int:
    """CLI-Entrypoint (startet standardmaessig die GUI)."""
    setup_application()

    parser = argparse.ArgumentParser(
        prog="pcb-rogowski",
        description="PCB Rogowski Analysetool",
    )
    parser.add_argument(
        "--no-samples", action="store_true",
        help="Keine Beispiel-Designs vorladen.",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Keine GUI starten (nur Logging/Setup-Test).",
    )
    args = parser.parse_args()

    if args.headless:
        logger.info("PCB Rogowski Tool gestartet (headless).")
        return 0
    return run_gui(load_samples=not args.no_samples)


if __name__ == "__main__":
    sys.exit(main())
