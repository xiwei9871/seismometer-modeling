"""Project-level entry point for the static Task 9A-R1 pipeline."""

from __future__ import annotations

import sys

from stage_09A_R1_exploded_rework.scripts.pipeline import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
