"""`python -m horus_graph` → CLI yang sama dengan `horus-graph`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
