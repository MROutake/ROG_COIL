"""Coil-Berechnungen: L, R, C und Uebertragungsfunktion.

Module
------

* ``inductance``        -- Eigen- und Via-Induktivitaet (Ruehli/Lorenz).
* ``resistance``        -- DC-Widerstand + Skin-/Proximity-Zuschlag.
* ``capacitance``       -- Parasitaere Parallelkapazitaet.
* ``transfer_function`` -- LRC+M-Ersatzschaltbild (``scipy.signal``).
* ``fitting``           -- Nichtlineare Anpassung an Bode100-Messungen.

Einheiten im gesamten Subpaket: SI (H, F, Ohm, Hz). Herleitungen:
``docs/berechnungen.md`` Abschnitt 2 - 4.
"""
