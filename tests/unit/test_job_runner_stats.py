"""Job runner statistics: queued, active, finished and runner-level errors."""

import threading

import pytest

from app.workers.job_runner import InlineJobRunner, RunnerStats, ThreadPoolJobRunner


class OkService:
    def run_job(self, file_id, content):
        return None


class CrashingService:
    def run_job(self, file_id, content):
        raise RuntimeError("boom")


class BlockingService:
    """Holds every job until the test says go, so we can look mid-flight."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run_job(self, file_id, content):
        self.started.set()
        assert self.release.wait(timeout=5)


def test_fresh_runner_has_zero_counts():
    runner = ThreadPoolJobRunner(OkService(), max_workers=3)

    assert runner.stats() == RunnerStats(
        workers=3, queued=0, active=0, finished=0, errors=0
    )
    runner.shutdown()


def test_inline_runner_counts_a_finished_job():
    runner = InlineJobRunner(OkService())

    runner.submit("a", b"x")

    assert runner.stats() == RunnerStats(
        workers=1, queued=0, active=0, finished=1, errors=0
    )


def test_inline_runner_counts_an_error_and_does_not_raise():
    runner = InlineJobRunner(CrashingService())

    runner.submit("a", b"x")

    assert runner.stats() == RunnerStats(
        workers=1, queued=0, active=0, finished=1, errors=1
    )


def test_thread_pool_shows_one_active_and_one_queued_mid_flight():
    service = BlockingService()
    runner = ThreadPoolJobRunner(service, max_workers=1)

    runner.submit("a", b"x")
    runner.submit("b", b"x")
    assert service.started.wait(timeout=5)

    mid = runner.stats()
    assert mid.active == 1
    assert mid.queued == 1
    assert mid.finished == 0

    service.release.set()
    runner.shutdown(wait=True)

    done = runner.stats()
    assert done == RunnerStats(workers=1, queued=0, active=0, finished=2, errors=0)


def test_thread_pool_counts_an_error():
    runner = ThreadPoolJobRunner(CrashingService(), max_workers=1)

    runner.submit("a", b"x")
    runner.shutdown(wait=True)

    done = runner.stats()
    assert done.finished == 1
    assert done.errors == 1
    assert done.active == 0
    assert done.queued == 0


def test_submit_after_shutdown_raises_and_leaves_counters_clean():
    runner = ThreadPoolJobRunner(OkService(), max_workers=1)
    runner.shutdown()

    with pytest.raises(RuntimeError):
        runner.submit("a", b"x")

    assert runner.stats().queued == 0
    assert runner.stats().finished == 0