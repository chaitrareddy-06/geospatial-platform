import json
import logging

import pytest

from app.core.logging_config import (
    JsonFormatter,
    configure_logging,
    job_id_ctx,
    request_id_ctx,
)


def make_record(msg="hello", level=logging.INFO, exc_info=None, **extra):
    logger = logging.getLogger("test")
    record = logger.makeRecord("test", level, __file__, 1, msg, (), exc_info, extra=extra)
    return record


def test_output_is_valid_json_with_core_fields():
    out = json.loads(JsonFormatter().format(make_record("hello")))
    assert out["message"] == "hello"
    assert out["level"] == "INFO"
    assert out["logger"] == "test"
    assert "timestamp" in out


def test_extra_fields_are_included():
    out = json.loads(JsonFormatter().format(make_record(features=120)))
    assert out["features"] == 120


def test_context_ids_are_included_when_set():
    t1 = request_id_ctx.set("req-1")
    t2 = job_id_ctx.set("job-1")
    try:
        out = json.loads(JsonFormatter().format(make_record()))
    finally:
        request_id_ctx.reset(t1)
        job_id_ctx.reset(t2)
    assert out["request_id"] == "req-1"
    assert out["job_id"] == "job-1"


def test_context_ids_absent_when_not_set():
    out = json.loads(JsonFormatter().format(make_record()))
    assert "request_id" not in out
    assert "job_id" not in out


def test_exception_is_captured():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = make_record("failed", level=logging.ERROR, exc_info=sys.exc_info())
    out = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in out["exception"]


def test_non_serializable_extra_does_not_crash():
    out = json.loads(JsonFormatter().format(make_record(obj=object())))
    assert "obj" in out


def test_configure_logging_is_idempotent_and_sets_level():
    configure_logging("DEBUG")
    configure_logging("WARNING")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.WARNING