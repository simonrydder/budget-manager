import pendulum

from budget_manager.types import Month


def next_first(date: pendulum.Date) -> pendulum.Date:
    first_this_month = date.start_of("month")
    if date == first_this_month:
        return date
    else:
        return first_this_month.add(months=1)


def month_shifter(month: Month, year: int, shift: int) -> tuple[Month, int]:
    date = pendulum.Date(year, month, 1) + pendulum.Duration(months=shift)

    return (date.month, date.year)


def is_completed_month(month: Month, year: int) -> bool:
    today = pendulum.Date.today()

    first_in_month = today.subtract(days=today.day)

    request_date = pendulum.Date(year, month, 1)

    return request_date < first_in_month


def is_current_month(month: Month, year: int) -> bool:
    today = pendulum.Date.today()

    return month == today.month and year == today.year


def is_date_in_month(date: pendulum.Date, month: Month, year: int | None = None) -> bool:
    year = year or pendulum.Date.today().year
    return date.month == month and date.year == year
