import pendulum


def next_first(date: pendulum.Date) -> pendulum.Date:
    first_this_month = date.start_of("month")
    if date == first_this_month:
        return date
    else:
        return first_this_month.add(months=1)
