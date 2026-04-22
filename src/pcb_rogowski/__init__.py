"""PCB Rogowski Coil Analysis Tool.

Wissenschaftliches Framework zur Berechnung, Visualisierung und
Validierung von PCB-basierten Rogowski-Spulen. Bereitstellung eines
kompletten Workflows:

1. **Import**: Gerber (gerbonara), optional ODB++.
2. **Klassifikation**: Segment-Rollen (winding / return / connection)
   plus Orientierung sigma und Via-Fenster.
3. **Berechnung**: L (Ruehli/Lorenz), R (DC + Skin/Proximity),
   C (Parallelplatten), M (analytisch / Flaechenintegral / numerisch).
4. **Uebertragungsfunktion**: H(s) = s*M / (1 + s*R*C + s^2*L*C).
5. **Validierung**: Fit gegen Bode100-Messungen.

Einstiegspunkte: :func:`pcb_rogowski.main.main` (CLI) und
:func:`pcb_rogowski.main.main_gui` (PyQt6-GUI).

Alle Formeln siehe ``docs/berechnungen.md``.
"""
