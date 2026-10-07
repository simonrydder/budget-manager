"""Small server-rendered SVG charts, so the app needs no JavaScript chart library."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils.html import escape

from budget_manager.engine import format_amount

COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"]


@dataclass
class TrendCard:
    name: str
    values: list[int]
    labels: list[str]
    color: str
    selected: int | None = None

    @property
    def index(self) -> int:
        return len(self.values) - 1 if self.selected is None else self.selected

    @property
    def value(self) -> int:
        return self.values[self.index]

    @property
    def value_label(self) -> str:
        return self.labels[self.index]

    @property
    def lowest(self) -> int:
        return min(self.values)

    @property
    def lowest_label(self) -> str:
        return self.labels[self.values.index(self.lowest)]

    @property
    def svg(self) -> str:
        return mini_chart(self.values, self.labels, marker=self.selected, color=self.color)


def trend_cards(points, accounts, marker: int | None = None) -> list[TrendCard]:
    """One small chart per account plus General Savings, each on its own scale."""
    labels = [point.month.short_label for point in points]
    cards = [
        TrendCard(
            account.name,
            [point.account_balances[account.id] for point in points],
            labels,
            COLORS[number % len(COLORS)],
            marker,
        )
        for number, account in enumerate(accounts)
    ]
    cards.append(
        TrendCard(
            "General Savings",
            [point.general_savings for point in points],
            labels,
            COLORS[len(accounts) % len(COLORS)],
            marker,
        )
    )
    return cards


def mini_chart(
    values: list[int], labels: list[str], *, marker: int | None = None, color: str = COLORS[0]
) -> str:
    """A small line chart with its own scale, a shaded area and the zero line if in range."""
    width, height, pad, bottom = 300, 74, 3, 14
    low = min(min(values), 0)
    high = max(max(values), 0)
    if high == low:
        high = low + 100
    count = len(values)

    def x(index: int) -> float:
        return pad + (
            index * (width - 2 * pad) / (count - 1) if count > 1 else (width - 2 * pad) / 2
        )

    def y(value: float) -> float:
        return pad + (1 - (value - low) / (high - low)) * (height - pad - bottom)

    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
    base = y(0)
    area = f"{x(0):.1f},{base:.1f} {line} {x(count - 1):.1f},{base:.1f}"
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Trend from '
        f"{escape(format_amount(values[0], decimals=False))} to "
        f'{escape(format_amount(values[-1], decimals=False))}">',
        f'<polygon points="{area}" fill="{color}" fill-opacity="0.13" stroke="none"/>',
        f'<line x1="{pad}" x2="{width - pad}" y1="{base:.1f}" y2="{base:.1f}" '
        f'stroke="var(--line)" stroke-width="1"/>',
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
        'stroke-linejoin="round" stroke-linecap="round"/>',
    ]
    if min(values) < 0:
        parts.append(
            f'<line x1="{pad}" x2="{width - pad}" y1="{base:.1f}" y2="{base:.1f}" '
            'stroke="var(--neg)" stroke-dasharray="3 3" stroke-width="1"/>'
        )
    point = marker if marker is not None and 0 <= marker < count else count - 1
    if marker is not None:
        parts.append(
            f'<line x1="{x(point):.1f}" x2="{x(point):.1f}" y1="{pad}" y2="{height - bottom}" '
            'stroke="var(--muted)" stroke-dasharray="2 3"/>'
        )
    parts.append(
        f'<circle cx="{x(point):.1f}" cy="{y(values[point]):.1f}" r="3.2" fill="{color}"/>'
    )
    parts.append(
        f'<text x="{pad}" y="{height - 2}" class="tick">{escape(labels[0])}</text>'
        f'<text x="{width - pad}" y="{height - 2}" class="tick" text-anchor="end">'
        f"{escape(labels[-1])}</text>"
    )
    parts.append("</svg>")
    return "".join(parts)
