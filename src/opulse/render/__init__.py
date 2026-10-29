"""Render Opulse values as images and sound, and export benchmark tasks with media.

Values use the shared encoding of the world showcases:

* ``{"t": "grid", "v": [[...]]}`` with ARC colours 0 to 9 becomes a PNG image;
* ``{"t": "note", "v": 60}`` and ``{"t": "melody", "v": [{"p": 60, "d": 1}, ...]}`` become WAV audio;
* ``{"t": "state", "v": {...}}`` (the action world) becomes a top-down PNG image.

Everything is deterministic: equal values and options give equal bytes.
"""

from __future__ import annotations

from dataclasses import dataclass

from opulse.render.audio import melody_midi, melody_wav, note_wav
from opulse.render.grid import ARC_PALETTE, grid_png
from opulse.render.png import encode_png, read_png
from opulse.render.state import state_png


@dataclass(frozen=True)
class RenderOptions:
    cell: int = 24            # grid cell size in pixels
    gridlines: bool = True
    state_cell: int = 32      # action map cell size in pixels
    sample_rate: int = 16000
    bpm: float = 120.0
    note_beats: int = 1       # how long a single note sounds


@dataclass(frozen=True)
class Media:
    kind: str   # "image" or "audio"
    ext: str
    mime: str
    data: bytes


def media_kind(value: dict) -> str | None:
    """``"image"``, ``"audio"`` or ``None`` (a value with no media form) for an encoded value."""
    return {"grid": "image", "state": "image", "note": "audio", "melody": "audio"}.get(
        value.get("t") if isinstance(value, dict) else None)


def render_value(value: dict, options: RenderOptions | None = None) -> Media | None:
    """The media form of an encoded value, or ``None`` for kinds without one (int, bool, ...)."""
    options = options or RenderOptions()
    kind = value.get("t") if isinstance(value, dict) else None
    if kind == "grid":
        return Media("image", "png", "image/png", grid_png(value["v"], options.cell, options.gridlines))
    if kind == "state":
        return Media("image", "png", "image/png", state_png(value["v"], options.state_cell))
    if kind == "melody":
        return Media("audio", "wav", "audio/wav", melody_wav(value["v"], options.sample_rate, options.bpm))
    if kind == "note":
        return Media("audio", "wav", "audio/wav",
                     note_wav(value["v"], options.note_beats, options.sample_rate, options.bpm))
    return None


__all__ = ["ARC_PALETTE", "Media", "RenderOptions", "encode_png", "grid_png", "media_kind", "melody_midi",
           "melody_wav", "note_wav", "read_png", "render_value", "state_png"]
