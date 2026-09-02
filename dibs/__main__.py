"""Entry point for `python -m dibs` (ARCHITECTURE §3, level L5)."""

import sys

from dibs import cli

if __name__ == '__main__':
    sys.exit(cli.main())
