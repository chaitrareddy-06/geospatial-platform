"""Real files carry float noise at the lon/lat limits; clearly bad values still fail."""

from __future__ import annotations

import pytest
from shapely import box

from app.core.exceptions import CRSResolutionError
from app.services.projection_strategy import (
    REASON_NOT_LONLAT,
    REASON_POLAR,
    STRATEGY_LAEA,
    choose_projection,
)


def test_longitude_a_hair_past_180_is_accepted() -> None:
    # The Natural Earth countries file has max longitude 180.00000000000006.
    choice = choose_projection([box(170.0, 0.0, 180.00000000000006, 10.0)])
    assert choice.label


def test_latitude_a_hair_past_minus_90_is_accepted_and_clipped() -> None:
    choice = choose_projection([box(0.0, -90.00000000000003, 10.0, -80.0)])
    assert choice.strategy == STRATEGY_LAEA
    assert choice.reason == REASON_POLAR
    assert choice.center_lat == pytest.approx(-85.0)


@pytest.mark.parametrize(
    "geom",
    [
        box(170.0, 0.0, 180.001, 10.0),
        box(-180.001, 0.0, -170.0, 10.0),
        box(0.0, 80.0, 10.0, 90.001),
    ],
)
def test_clearly_out_of_range_coordinates_are_still_rejected(geom) -> None:
    with pytest.raises(CRSResolutionError) as info:
        choose_projection([geom])
    assert info.value.details["reason"] == REASON_NOT_LONLAT