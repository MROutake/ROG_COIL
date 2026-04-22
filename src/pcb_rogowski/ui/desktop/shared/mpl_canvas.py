"""
Matplotlib-Canvas als Qt-Widget (QtAgg-Backend).

Minimal-Wrapper mit eingebauter Toolbar und ``clear()`` /
``draw()``-Convenience.
"""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("QtAgg", force=False)

from matplotlib.backends.backend_qtagg import (  # noqa: E402
    FigureCanvasQTAgg as FigureCanvas,
)
from matplotlib.backends.backend_qt import (  # noqa: E402
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure  # noqa: E402
from PyQt6.QtWidgets import QVBoxLayout, QWidget  # noqa: E402


class MplCanvas(QWidget):
    """Matplotlib-Canvas mit optionaler Toolbar (``show_toolbar``)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        show_toolbar: bool = True,
        tight: bool = True,
        figsize: tuple[float, float] = (6.0, 4.0),
        dpi: int = 100,
    ) -> None:
        super().__init__(parent)
        self.figure: Figure = Figure(figsize=figsize, dpi=dpi, tight_layout=tight)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self) if show_toolbar else None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        if self.toolbar is not None:
            lay.addWidget(self.toolbar)
        lay.addWidget(self.canvas)

    # Convenience ---------------------------------------------------------
    def clear(self) -> None:
        self.figure.clear()
        self.canvas.draw_idle()

    def redraw(self) -> None:
        self.canvas.draw_idle()

    def add_subplot(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        return self.figure.add_subplot(*args, **kwargs)
