"""
QThreadPool-Worker fuer lange Berechnungen.

Verwendung::

    worker = Worker(fn, *args, **kwargs)
    worker.signals.result.connect(self._on_result)
    worker.signals.error.connect(self._on_error)
    worker.signals.progress.connect(self._on_progress)
    QThreadPool.globalInstance().start(worker)
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    """Signale zur Kommunikation mit dem GUI-Thread."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str, float)   # (label, fraction 0..1)
    finished = pyqtSignal()


class Worker(QRunnable):
    """Fuehrt ``fn(*args, **kwargs)`` im Pool aus.

    Falls ``fn`` einen Keyword-Parameter ``progress_cb`` akzeptiert,
    wird dieser auf ``signals.progress.emit`` geroutet.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Progress-Callback automatisch injizieren (duck typing)
        try:
            import inspect
            if "progress_cb" in inspect.signature(fn).parameters:
                self.kwargs.setdefault(
                    "progress_cb",
                    lambda label, frac: self.signals.progress.emit(label, float(frac)),
                )
        except (TypeError, ValueError):
            pass

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            tb = traceback.format_exc()
            self.signals.error.emit(f"{exc}\n\n{tb}")
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
