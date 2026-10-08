from __future__ import annotations

from datetime import date

from django.http import Http404
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from budget_manager.engine import YearMonth, parse_amount


def parse_month(text: str) -> YearMonth:
    try:
        return YearMonth.parse(text)
    except ValueError as error:
        raise Http404("Unknown month") from error


def today() -> date:
    return date.today()


def next_value(request) -> str:
    """The ``next`` address to return to, if it points back into this app."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return ""


def safe_next(request, fallback: str) -> str:
    """The ``next`` address if there is one, else ``fallback`` (a URL name)."""
    return next_value(request) or reverse(fallback)


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
