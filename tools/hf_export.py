"""Standalone entry point for the local Hugging Face dataset export."""

from __future__ import annotations

import argparse

from opulse.cli.export import add_arguments, run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
