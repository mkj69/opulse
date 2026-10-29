"""Compile two operators separately, stitch their weights, and compare with the whole compile.

    python examples/compile/stitch_demo.py            # domain 0..15
    python examples/compile/stitch_demo.py --n 8 --trained

Same as ``python -m opulse.compile``. Needs torch.
"""

from opulse.compile.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
