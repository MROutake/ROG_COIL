"""Smoke-Test: Gerber laden und Board-Statistiken ausgeben."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from pcb_rogowski.infrastructure.gerber.loader import GerberBoardLoader

# Pfade anpassen, wenn nötig
# Desgin 1 : data_samples/gerber/Desgin_01
# Desgin 2 : data_samples/gerber/Desgin_02
# Desgin 3 : data_samples/gerber/Desgin_03

loader = GerberBoardLoader()
board = loader.load_from_gerber(Path("data_samples/gerber/Desgin_01"))

print()
print(f"Board: {board.name}")
print(f"Outline: {board.outline_mm}")
print(f"Lagen: {len(board.layers)}")
for la in board.layers:
    print(f"  [{la.index:2d}] {la.name:<45s} {la.layer_type.value:<12s}  "
          f"{len(la.lines):>5d} Linien  {len(la.pads):>4d} Pads")
print(f"Summe: {sum(len(la.lines) for la in board.layers):,} Linien, "
      f"{sum(len(la.pads) for la in board.layers):,} Pads")
