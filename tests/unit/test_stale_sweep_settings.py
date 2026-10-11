"""The sweeper's two settings are validated, so a typo fails at startup."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("JOB_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("STALE_SWEEP_INTERVAL_SECONDS", raising=False)

    s = Settings(_env_file=None)

    assert s.job_timeout_seconds == 900.0
    assert s.stale_sweep_interval_seconds == 60.0


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("JOB_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("STALE_SWEEP_INTERVAL_SECONDS", "5")

    s = Settings(_env_file=None)

    assert s.job_timeout_seconds == 120.0
    assert s.stale_sweep_interval_seconds == 5.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JOB_TIMEOUT_SECONDS", "0"),
        ("JOB_TIMEOUT_SECONDS", "-5"),
        ("STALE_SWEEP_INTERVAL_SECONDS", "0"),
    ],
)
def test_non_positive_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)