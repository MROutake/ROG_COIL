"""Application Layer -- Use-Cases und Ablaufsteuerung.

Dieses Paket orchestriert die Domaenen-Logik (Pipeline
Gerber-Import -> Klassifikation -> RLC/M-Berechnung) und enthaelt
bewusst KEINE Fachformeln, GUI- oder IO-Details.

Zentraler Einstiegspunkt:
:func:`pcb_rogowski.app.use_cases.analyze_design.analyze_design`.
"""
