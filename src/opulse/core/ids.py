"""Random identifiers for generated operator functions."""

from __future__ import annotations

import random
import string

FUNC_ID_ALPHABET = string.ascii_letters + string.digits
FUNC_ID_LENGTH = 10


def new_func_id(rng: random.Random | None = None) -> str:
    """Return a 10-character alphanumeric id usable inside a Python identifier."""
    rng = rng or random
    return "".join(rng.choice(FUNC_ID_ALPHABET) for _ in range(FUNC_ID_LENGTH))
