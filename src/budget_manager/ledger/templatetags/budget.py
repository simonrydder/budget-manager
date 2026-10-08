from __future__ import annotations

from datetime import date, timedelta

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from budget_manager.engine import YearMonth, format_amount, format_input

register = template.Library()


@register.filter
def money(value) -> str:
    """``123456`` → ``1.234,56``."""
    if value is None or value == "":
        return ""
    return format_amount(int(value))


@register.filter
def money0(value) -> str:
    """``123456`` → ``1.235`` (rounded, no decimals)."""
    if value is None or value == "":
        return ""
    return format_amount(int(value), decimals=False)


@register.filter
def money_input(value) -> str:
    return format_input(None if value in (None, "") else int(value))


@register.filter
def absolute(value):
    try:
        return abs(int(value))
    except (TypeError, ValueError):
        return value


@register.filter
def signed(value) -> str:
    """Money with an explicit + for positive amounts."""
    if value is None:
        return ""
    value = int(value)
    return ("+" if value > 0 else "") + format_amount(value)


@register.filter
def signed0(value) -> str:
    """Rounded money with an explicit + for positive amounts."""
    if value is None:
        return ""
    value = int(value)
    return ("+" if value > 0 else "") + format_amount(value, decimals=False)


@register.filter
def tone(value) -> str:
    """CSS class for an amount: ``neg`` below zero."""
    try:
        return "neg" if int(value) < 0 else ""
    except (TypeError, ValueError):
        return ""


@register.filter
def month_label(value) -> str:
    if isinstance(value, YearMonth):
        return value.label
    if isinstance(value, date):
        return YearMonth.of(value).label
    return str(value)


@register.filter
def short_date(value: date | None) -> str:
    if not value:
        return ""
    return f"{value.day} {value:%b} {value.year}"


@register.filter
def times(value, factor):
    """``value`` multiplied by ``factor`` (whole numbers)."""
    try:
        return int(value) * int(factor)
    except (TypeError, ValueError):
        return value


@register.filter
def share_of(value, total) -> int:
    """``value`` as a whole percentage of ``total``."""
    try:
        total = int(total)
        return round(int(value) * 100 / total) if total else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def add_days(value: date | None, days) -> date | None:
    if not value:
        return value
    return value + timedelta(days=int(days))


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.simple_tag(takes_context=True)
def current(context, *prefixes):
    """``aria-current="page"`` when the current URL name starts with one of ``prefixes``."""
    match = getattr(context.get("request"), "resolver_match", None)
    name = getattr(match, "url_name", "") or ""
    if any(name.startswith(prefix) for prefix in prefixes):
        return mark_safe(' aria-current="page"')
    return ""


@register.simple_tag
def band(value, minimum, maximum):
    """A small bar showing where ``value`` lands compared with the NemKonto limits."""
    value, minimum, maximum = int(value), int(minimum), int(maximum)
    top = max(maximum * 1.6, value * 1.1, minimum + 1, 1)
    bottom = min(0, value * 1.1)
    span = top - bottom

    def pos(amount):
        return round((amount - bottom) / span * 100, 2)

    return format_html(
        '<div class="band" role="img" aria-label="NemKonto ends at {} (limits {} to {})">'
        '<span class="band-zone" style="left:{}%;width:{}%"></span>'
        '<span class="band-dot" style="left:{}%"></span></div>',
        format_amount(value),
        format_amount(minimum),
        format_amount(maximum),
        pos(minimum),
        max(pos(maximum) - pos(minimum), 0.8),
        min(max(pos(value), 0), 100),
    )
