"""
Read-only Widget zum Rendern einer Formel in der GUI.

Konvertiert Unicode-Formelstrings (z. B. ``µ₀·l/(2π)`` aus der zentralen
Formel-Registry :mod:`pcb_rogowski.domain.formulas`) in matplotlib-MathText
und rendert sie in ein eingebettetes Canvas.

Design-Entscheidung
-------------------
Das Widget ist **bewusst nicht editierbar**.  Alle Formeln werden zentral
in :mod:`pcb_rogowski.domain.formulas` deklariert; zur Anpassung muss dort
``latex`` geändert und die zugehörige Python-Implementierung synchronisiert
werden.  Freies Überschreiben im GUI wurde entfernt, um inkonsistente
Zustände zwischen Anzeige und Rechenkern auszuschließen.
"""

from __future__ import annotations

import re

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from pcb_rogowski.ui.desktop.shared.theme import BG_PANEL, TEXT


# Unicode -> LaTeX Ersetzungs-Tabelle ------------------------------------
_UNICODE_TO_LATEX = {
    "·": r"\cdot ", "×": r"\times ", "÷": r"\div ",
    "±": r"\pm ", "∓": r"\mp ", "≈": r"\approx ",
    "≤": r"\leq ", "≥": r"\geq ", "≠": r"\neq ",
    "→": r"\to ", "←": r"\leftarrow ",
    "√": r"\sqrt ",
    "π": r"\pi ", "µ": r"\mu ", "μ": r"\mu ",
    "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ",
    "ε": r"\varepsilon ", "Ε": r"\varepsilon ",
    "ρ": r"\rho ", "σ": r"\sigma ", "τ": r"\tau ",
    "ω": r"\omega ", "Ω": r"\Omega ", "Σ": r"\Sigma ",
    "Δ": r"\Delta ", "∂": r"\partial ",
    "∞": r"\infty ",
    # Sub-/Superscripts
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}",
    "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}",
    "⁷": "^{7}", "⁸": "^{8}", "⁹": "^{9}",
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}",
    "₄": "_{4}", "₅": "_{5}", "₆": "_{6}",
    "₇": "_{7}", "₈": "_{8}", "₉": "_{9}",
}


def _to_mathtext(s: str) -> str:
    """Konvertiert einen Unicode-Formel-String in MathText."""
    if not s:
        return ""
    # Bereits LaTeX?
    if "$" in s:
        return s
    out = s
    for k, v in _UNICODE_TO_LATEX.items():
        out = out.replace(k, v)
    # Bezeichner-Wrapping: NUR Wortfolgen, die nicht bereits Teil eines
    # LaTeX-Befehls (\xxx) oder innerhalb \mathrm{...} sind. Negative
    # Lookbehind auf '\' bzw. '{' + einfache Schutzliste fuer LaTeX-Commands.
    _reserved = {
        "mathrm", "mu", "pi", "cdot", "times", "div", "pm", "mp",
        "approx", "leq", "geq", "neq", "to", "leftarrow", "sqrt",
        "alpha", "beta", "gamma", "rho", "sigma", "tau", "omega",
        "Omega", "Sigma", "Delta", "partial", "infty", "ln", "log",
        "sin", "cos", "tan", "exp", "frac", "varepsilon",
    }

    def _wrap_word(m: "re.Match[str]") -> str:
        w = m.group(0)
        if w in _reserved:
            return w
        return rf"\mathrm{{{w}}}"

    out = re.sub(r"(?<![\\{A-Za-z])[A-Za-z]{2,}", _wrap_word, out)

    # Benachbarte Sub/Sup-Gruppen zusammenfuehren:
    #   \rho _{2}_{0}  -> \rho _{20}
    #   x^{1}^{2}      -> x^{12}
    #   x^2^3          -> x^{23}
    #   y_1_2          -> y_{12}
    # (sonst matplotlib-mathtext: "Double subscript/superscript")
    #
    # 1) JEDES un-geklammerte einzelne Sub/Sup-Zeichen wickeln
    out = re.sub(r"_(?!\{)([A-Za-z0-9])", r"_{\1}", out)
    out = re.sub(r"\^(?!\{)([A-Za-z0-9])", r"^{\1}", out)
    # 2) Benachbarte Klammerpaare zusammenfuehren (iterativ fuer Ketten)
    for _ in range(6):
        new = re.sub(r"_\{([^{}]*)\}_\{([^{}]*)\}", r"_{\1\2}", out)
        new = re.sub(r"\^\{([^{}]*)\}\^\{([^{}]*)\}", r"^{\1\2}", new)
        if new == out:
            break
        out = new
    return f"${out}$"


class FormulaBox(QWidget):
    """Rendert eine Formel read-only in ein kleines matplotlib-Canvas.

    Die angezeigten Formeln stammen ausschließlich aus der zentralen
    Registry (:mod:`pcb_rogowski.domain.formulas`).  Eine Editier-
    Oberfläche wird bewusst nicht angeboten.
    """

    def __init__(self, parent: QWidget | None = None, *, height: int = 70) -> None:
        super().__init__(parent)
        self._current_raw: str = ""
        self._fig = Figure(figsize=(5, height / 100), dpi=100)
        self._fig.patch.set_facecolor(BG_PANEL)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setMinimumHeight(height)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        root.addWidget(self._canvas)

        self.clear()

    # ------------------------------------------------------------------
    def set_formula(self, formula: str) -> None:
        self._current_raw = formula or ""
        self._fig.clear()
        ax = self._fig.add_subplot(111)
        ax.set_axis_off()
        ax.set_facecolor(BG_PANEL)
        rendered = _to_mathtext(formula) if formula else ""
        try:
            if rendered:
                ax.text(0.02, 0.5, rendered, ha="left", va="center",
                        fontsize=13, color=TEXT)
        except Exception:
            ax.clear()
            ax.set_axis_off()
            ax.text(0.02, 0.5, formula, ha="left", va="center",
                    fontsize=11, color=TEXT, family="monospace")
        try:
            self._fig.tight_layout(pad=0.2)
        except Exception:
            pass
        self._canvas.draw_idle()

    def clear(self) -> None:
        self.set_formula("")
