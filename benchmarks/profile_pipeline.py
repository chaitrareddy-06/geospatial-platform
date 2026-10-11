"""Shows where the time goes for one dataset. Usage:
python -m benchmarks.profile_pipeline benchmarks/data/polygon_100000.zip
"""

from __future__ import annotations

import cProfile
import pstats
import sys
from pathlib import Path

from benchmarks.run_pipeline import run_once

profiler = cProfile.Profile()
profiler.runcall(run_once, Path(sys.argv[1]))
pstats.Stats(profiler).sort_stats("cumulative").print_stats(25)