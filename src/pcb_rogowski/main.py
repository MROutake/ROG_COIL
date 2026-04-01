"""
main.py – Einstiegspunkt für das PCB Rogowski Tool.

Initialisiert Logging, lädt Konfiguration und startet die Anwendung.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Projektwurzel
ROOT = Path(__file__).parent.parent.parent


def setup_application() -> None:
    """Initialisiert Logging und Konfiguration."""
    from pcb_rogowski.infrastructure.logging.setup import setup_logging

    try:
        import yaml
        config_path = ROOT / "configs" / "defaults.yaml"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                defaults = yaml.safe_load(fh)
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
        logger.warning("PyYAML nicht installiert – Defaults nicht geladen.")


def main() -> int:
    """
    Haupteinstiegspunkt.

    Returns:
        Exit-Code (0 = OK, != 0 = Fehler)
    """
    setup_application()
    logger.info("PCB Rogowski Tool gestartet")

    # TODO Sprint 5: Desktop-GUI starten
    # from pcb_rogowski.ui.desktop.main_window.window import MainWindow
    # app = QApplication(sys.argv)
    # window = MainWindow()
    # window.show()
    # return app.exec()

    print("PCB Rogowski Tool v0.1.0")
    print("GUI noch nicht implementiert (Sprint 5)")
    print("Starte mit: python scripts/bootstrap_project.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
