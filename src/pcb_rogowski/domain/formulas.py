"""
Zentrale Formel-Registry (Single Source of Truth)
=================================================

Diese Datei ist die *einzige* Stelle, an der alle physikalischen Formeln,
die im Rechenkern von ``pcb_rogowski`` verwendet werden, deklariert und
dokumentiert sind.

Ziel
----
* **Eine** Datei, um die verwendeten Formeln zu prüfen und anzupassen.
* Konsistente Anzeige in GUI, Reports und Exporten.
* Gekoppelt an die Literaturquellen aus ``docs/berechnungen.md``.

Aufbau
------
Jede Formel ist ein unveränderliches :class:`Formula`-Objekt mit:

``key``
    Stabiler Bezeichner (identisch zum Dict-Schlüssel).  Wird von den
    Berechnungsroutinen (``service.py``, ``calculator.py``) zur Auflösung
    des Anzeige-Textes benutzt -- **nie frei getippte Strings**.

``latex``
    Unicode-mathematische Repräsentation (wird in der GUI via
    :mod:`formula_box` durch eine Unicode→MathText-Abbildung gerendert).
    *Darf* mehrere Zeilen enthalten.

``description``
    Fachlich-physikalische Beschreibung (deutsch), inkl. Modell-Annahmen.

``variables``
    Variablen-Glossar ``{symbol: "Bedeutung [Einheit]"}``.

``unit``
    Einheit der linken Seite (``output`` im :class:`TraceStep`).

``reference``
    Literaturverweis oder Pfad in ``docs/berechnungen.md``.

``impl``
    Cross-Link auf die Python-Funktion, welche die Formel *tatsächlich
    ausrechnet*, im Format ``modul.pfad::funktion`` (z. B.
    ``domain.coil.service::CoilParameterServiceImpl._calc_l_vias``).
    Dieses Feld ist der Anker für *„wo muss ich editieren, wenn sich die
    Physik ändert?“* -- Details siehe ``docs/FORMELN-ANPASSEN.md``.

Anpassung
---------
Um eine Formel zu ändern, gibt es **zwei** Ebenen -- bitte bewusst
entscheiden welche:

* **Nur Anzeige**  → ``latex`` / ``description`` hier in der Registry
  anpassen. Ergebnis in GUI/Reports ändert sich, die Berechnung
  bleibt identisch.
* **Auch Berechnung**  → zusätzlich die in ``impl`` referenzierte
  Python-Funktion anpassen. Vorgehensweise + Konsistenz-Checkliste:
  **siehe** ``docs/FORMELN-ANPASSEN.md``.

Tests prüfen automatisch, dass jeder registrierte ``key`` im Rechenkern
verwendet wird und das ``impl``-Ziel existiert
(``tests/unit/test_formula_registry.py``).

Konsistenz-Check
----------------
Die Funktion :func:`check_coverage` kann in Tests aufgerufen werden,
um zu verifizieren, dass alle registrierten Formeln tatsächlich
aus dem Code referenziert werden und umgekehrt keine freien
Formel-Strings verwendet werden.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Formula:
    """Deklarative Beschreibung einer physikalischen Formel."""

    key: str
    latex: str
    description: str
    variables: Mapping[str, str]
    unit: str
    reference: str
    impl: str  # "module.path::function_or_method"  (Cross-Link auf Python-Impl)

    def __post_init__(self) -> None:
        # variables immutable machen
        object.__setattr__(self, "variables",
                           MappingProxyType(dict(self.variables)))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
#
# WICHTIG: Reihenfolge und Schlüssel sind stabil -- bitte nicht willkürlich
# umbenennen (Abwärtskompatibilität persistierter Traces).
#

_FORMULAS: dict[str, Formula] = {}


def _add(f: Formula) -> None:
    if f.key in _FORMULAS:
        raise ValueError(f"Duplicate formula key: {f.key!r}")
    _FORMULAS[f.key] = f


# --- Geometrie-Schritt (nur Eingangsdaten) --------------------------------
_add(Formula(
    key="geometry_extract",
    latex="extrahiert aus TraceLayout + Board + Stackup",
    description=(
        "Kein Rechenschritt im engeren Sinn, sondern Zusammenfassung der "
        "aus dem klassifizierten TraceLayout, dem Board und dem Stackup "
        "extrahierten Geometrie-Parameter."
    ),
    variables={
        "W":  "Leiterbreite [m]",
        "H":  "Leiter-Lagenabstand [m]",
        "T":  "Kupferdicke [m]",
        "l_track":  "Gesamtlänge Windungssegmente [m]",
        "h_via":    "Via-Höhe (Lagenabstand) [m]",
        "d_via":    "Via-Bohrdurchmesser [m]",
        "n_vias":   "Anzahl Vias im Windungspfad",
        "l_trace":  "Länge Anschlussleitung [m]",
        "eps_r":    "Substrat-Permittivität",
        "N_turns":  "Windungszahl",
        "p":        "Pitch (Center-to-Center) der Zähne [m]",
    },
    unit="–",
    reference="docs/berechnungen.md §Geometrie",
    impl="domain.coil.geometry::GeometryExtractor.extract",
))

# --- L_track (Ruehli/Lorenz Selbstinduktivität pro Segment) ---------------
_add(Formula(
    key="L_track_self_segment",
    latex="L_self,i = µ₀·l_i/(2π)·[ln(2·l_i/(w+t)) + 0.5 + 0.2235·(w+t)/l_i]",
    description=(
        "Freiraum-Selbstinduktivität eines einzelnen rechteckigen "
        "Leitersegments nach Ruehli/Lorenz (1972). L_track = n_seg · L_self,i. "
        "Kein Mikrostreifen-Modell – keine durchgehende GND-Plane angenommen."
    ),
    variables={
        "l_i":   "Segmentlänge [m]  (l_track / n_seg)",
        "w":     "Leiterbreite [m]",
        "t":     "Kupferdicke [m]",
        "n_seg": "Anzahl Segmente (= 2·N_turns, Top + Bottom)",
        "µ₀":    "Permeabilität des Vakuums [H/m]",
    },
    unit="µH",
    reference=(
        "Ruehli A. E., 'Inductance calculations in a complex "
        "integrated circuit environment', IBM J. Res. Dev., 1972; "
        "docs/berechnungen.md §L_track"
    ),
    impl="domain.coil.service::CoilParameterServiceImpl._calc_l_track",
))

# --- L_vias ---------------------------------------------------------------
_add(Formula(
    key="L_vias",
    latex="L_vias = n · µ₀·h / (2π) · (1 + ln(4h/d))",
    description=(
        "Induktivität der Vias des Windungspfades. Zylindrischer Draht, "
        "Summe über alle Vias (serielle Anordnung im Windungspfad)."
    ),
    variables={
        "h":  "Via-Höhe (Lagenabstand) [m]",
        "d":  "Via-Bohrdurchmesser [m]",
        "n":  "Anzahl Vias",
        "µ₀": "Permeabilität des Vakuums [H/m]",
    },
    unit="nH",
    reference=(
        "Goldfarb M. E., Pucel R. A., 'Modeling via hole grounds in "
        "microstrip', IEEE MGWL, 1991; docs/berechnungen.md §L_vias"
    ),
    impl="domain.coil.service::CoilParameterServiceImpl._calc_l_vias",
))

# --- L_trace (Anschlussleitung) ------------------------------------------
_add(Formula(
    key="L_trace",
    latex="L_trace = µ₀·l / (2π) · (ln(2l/w) + 0.5 + 0.2235·w/l)",
    description=(
        "Induktivität der Anschlussleitung (single-ended, Ruehli/Lorenz). "
        "Gleiche Formel wie L_track, jedoch mit der Gesamtlänge der als "
        "CONNECTION klassifizierten Segmente."
    ),
    variables={
        "l":  "Gesamtlänge Anschlussleitung [m]",
        "w":  "Leiterbreite [m]",
        "µ₀": "Permeabilität des Vakuums [H/m]",
    },
    unit="nH",
    reference="Ruehli/Lorenz 1972; docs/berechnungen.md §L_trace",
    impl="domain.coil.service::CoilParameterServiceImpl._calc_l_trace",
))

# --- L_total --------------------------------------------------------------
_add(Formula(
    key="L_total",
    latex="L_C = L_track + L_vias + L_trace",
    description=(
        "Gesamtinduktivität der Spule: Summe der drei Teilinduktivitäten "
        "(vernachlässigbare Gegeninduktivitäten zwischen benachbarten "
        "Zähnen – Annahme Fishbone-Layout)."
    ),
    variables={
        "L_track": "Induktivität der Windungsleiter [H]",
        "L_vias":  "Induktivität der Vias [H]",
        "L_trace": "Induktivität der Anschlussleitung [H]",
    },
    unit="µH",
    reference="docs/berechnungen.md §L_C",
    impl="domain.coil.service::CoilParameterServiceImpl.calculate",
))

# --- R_C (Serienwiderstand temperaturkorrigiert) --------------------------
_add(Formula(
    key="R_series",
    latex="R_C = ρ(T)·l_total / (W·T_cu)   mit  ρ(T) = ρ₂₀·(1 + α·ΔT)",
    description=(
        "Ohmscher Serienwiderstand. Linearer Temperatur-Koeffizient, "
        "Querschnittsfläche A = W·T_cu, DC-Näherung (Skin-Effekt wird "
        "im frequenzabhängigen Modell separat behandelt)."
    ),
    variables={
        "ρ₂₀":   "spez. elektrischer Widerstand Cu @ 20 °C [Ω·m]",
        "α":     "linearer Temperatur-Koeffizient Cu [1/K]",
        "ΔT":    "T - 20 °C",
        "l_total": "Gesamtleitungslänge (l_track + l_trace) [m]",
        "W":     "Leiterbreite [m]",
        "T_cu":  "Kupferdicke [m]",
    },
    unit="Ω",
    reference="docs/berechnungen.md §R_C",
    impl="domain.coil.service::CoilParameterServiceImpl._calc_r_series",
))

# --- C_C (Interleiter-Kapazität, CPS-Modell) ------------------------------
_add(Formula(
    key="C_interturn_cps",
    latex=(
        "C'_CPS = ε₀·ε_eff · K(k')/K(k)\n"
        "C_C    = C'_CPS · l_seg · N_pairs\n"
        "k = s/(s+2W),  s = p-W,  ε_eff = (1+εr)/2"
    ),
    description=(
        "Interleiter-Kapazität nach dem Modell koplanarer Streifen "
        "ohne Grundebene (CPS). Hilberg-Näherung für K(k)/K(k'). "
        "ε_eff = (1+εr)/2 berücksichtigt halb Substrat, halb Luft."
    ),
    variables={
        "W":       "Leiterbreite [m]",
        "p":       "Pitch (Mitte-Mitte) benachbarter Zähne [m]",
        "s":       "Kante-zu-Kante Abstand (p - W) [m]",
        "k, k'":   "CPS-Modulparameter, k' = √(1-k²)",
        "ε_r":     "relative Substrat-Permittivität",
        "ε_eff":   "effektive Permittivität (CPS, ohne GND)",
        "l_seg":   "mittlere Zahnlänge (l_track / (2·N)) [m]",
        "N_pairs": "Anzahl Nachbarschaftspaare (= 2·(N-1))",
    },
    unit="pF",
    reference=(
        "Hilberg W., 'From approximations to exact relations for "
        "characteristic impedances', IEEE MTT, 1969; "
        "docs/berechnungen.md §C_C"
    ),
    impl="domain.coil.service::CoilParameterServiceImpl._calc_c_series",
))

# --- f_res ----------------------------------------------------------------
_add(Formula(
    key="f_res",
    latex="f_res = 1 / (2π·√(L_C·C_C))",
    description=(
        "Eigenresonanzfrequenz des LC-Schwingkreises (Rogowski-Coil ohne "
        "Bürde). Dämpfung durch R_C wird hier nicht berücksichtigt; "
        "für Q < 1/2 verschiebt sich das tatsächliche Maximum."
    ),
    variables={
        "L_C": "Gesamtinduktivität [H]",
        "C_C": "parasitäre Interleiter-Kapazität [F]",
    },
    unit="MHz",
    reference="docs/berechnungen.md §f_res",
    impl="domain.coil.service::CoilParameterServiceImpl.calculate",
))

# --- Mutual: Primärleiter-Konfiguration -----------------------------------
_add(Formula(
    key="M_conductor_config",
    latex="Leiter 1: (+I) bei (x₁, y₁),  Leiter 2: (−I) bei (x₂, y₂)",
    description=(
        "Dokumentation der Primärleiter-Konfiguration (Dual-Busbar). "
        "Kein Rechenschritt – nur Eingangsdaten für die anschließenden "
        "Fensterintegrale."
    ),
    variables={
        "x₁, y₁":   "Position Leiter 1 (Hin-Leiter, +I) [m]",
        "x₂, y₂":   "Position Leiter 2 (Rück-Leiter, −I) [m]",
        "axis":     "Leiterachse (z: senkrecht zur PCB)",
        "N_windows": "Anzahl der Via-Fenster",
    },
    unit="Fenster",
    reference="docs/berechnungen.md §M_prim (Dual-Busbar)",
    impl="domain.mutual.calculator::MutualInductanceCalculator.compute",
))

# --- M_total --------------------------------------------------------------
_add(Formula(
    key="M_total",
    latex="M_ges = Σ |M_m|  (betragsmäßige Aufsummierung)",
    description=(
        "Gesamt-Gegeninduktivität zwischen Primärleitern und Spule: "
        "Betragssumme der Einzelbeiträge aller Via-Fenster. "
        "Die Betragsbildung verhindert Auslöschung bei Fishbone-Layout, "
        "in dem benachbarte Fenster entgegengesetzt orientiert sind (σ_m). "
        "M_m pro Fenster wird je nach Methode über das Linienintegral "
        "des realen B-Feldes, eine analytische ln-Formel oder 2D-"
        "Rasterintegration berechnet (siehe "
        "``MutualInductanceCalculator``)."
    ),
    variables={
        "M_m":    "Fensterbeitrag zur Gegeninduktivität [H]",
        "σ_m":    "Vorzeichen/Orientierung des Fensters ±1",
        "N_windows": "Anzahl Fenster",
    },
    unit="nH",
    reference="docs/berechnungen.md §M_prim",
    impl="domain.mutual.calculator::MutualInductanceCalculator._compute_window_field_integral",
))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

#: Immutable view auf die Registry -- importiere dies in den Rechenkernen.
FORMULAS: Mapping[str, Formula] = MappingProxyType(_FORMULAS)


def latex(key: str) -> str:
    """Komfort-Zugriff: gibt den LaTeX-/Unicode-String der Formel zurück.

    Löst über ``FORMULAS[key]`` auf und wirft ``KeyError`` bei unbekanntem
    Schlüssel. Unbekannte Schlüssel sind ein *Programmierfehler* und
    dürfen nicht stillschweigend ignoriert werden.
    """
    return FORMULAS[key].latex


def check_coverage(referenced_keys: set[str]) -> tuple[set[str], set[str]]:
    """Prüft Konsistenz zwischen Registry und Code.

    Returns:
        (missing, unused):
            * ``missing``  -- im Code referenzierte Schlüssel, die *nicht*
              in der Registry stehen (→ Registry-Eintrag fehlt).
            * ``unused``   -- in der Registry deklariert, aber nirgends
              im Code referenziert (→ Formel ist tot oder umbenannt).
    """
    declared = set(FORMULAS.keys())
    missing = referenced_keys - declared
    unused = declared - referenced_keys
    return missing, unused


def resolve_impl(key: str) -> object:
    """Löst ``Formula.impl`` zu einem aufrufbaren Python-Objekt auf.

    Format von ``impl``:  ``modul.pfad::funktion_oder_methode``.
    Der Modulpfad ist **relativ zu ``pcb_rogowski``** (also ohne den
    Paket-Prefix), z. B. ``domain.coil.service::CoilParameterServiceImpl._calc_l_vias``.

    Wirft ``ImportError`` oder ``AttributeError`` wenn das Ziel fehlt --
    genau dieses Verhalten verifiziert ``test_formula_registry`` beim
    Start, sodass umbenannte Funktionen sofort auffallen.
    """
    import importlib

    spec = FORMULAS[key].impl
    if "::" not in spec:
        raise ValueError(f"Invalid impl-spec for {key!r}: {spec!r} (missing '::')")
    mod_path, attr_path = spec.split("::", 1)
    module = importlib.import_module(f"pcb_rogowski.{mod_path}")
    obj: object = module
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    return obj


__all__ = ["Formula", "FORMULAS", "latex", "check_coverage", "resolve_impl"]
