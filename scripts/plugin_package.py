#!/usr/bin/env python3
"""Developer entry point; run from an LDS source checkout, without booting LDS."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'sdk' / 'python'))

from lds_package.cli import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main())
