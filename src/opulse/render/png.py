"""A minimal, deterministic PNG codec for 8-bit RGB images.

Images are numpy arrays of shape ``(height, width, 3)`` and dtype ``uint8``. The encoder
uses filter type 0 and a fixed zlib level, so the same pixels always give the same bytes.
Pillow is not needed; :func:`read_png` decodes the files this module writes (tests use it).
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(pixels: np.ndarray) -> bytes:
    """PNG bytes for an RGB ``uint8`` array of shape ``(height, width, 3)``."""
    pixels = np.ascontiguousarray(pixels, dtype=np.uint8)
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError("pixels must have shape (height, width, 3)")
    height, width = pixels.shape[:2]
    if height < 1 or width < 1:
        raise ValueError("an image needs at least one pixel")
    rows = np.zeros((height, 1 + 3 * width), dtype=np.uint8)  # leading 0: filter type None
    rows[:, 1:] = pixels.reshape(height, 3 * width)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows.tobytes(), 9))
            + _chunk(b"IEND", b""))


def read_png(data: bytes) -> np.ndarray:
    """Decode an 8-bit RGB, non-interlaced PNG written with filter type 0 (as :func:`encode_png` writes)."""
    if data[:8] != _SIGNATURE:
        raise ValueError("not a PNG file")
    position, idat, header = 8, b"", None
    while position < len(data):
        (length,) = struct.unpack(">I", data[position:position + 4])
        kind = data[position + 4:position + 8]
        body = data[position + 8:position + 8 + length]
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        position += 12 + length
    if header is None:
        raise ValueError("PNG without a header")
    width, height, depth, colour, _, _, interlace = header
    if (depth, colour, interlace) != (8, 2, 0):
        raise ValueError("only 8-bit RGB non-interlaced PNG files are supported")
    rows = np.frombuffer(zlib.decompress(idat), dtype=np.uint8).reshape(height, 1 + 3 * width)
    if rows[:, 0].any():
        raise ValueError("only filter type 0 is supported")
    return rows[:, 1:].reshape(height, width, 3).copy()


def png_size(data: bytes) -> tuple[int, int]:
    """``(width, height)`` from the PNG header."""
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def hex_colour(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
