#!/usr/bin/env python3
"""FrontDesk Book launcher. Needs only Python 3.9+ (standard library)."""
import sys

if sys.version_info < (3, 9):
    sys.exit("FrontDesk Book needs Python 3.9 or newer.")

from frontdesk.app import main  # noqa: E402

if __name__ == "__main__":
    main()
