import pytest

from engine import ceiling_floor


@pytest.mark.parametrize(
    "exchange, reference, expected",
    [
        ("HOSE", 11.75, (12.55, 10.95)),   # PDR 2026-11-09, matches the HOSE board
        ("HOSE", 5, (5.35, 4.65)),         # tick 0.01 under 10
        ("HOSE", 20, (21.4, 18.6)),        # tick 0.05 under 50
        ("HOSE", 75, (80.2, 69.8)),        # tick 0.1 from 50
        ("HNX", 20, (22.0, 18.0)),         # ±10%, tick 0.1
        ("UPCOM", 20, (23.0, 17.0)),       # ±15%, tick 0.1
    ],
)
def test_ceiling_floor_by_exchange(exchange, reference, expected):
    assert ceiling_floor(exchange, reference) == expected


@pytest.mark.parametrize("exchange, band", [("HOSE", 0.07), ("HNX", 0.10), ("UPCOM", 0.15)])
@pytest.mark.parametrize("reference", [1, 9.99, 10, 11.75, 33.37, 49.99, 50, 99.99, 100, 250])
def test_ceiling_floor_stay_inside_the_band(exchange, band, reference):
    ceiling, floor = ceiling_floor(exchange, reference)
    assert floor <= reference <= ceiling
    assert ceiling <= reference * (1 + band) + 1e-9
    assert floor >= reference * (1 - band) - 1e-9
