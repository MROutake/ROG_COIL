"""
Infrastructure: Logging-Konfiguration.

Stellt ein projektweites Logging-Setup bereit, das sowohl
auf die Konsole als auch in eine Logdatei schreibt.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
) -> None:
    """
    Konfiguriert das projektweite Logging.

    Args:
        level: Log-Level als String (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional – Pfad zur Log-Datei.
        log_format: Format-String für Log-Einträge.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=handlers,
        force=True,
    )

    logging.getLogger("pcb_rogowski").setLevel(numeric_level)
    logging.info("Logging initialisiert (Level: %s)", level)
