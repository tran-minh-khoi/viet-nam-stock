import pytest

from api import calculate_ceiling_floor


@pytest.mark.parametrize(
    "ref_price, expected_ceiling, expected_floor",
    [
        (5, 5.35, 4.65),      # tick 0.01, ref < 10
        (20, 21.4, 18.6),     # tick 0.05, ref < 50
        (75, 80.2, 69.8),     # tick 0.1, ref < 100
        (200, 214.0, 186.0),  # tick 0.5, ref < 500
        (800, 856.0, 744.0),  # tick 1.0, ref >= 500
    ],
)
def test_calculate_ceiling_floor_tick_size_bands(ref_price, expected_ceiling, expected_floor):
    ceiling, floor = calculate_ceiling_floor(ref_price)
    assert ceiling == expected_ceiling
    assert floor == expected_floor


@pytest.mark.parametrize("ref_price", [1, 9.99, 10, 49.99, 50, 99.99, 100, 499.99, 500, 1000])
def test_ceiling_and_floor_stay_within_7_percent_and_bracket_reference(ref_price):
    ceiling, floor = calculate_ceiling_floor(ref_price)
    assert floor <= ref_price <= ceiling
    assert ceiling <= ref_price * 1.07
    assert floor >= ref_price * 0.93
