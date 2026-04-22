"""Domain Layer -- Fachmodelle und Berechnungs-Primitive.

Vollstaendig unabhaengig von UI, IO und Framework. Alle Groessen in
SI-Einheiten; Anzeige-Umrechnungen (uH, pF, nH) geschehen ausschliesslich
in :mod:`pcb_rogowski.ui` oder in Convenience-Properties.

Subpakete
---------

* ``board``      -- Board-/Layer-/LineFeature-/Pad-Modelle.
* ``trace``      -- Klassifikation, Topologie-Reparatur.
* ``coil``       -- L, R, C und Uebertragungsfunktion (LRC+M).
* ``mutual``     -- Gegeninduktivitaet M (3 Methoden).
* ``materials``  -- Materialdaten (Cu-Leitfaehigkeit T-abhaengig, eps_r).
* ``stackup``    -- Lagenaufbau (Kupferdicke, Prepreg, Dielektrika).
* ``common``     -- :class:`CalculationTrace`, :class:`TraceStep`.
* ``validation`` -- Bereichs- und Konsistenzpruefungen.

Architektur-Regel: Keine Importe aus :mod:`pcb_rogowski.infrastructure`,
:mod:`pcb_rogowski.app` oder :mod:`pcb_rogowski.ui`. Siehe
``docs/adr/ADR-001-layered-architecture.md``.
"""
