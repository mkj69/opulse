"""Command line wrapper for the trained model report."""

import sys

from opulse.compile.handwired.analysis import main

if __name__ == "__main__":
    main(sys.argv[1:] or ["handwired_small"])
