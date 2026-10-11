"""The worker count is a validated setting, not a hidden constant."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_default_is_two(monkeypatch):
    monkeypatch.delenv("JOB_WORKERS", raising=False)
    # _env_file=None so the developer's real .env cannot change the result.
    assert Settings(_env_file=None).job_workers == 2


def test_environment_variable_overrides_default(monkeypatch):
    monkeypatch.setenv("JOB_WORKERS", "4")
    assert Settings(_env_file=None).job_workers == 4


@pytest.mark.parametrize("bad_value", ["0", "17"])
def test_out_of_range_value_is_rejected(monkeypatch, bad_value):
    monkeypatch.setenv("JOB_WORKERS", bad_value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)