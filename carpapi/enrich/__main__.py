"""Allow ``python -m carpapi.enrich`` to dispatch into the CLI."""
from __future__ import annotations

import sys

from .cli import main


if __name__ == "__main__":
    sys.exit(main())
