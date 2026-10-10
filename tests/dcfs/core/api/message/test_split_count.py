from dcfs.core.api.message import (
    MAX_PARALLEL_RANGE_REQUESTS,
    MIN_PARALLEL_RANGE_REQUESTS,
    PARALLEL_RANGE_TARGET_SIZE,
    MessageApi,
)


def test_small_ranges_use_the_minimum():
    assert MessageApi._parallel_split_count(0) == MIN_PARALLEL_RANGE_REQUESTS
    assert MessageApi._parallel_split_count(1) == MIN_PARALLEL_RANGE_REQUESTS
    assert (
        MessageApi._parallel_split_count(PARALLEL_RANGE_TARGET_SIZE)
        == MIN_PARALLEL_RANGE_REQUESTS
    )


def test_split_count_scales_with_size():
    assert MessageApi._parallel_split_count(6 * PARALLEL_RANGE_TARGET_SIZE) == 6


def test_split_count_is_capped():
    assert (
        MessageApi._parallel_split_count(1024 * PARALLEL_RANGE_TARGET_SIZE)
        == MAX_PARALLEL_RANGE_REQUESTS
    )
