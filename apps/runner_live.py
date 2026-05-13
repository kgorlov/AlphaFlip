"""Live runner entrypoint.

Live trading must stay disabled unless config and runtime confirmation both allow it.
"""

import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    raise SystemExit("Live runner is not implemented. Use paper/shadow first.")


if __name__ == "__main__":
    main()
