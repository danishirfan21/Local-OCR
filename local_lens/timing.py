"""Lightweight stage timing.

Not a profiler -- just enough to answer "where did the time go" for a
single pipeline run, surfaced in DocumentResult.metadata["timings"] and an
"Advanced details" UI panel. This will also inform future routing decisions
(e.g. "is table extraction worth its latency cost here").
"""

from __future__ import annotations

import time
from contextlib import contextmanager


class Stopwatch:
    """Accumulates named stage durations (milliseconds) across a pipeline run."""

    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}

    @contextmanager
    def measure(self, stage: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.timings_ms[stage] = round((time.perf_counter() - start) * 1000, 1)

    @property
    def total_ms(self) -> float:
        return round(sum(self.timings_ms.values()), 1)
