"""Amounts are integers in hundredths (øre) and are shown as plain numbers like ``1.234,56``."""

from __future__ import annotations

import re

MINUS = chr(0x2212)  # typographic minus sign
NBSP = chr(0xA0)  # non-breaking space, often pasted from bank websites
_DIGITS = re.compile(r"^\d+$")


def format_amount(value: int, *, decimals: bool = True) -> str:
    """Format hundredths as ``1.234,56``. Negative amounts get a real minus sign."""
    sign = MINUS if value < 0 else ""
    value = abs(value)
    if not decimals:
        units = (value + 50) // 100
        return f"{sign}{units:,}".replace(",", ".")
    units, cents = divmod(value, 100)
    return f"{sign}{units:,}".replace(",", ".") + f",{cents:02d}"


def format_input(value: int | None) -> str:
    """Format for a form field. Same as :func:`format_amount` but uses a plain hyphen."""
    if value is None:
        return ""
    return format_amount(value).replace(MINUS, "-")


def parse_amount(text: str | None) -> int | None:
    """Parse an amount typed by a person. Returns hundredths, or ``None`` for an empty field.

    Accepts Danish style (``1.234,56``) and plain numbers (``1234.56``, ``1234``).
    A comma is always the decimal separator. Without a comma, a single dot followed by one or
    two digits is read as a decimal point; otherwise dots are thousands separators.
    """
    if text is None:
        return None
    cleaned = text.strip().replace(" ", "").replace(NBSP, "").replace(MINUS, "-").replace("'", "")
    if not cleaned:
        return None

    sign = 1
    if cleaned[0] in "+-":
        sign = -1 if cleaned[0] == "-" else 1
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("Enter a number, for example 1.234,56")

    if "," in cleaned:
        whole, _, fraction = cleaned.partition(",")
        if "," in fraction:
            raise ValueError("Use only one decimal comma, for example 1.234,56")
        whole = _strip_thousands(whole)
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            whole, fraction = parts
        else:
            whole, fraction = _strip_thousands(cleaned), ""
    else:
        whole, fraction = cleaned, ""

    whole = whole or "0"
    if not _DIGITS.match(whole) or (fraction and not _DIGITS.match(fraction)):
        raise ValueError("Enter a number, for example 1.234,56")
    if len(fraction) > 2:
        raise ValueError("Use at most two decimals")
    return sign * (int(whole) * 100 + int(fraction.ljust(2, "0") or "0"))


def _strip_thousands(text: str) -> str:
    groups = text.split(".")
    if len(groups) > 1 and (not groups[0] or any(len(group) != 3 for group in groups[1:])):
        raise ValueError("Thousands separators must group three digits, for example 1.234,56")
    return "".join(groups)
