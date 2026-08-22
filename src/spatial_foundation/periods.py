from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from empirical_contracts import PeriodScheme


@dataclass(frozen=True)
class Period:
    period_id: str
    start_year: int
    end_year: int
    ordinal: int
    start_date: date
    end_date_exclusive: date


class PeriodIndex:
    def __init__(self, scheme: PeriodScheme):
        self.scheme = scheme

    def start_year_for(self, value: date | datetime | int) -> int:
        year = value if isinstance(value, int) else value.year
        width = self.scheme.width_years
        return self.scheme.anchor_year + math.floor((year - self.scheme.anchor_year) / width) * width

    def period_for(self, value: date | datetime | int) -> Period:
        start = self.start_year_for(value)
        width = self.scheme.width_years
        end = start + width - 1
        ordinal = (start - self.scheme.anchor_year) // width
        return Period(
            period_id=f"{start}-{end}",
            start_year=start,
            end_year=end,
            ordinal=ordinal,
            start_date=date(start, 1, 1),
            end_date_exclusive=date(start + width, 1, 1),
        )

    def range(self, start_year: int, end_year: int) -> tuple[Period, ...]:
        if end_year < start_year:
            raise ValueError("end_year must be >= start_year")
        first = self.start_year_for(start_year)
        last = self.start_year_for(end_year)
        return tuple(self.period_for(year) for year in range(first, last + 1, self.scheme.width_years))
