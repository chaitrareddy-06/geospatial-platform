import pytest
from pydantic import ValidationError
from shapely.geometry import Point

from app.core.config import Settings
from app.services.projection_strategy import choose_projection


def test_offset_between_thresholds_flips_strategy():
    # Centred on zone 44's centre line (81 deg); the edges are 2.5 deg away.
    data = [Point(78.5, 17.0), Point(83.5, 17.0)]
    assert choose_projection(data, max_utm_offset_deg=4.0).strategy == "utm"
    assert choose_projection(data, max_utm_offset_deg=2.0).strategy == "laea"


def test_zone_edge_dataset_flips_at_three_degrees():
    # A tiny dataset on a zone boundary is about 3 deg from the centre line,
    # so a threshold of 3 or lower sends even tiny files to equal-area.
    data = [Point(77.9, 17.0), Point(78.1, 17.0)]
    assert choose_projection(data, max_utm_offset_deg=4.0).strategy == "utm"
    assert choose_projection(data, max_utm_offset_deg=3.0).strategy == "laea"


@pytest.mark.parametrize("bad_value", [0, -1.0, 10.5])
def test_invalid_threshold_parameter_raises(bad_value):
    with pytest.raises(ValueError):
        choose_projection([Point(78.47, 17.38)], max_utm_offset_deg=bad_value)


def test_threshold_of_ten_is_accepted():
    result = choose_projection([Point(78.47, 17.38)], max_utm_offset_deg=10.0)
    assert result.strategy == "utm"


def test_setting_default_is_four():
    assert Settings().max_utm_offset_degrees == 4.0


def test_setting_zero_is_rejected():
    with pytest.raises(ValidationError):
        Settings(max_utm_offset_degrees=0)


def test_setting_above_ten_is_rejected():
    with pytest.raises(ValidationError):
        Settings(max_utm_offset_degrees=11)


def test_setting_ten_is_accepted():
    assert Settings(max_utm_offset_degrees=10).max_utm_offset_degrees == 10