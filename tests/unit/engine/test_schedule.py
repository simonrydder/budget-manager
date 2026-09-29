from datetime import date

from budget_manager.engine import MonthSchedule, Schedule, YearMonth, frequency_label


def test_monthly_due_dates_keep_the_day_and_clamp_short_months():
    schedule = Schedule(date(2025, 1, 31), 1)
    assert schedule.due_in(YearMonth(2025, 2)) == date(2025, 2, 28)
    assert schedule.due_in(YearMonth(2025, 3)) == date(2025, 3, 31)
    assert schedule.due_in(YearMonth(2024, 12)) is None


def test_quarterly_due_only_every_third_month():
    schedule = Schedule(date(2025, 1, 15), 3)
    due = [m for m in range(1, 13) if schedule.due_in(YearMonth(2025, m))]
    assert due == [1, 4, 7, 10]


def test_next_due_finds_the_next_payment():
    schedule = Schedule(date(2025, 3, 1), 12)
    assert schedule.next_due(YearMonth(2025, 1)) == date(2025, 3, 1)
    assert schedule.next_due(YearMonth(2025, 3)) == date(2025, 3, 1)
    assert schedule.next_due(YearMonth(2025, 4)) == date(2026, 3, 1)


def test_one_off_is_due_once():
    schedule = Schedule(date(2030, 8, 1), 0)
    assert schedule.next_due(YearMonth(2025, 5)) == date(2030, 8, 1)
    assert schedule.due_in(YearMonth(2030, 8)) == date(2030, 8, 1)
    assert schedule.next_due(YearMonth(2030, 9)) is None
    assert schedule.due_in(YearMonth(2031, 8)) is None


def test_end_date_stops_payments():
    schedule = Schedule(date(2025, 1, 10), 1, end_date=date(2025, 6, 30))
    assert schedule.due_in(YearMonth(2025, 6)) == date(2025, 6, 10)
    assert schedule.due_in(YearMonth(2025, 7)) is None
    assert schedule.next_due(YearMonth(2025, 7)) is None


def test_upcoming_lists_due_dates_from_a_day():
    schedule = Schedule(date(2025, 2, 15), 6)
    assert schedule.upcoming(date(2025, 5, 1), 3) == [
        date(2025, 8, 15),
        date(2026, 2, 15),
        date(2026, 8, 15),
    ]
    assert Schedule(date(2025, 2, 15), 0).upcoming(date(2025, 5, 1), 3) == []


def test_next_due_from_skips_dates_earlier_in_the_month():
    rent = Schedule(date(2025, 1, 1), 1)
    assert rent.next_due_from(date(2025, 9, 29)) == date(2025, 10, 1)
    assert rent.next_due_from(date(2025, 10, 1)) == date(2025, 10, 1)
    assert Schedule(date(2025, 9, 1), 0).next_due_from(date(2025, 9, 29)) is None


def test_month_schedule_for_income():
    quarterly = MonthSchedule(YearMonth(2025, 1), 3, end_month=YearMonth(2025, 10))
    assert [m for m in range(1, 13) if quarterly.is_due(YearMonth(2025, m))] == [1, 4, 7, 10]
    assert not quarterly.is_due(YearMonth(2026, 1))
    once = MonthSchedule(YearMonth(2025, 6), 0)
    assert once.is_due(YearMonth(2025, 6))
    assert not once.is_due(YearMonth(2025, 7))


def test_frequency_labels():
    assert frequency_label(0) == "One-off"
    assert frequency_label(12) == "Yearly"
    assert frequency_label(5) == "Every 5 months"
