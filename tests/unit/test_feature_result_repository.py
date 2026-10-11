import pytest

from app.domain.entities.feature_result import ProcessedFeature
from app.domain.enums.geometry_kind import GeometryKind
from app.repositories.in_memory_feature_result_repository import (
    InMemoryFeatureResultRepository,
)


def _feature(index: int, status: str = "measured") -> ProcessedFeature:
    return ProcessedFeature(
        index=index,
        kind=GeometryKind.POLYGON,
        status=status,
        reason=None,
        reason_code=None,
        repaired=False,
        properties={},
        measurement=None,
        cross_check=None,
        length_method=None,
    )


def test_add_layer_and_read_back():
    repo = InMemoryFeatureResultRepository()
    repo.add_layer("f1", "layer_a", [_feature(0), _feature(1)])
    page = repo.list_page("f1")
    assert page.total == 2
    assert [i.feature.index for i in page.items] == [0, 1]
    assert all(i.layer == "layer_a" for i in page.items)


def test_pagination_slices_in_order():
    repo = InMemoryFeatureResultRepository()
    repo.add_layer("f1", "a", [_feature(i) for i in range(10)])
    page = repo.list_page("f1", offset=3, limit=4)
    assert [i.feature.index for i in page.items] == [3, 4, 5, 6]
    assert page.total == 10
    assert (page.offset, page.limit) == (3, 4)


def test_status_filter_changes_total():
    repo = InMemoryFeatureResultRepository()
    repo.add_layer(
        "f1", "a", [_feature(0), _feature(1, "skipped"), _feature(2, "skipped")]
    )
    page = repo.list_page("f1", status="skipped")
    assert page.total == 2
    assert [i.feature.index for i in page.items] == [1, 2]


def test_unknown_file_gives_empty_page():
    page = InMemoryFeatureResultRepository().list_page("nope")
    assert page.items == ()
    assert page.total == 0


def test_layers_are_kept_separate_and_in_order():
    repo = InMemoryFeatureResultRepository()
    repo.add_layer("f1", "first", [_feature(0)])
    repo.add_layer("f1", "second", [_feature(0)])
    page = repo.list_page("f1")
    assert [i.layer for i in page.items] == ["first", "second"]


def test_offset_past_end_is_empty_but_total_is_correct():
    repo = InMemoryFeatureResultRepository()
    repo.add_layer("f1", "a", [_feature(0), _feature(1)])
    page = repo.list_page("f1", offset=50, limit=10)
    assert page.items == ()
    assert page.total == 2


@pytest.mark.parametrize("offset,limit", [(-1, 10), (0, 0)])
def test_invalid_paging_arguments_raise(offset, limit):
    repo = InMemoryFeatureResultRepository()
    with pytest.raises(ValueError):
        repo.list_page("f1", offset=offset, limit=limit)