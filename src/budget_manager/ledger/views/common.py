from __future__ import annotations

from datetime import date

from django.http import Http404

from budget_manager.engine import YearMonth, parse_amount


def parse_month(text: str) -> YearMonth:
    try:
        return YearMonth.parse(text)
    except ValueError as error:
        raise Http404("Unknown month") from error


def today() -> date:
    return date.today()


def read_amounts(post, prefix: str, ids) -> tuple[dict[int, int | None], dict[int, str]]:
    """Read ``{prefix}{id}`` fields. Returns the parsed amounts and error messages per id."""
    values: dict[int, int | None] = {}
    errors: dict[int, str] = {}
    for item_id in ids:
        raw = post.get(f"{prefix}{item_id}", "")
        try:
            values[item_id] = parse_amount(raw)
        except ValueError as error:
            errors[item_id] = str(error)
    return values, errors


def save_entries(model, key: str, month: date, values: dict[int, int | None], user) -> None:
    """Create, update or delete one entry per id for ``month``. ``None`` deletes the entry."""
    for item_id, amount in values.items():
        lookup = {f"{key}_id": item_id, "month": month}
        if amount is None:
            model.objects.filter(**lookup).delete()
        else:
            model.objects.update_or_create(
                **lookup, defaults={"amount": amount, "updated_by": user}
            )
