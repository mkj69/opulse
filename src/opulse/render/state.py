"""Action world states as top-down pictures, and derivations as frame sequences.

The input is the state payload of ``{"t": "state", "v": {...}}`` as the action world writes it:
``width``, ``height``, ``max_height``, ``terrain`` (rows of ``.`` floor, ``#`` wall, ``~`` water,
``B`` bench), ``stacks`` (``{"x", "y", "blocks"}`` bottom first), ``tools`` (``{"x", "y", "name"}``),
``bridges`` (``[x, y]`` pairs) and ``robot`` (``x``, ``y``, ``facing`` N/E/S/W and ``held``).
Only this payload is read; the action world itself is not imported.

Each map cell is a ``cell`` pixel square. Blocks are bars stacked from the bottom of their cell,
a tool is a brown diamond, and the robot is a dark disc with a white arrow toward its facing.
What the robot holds is a small square on the disc, behind the arrow.
"""

from __future__ import annotations

import numpy as np

from opulse.render.png import encode_png, hex_colour

TERRAIN = {".": "#EDE8DA", "#": "#3D3D3D", "~": "#4A90D9", "B": "#A0703C"}
BLOCKS = {"R": "#E53935", "B": "#1E63D6", "Y": "#F6C915", "G": "#2E9E44", "P": "#8E44AD", "O": "#F57C00"}
BRIDGE, BRIDGE_SEAM = "#C8A165", "#8B6B3E"
TOOL = "#8B5A2B"
GRIDLINE = "#BFB8A5"
OUTLINE = "#222222"
ROBOT, ARROW = "#262626", "#FFFFFF"


def _fill(image, x0, y0, x1, y1, colour):
    image[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = hex_colour(colour)


def _coords(cell: int):
    ys, xs = np.mgrid[0:cell, 0:cell]
    return xs + 0.5, ys + 0.5


def state_pixels(state: dict, cell: int = 32) -> np.ndarray:
    """An RGB array for an action state payload."""
    if cell < 12:
        raise ValueError("cell size must be at least 12 pixels")
    width, height = state["width"], state["height"]
    terrain = state["terrain"]
    if len(terrain) != height or any(len(row) != width for row in terrain):
        raise ValueError("terrain does not match the map size")
    image = np.empty((height * cell + 1, width * cell + 1, 3), dtype=np.uint8)
    image[:] = hex_colour(GRIDLINE)
    bridges = {tuple(p) for p in state.get("bridges", [])}
    for y, row in enumerate(terrain):
        for x, kind in enumerate(row):
            if kind not in TERRAIN:
                raise ValueError(f"unknown terrain {kind!r}")
            x0, y0 = x * cell + 1, y * cell + 1
            _fill(image, x0, y0, x0 + cell - 1, y0 + cell - 1, TERRAIN[kind])
            if kind == "~" and (x, y) in bridges:
                _fill(image, x0 + 2, y0, x0 + cell - 3, y0 + cell - 1, BRIDGE)
                for seam in range(y0 + 5, y0 + cell - 1, 6):
                    _fill(image, x0 + 2, seam, x0 + cell - 3, seam + 1, BRIDGE_SEAM)
    xs, ys = _coords(cell - 1)  # pixel centres inside one cell (the cell minus its gridline)
    max_height = max(1, state.get("max_height", 4))
    bar = max(2, (cell - 8) // max_height)
    for item in state.get("stacks", []):
        x0, y0 = item["x"] * cell + 1, item["y"] * cell + 1
        for level, colour in enumerate(item["blocks"]):
            if colour not in BLOCKS:
                raise ValueError(f"unknown block colour {colour!r}")
            bottom = y0 + cell - 4 - level * bar
            _fill(image, x0 + 4, bottom - bar, x0 + cell - 5, bottom, OUTLINE)
            _fill(image, x0 + 5, bottom - bar + 1, x0 + cell - 6, bottom - 1, BLOCKS[colour])
    for item in state.get("tools", []):
        x0, y0 = item["x"] * cell + 1, item["y"] * cell + 1
        diamond = np.abs(xs - (cell - 1) / 2) + np.abs(ys - cell * 0.3) <= cell * 0.2
        image[y0:y0 + cell - 1, x0:x0 + cell - 1][diamond] = hex_colour(TOOL)
    robot = state["robot"]
    x0, y0 = robot["x"] * cell + 1, robot["y"] * cell + 1
    patch = image[y0:y0 + cell - 1, x0:x0 + cell - 1]
    px, py = xs - (cell - 1) / 2, ys - (cell - 1) / 2
    radius = cell * 0.36
    patch[px * px + py * py <= radius * radius] = hex_colour(ROBOT)
    # Arrow toward the facing: rotate the frame so "forward" is +u.
    ux, uy = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}[robot["facing"]]
    u = px * ux + py * uy
    v = px * -uy + py * ux
    tip, base, half = radius * 0.95, radius * 0.35, radius * 0.45
    arrow = (u >= base) & (u <= tip) & (np.abs(v) <= half * (tip - u) / (tip - base))
    patch[arrow] = hex_colour(ARROW)
    held = robot.get("held")
    if held:
        colour = BLOCKS.get(held.get("colour")) if held.get("kind") == "block" else TOOL
        # A square behind the arrow, so both stay visible.
        size = max(2, cell // 7)
        cx = (cell - 1) // 2 - round(ux * radius * 0.3)
        cy = (cell - 1) // 2 - round(uy * radius * 0.3)
        patch[cy - size:cy + size, cx - size:cx + size] = hex_colour(ARROW)
        patch[cy - size + 1:cy + size - 1, cx - size + 1:cx + size - 1] = hex_colour(colour)
    return image


def state_png(state: dict, cell: int = 32) -> bytes:
    """PNG bytes for an action state payload (deterministic)."""
    return encode_png(state_pixels(state, cell))


def frames_gif(frames: list[np.ndarray], duration_ms: int = 700) -> bytes:
    """An animated GIF of equally sized RGB frames. Needs Pillow."""
    import io

    from PIL import Image

    if not frames:
        raise ValueError("no frames")
    images = [Image.fromarray(frame, "RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
              for frame in frames]
    buffer = io.BytesIO()
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=duration_ms,
                   loop=0, optimize=False)
    return buffer.getvalue()
