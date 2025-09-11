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
