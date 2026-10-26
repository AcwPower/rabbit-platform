from datetime import datetime
from app.schedule import boss_requested_window


def test_upcoming_and_ongoing_window():
    assert boss_requested_window(datetime(2026,10,25,10), '20:00', '02:00') == (
        datetime(2026,10,25,12), datetime(2026,10,25,18))
    assert boss_requested_window(datetime(2026,10,25,13), '20:00', '02:00') == (
        datetime(2026,10,25,13), datetime(2026,10,25,18))


def test_after_midnight_retains_current_window_and_boundary_moves_forward():
    assert boss_requested_window(datetime(2026,10,25,17), '20:00', '02:00') == (
        datetime(2026,10,25,17), datetime(2026,10,25,18))
    assert boss_requested_window(datetime(2026,10,25,18), '20:00', '02:00') == (
        datetime(2026,10,26,12), datetime(2026,10,26,18))


def test_daytime_and_full_day_windows():
    assert boss_requested_window(datetime(2026,10,25,3), '09:00', '12:00') == (
        datetime(2026,10,25,3), datetime(2026,10,25,4))
    assert boss_requested_window(datetime(2026,10,25,3), '09:00', '09:00') == (
        datetime(2026,10,25,3), datetime(2026,10,26,1))
