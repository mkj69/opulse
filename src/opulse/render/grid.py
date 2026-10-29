"""Grid values as images in the ARC palette.

A grid is a rectangular list of rows of colours 0 to 9, as in ``{"t": "grid", "v": [[...]]}``.
Each cell becomes a ``cell`` by ``cell`` square. With gridlines, a line of ``line`` pixels
separates neighbouring cells and frames the image, so cell ``(row, col)`` starts at
``line + col * (cell + line)`` horizontally.
"""

from __future__ import annotations

import numpy as np

from opulse.render.png import encode_png, hex_colour

# The ARC task viewer palette, indexed by colour 0 to 9.
ARC_PALETTE = (
    "#000000",  # 0 black (background)
    "#0074D9",  # 1 blue
    "#FF4136",  # 2 red
    "#2ECC40",  # 3 green
    "#FFDC00",  # 4 yellow
    "#AAAAAA",  # 5 grey
    "#F012BE",  # 6 magenta
    "#FF851B",  # 7 orange
    "#7FDBFF",  # 8 sky
    "#870C25",  # 9 maroon
)
GRIDLINE = "#555555"


def check_grid(value) -> list[list[int]]:
    rows = [list(row) for row in value]
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("a grid needs at least one cell and rows of equal length")
    if any(type(cell) is not int or not 0 <= cell <= 9 for row in rows for cell in row):
        raise ValueError("grid colours are integers from 0 to 9")
    return rows


def cell_origin(row: int, col: int, cell: int = 24, line: int = 1) -> tuple[int, int]:
    """Top left pixel ``(x, y)`` of a cell."""
    return line + col * (cell + line), line + row * (cell + line)


def grid_pixels(value, cell: int = 24, gridlines: bool = True, line: int = 1,
                palette=ARC_PALETTE, line_colour: str = GRIDLINE) -> np.ndarray:
    """An RGB array for a grid value."""
    rows = check_grid(value)
    if cell < 1:
        raise ValueError("cell size must be positive")
    line = line if gridlines else 0
    height, width = len(rows), len(rows[0])
    colours = np.array([hex_colour(c) for c in palette], dtype=np.uint8)
    image = np.empty((line + height * (cell + line), line + width * (cell + line), 3), dtype=np.uint8)
    image[:] = hex_colour(line_colour)
    for r, row in enumerate(rows):
        for c, colour in enumerate(row):
            x, y = cell_origin(r, c, cell, line)
            image[y:y + cell, x:x + cell] = colours[colour]
    return image


def grid_png(value, cell: int = 24, gridlines: bool = True, line: int = 1, palette=ARC_PALETTE) -> bytes:
    """PNG bytes for a grid value (deterministic)."""
    return encode_png(grid_pixels(value, cell, gridlines, line, palette))
