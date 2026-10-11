import math
from datetime import datetime

import numpy as np
import pytest

from app.api.schemas import json_safe


@pytest.mark.parametrize(
    "value,expected",
    [
        (float("nan"), None),
        (float("inf"), None),
        (np.int64(5), 5),
        (np.float64(1.5), 1.5),
        (datetime(2020, 1, 2), "2020-01-02T00:00:00"),
    ],
)
def test_json_safe_scalars(value, expected):
    assert json_safe(value) == expected


def test_json_safe_nested_values():
    result = json_safe({"a": [1, float("nan"), np.int64(2)], "b": {"c": np.float64(math.inf)}})
    assert result == {"a": [1, None, 2], "b": {"c": None}}