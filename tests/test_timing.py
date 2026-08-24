import time

from local_lens.timing import Stopwatch


def test_measure_records_duration_in_ms():
    sw = Stopwatch()
    with sw.measure("stage_a"):
        time.sleep(0.01)
    assert "stage_a" in sw.timings_ms
    assert sw.timings_ms["stage_a"] > 0


def test_multiple_stages_accumulate():
    sw = Stopwatch()
    with sw.measure("a"):
        pass
    with sw.measure("b"):
        pass
    assert set(sw.timings_ms.keys()) == {"a", "b"}


def test_total_ms_sums_all_stages():
    sw = Stopwatch()
    with sw.measure("a"):
        time.sleep(0.005)
    with sw.measure("b"):
        time.sleep(0.005)
    assert sw.total_ms >= sw.timings_ms["a"] + sw.timings_ms["b"] - 0.1


def test_exception_inside_measure_still_records_timing():
    sw = Stopwatch()
    try:
        with sw.measure("failing"):
            raise ValueError("boom")
    except ValueError:
        pass
    assert "failing" in sw.timings_ms
