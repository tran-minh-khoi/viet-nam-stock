from datetime import datetime, timedelta

from api import get_history_window


def test_get_history_window_defaults_to_7_days():
    start_date, end_date = get_history_window()

    assert end_date == datetime.now().strftime('%Y-%m-%d')
    assert start_date == (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
