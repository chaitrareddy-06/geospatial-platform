import pytest

from app.domain.enums.job_status import JobStatus
from app.workers.job_runner import InlineJobRunner, ThreadPoolJobRunner


def test_inline_runner_completes_a_queued_job(make_service, kml_bytes):
    service = make_service()
    queued = service.submit("survey.kml", kml_bytes)

    InlineJobRunner(service).submit(queued.id, kml_bytes)

    assert service.get(queued.id).status is JobStatus.COMPLETED


def test_inline_runner_swallows_errors_for_unknown_ids(make_service, kml_bytes):
    InlineJobRunner(make_service()).submit("does-not-exist", kml_bytes)  # no raise


def test_thread_pool_runner_completes_a_queued_job(make_service, kml_bytes):
    service = make_service()
    queued = service.submit("survey.kml", kml_bytes)
    runner = ThreadPoolJobRunner(service, max_workers=2)

    runner.submit(queued.id, kml_bytes)
    runner.shutdown(wait=True)  # waits for the job to finish

    done = service.get(queued.id)
    assert done.status is JobStatus.COMPLETED
    assert done.feature_count == 3


def test_thread_pool_runner_survives_a_bad_job(make_service, kml_bytes):
    service = make_service()
    queued = service.submit("survey.kml", kml_bytes)
    runner = ThreadPoolJobRunner(service)

    runner.submit("does-not-exist", kml_bytes)  # fails inside the worker
    runner.submit(queued.id, kml_bytes)  # must still run afterwards
    runner.shutdown(wait=True)

    assert service.get(queued.id).status is JobStatus.COMPLETED


def test_thread_pool_runner_rejects_zero_workers(make_service):
    with pytest.raises(ValueError):
        ThreadPoolJobRunner(make_service(), max_workers=0)