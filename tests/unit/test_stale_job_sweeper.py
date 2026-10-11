"""The sweeper thread: sweeps on a timer, survives errors, stops promptly."""

import threading

import pytest

from app.workers.stale_job_sweeper import StaleJobSweeper


class FakeService:
    def __init__(self, result=0, fail_first=False):
        self.calls = []
        self.enough = threading.Event()
        self._result = result
        self._fail_first = fail_first

    def fail_stale_jobs(self, *, max_age_seconds, now=None):
        self.calls.append({"max_age_seconds": max_age_seconds})
        if len(self.calls) >= 2:
            self.enough.set()
        if self._fail_first and len(self.calls) == 1:
            raise RuntimeError("boom")
        return self._result


def test_run_once_calls_the_service_and_returns_its_count():
    service = FakeService(result=3)
    sweeper = StaleJobSweeper(service, max_age_seconds=600.0, interval_seconds=1.0)

    assert sweeper.run_once() == 3
    assert service.calls == [{"max_age_seconds": 600.0}]


@pytest.mark.parametrize(
    ("max_age", "interval"), [(0, 1), (-1, 1), (1, 0), (1, -1)]
)
def test_non_positive_arguments_are_rejected(max_age, interval):
    with pytest.raises(ValueError):
        StaleJobSweeper(
            FakeService(), max_age_seconds=max_age, interval_seconds=interval
        )


def test_background_thread_sweeps_repeatedly():
    service = FakeService()
    sweeper = StaleJobSweeper(service, max_age_seconds=600.0, interval_seconds=0.01)

    sweeper.start()
    try:
        assert service.enough.wait(timeout=5)
    finally:
        sweeper.stop()

    assert len(service.calls) >= 2


def test_stop_is_prompt_and_safe_to_repeat():
    # A long interval proves stop() wakes the thread instead of waiting it out.
    sweeper = StaleJobSweeper(
        FakeService(), max_age_seconds=600.0, interval_seconds=3600.0
    )
    sweeper.start()
    assert sweeper.is_running

    sweeper.stop(timeout=5)
    sweeper.stop(timeout=5)

    assert not sweeper.is_running


def test_a_crashing_sweep_does_not_end_the_loop():
    service = FakeService(fail_first=True)
    sweeper = StaleJobSweeper(service, max_age_seconds=600.0, interval_seconds=0.01)

    sweeper.start()
    try:
        assert service.enough.wait(timeout=5)
    finally:
        sweeper.stop()

    assert len(service.calls) >= 2


def test_starting_twice_does_not_create_a_second_thread():
    sweeper = StaleJobSweeper(
        FakeService(), max_age_seconds=600.0, interval_seconds=3600.0
    )
    sweeper.start()
    try:
        first = sweeper._thread
        sweeper.start()
        assert sweeper._thread is first
    finally:
        sweeper.stop()