# formula_utils/funcs/date.py
# Date and time functions for formula engine

from datetime import datetime, date, timezone, timedelta
from typing import Any, Optional
import calendar as _calendar


def now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def today() -> date:
    """Return current date."""
    return date.today()


def year(dt: Any) -> Optional[int]:
    """Extract year from datetime/date."""
    if isinstance(dt, (datetime, date)):
        return dt.year
    return None


def month(dt: Any) -> Optional[int]:
    """Extract month from datetime/date."""
    if isinstance(dt, (datetime, date)):
        return dt.month
    return None


def day(dt: Any) -> Optional[int]:
    """Extract day from datetime/date."""
    if isinstance(dt, (datetime, date)):
        return dt.day
    return None


def quarter(dt: Any) -> Optional[int]:
    """Return quarter (1-4) for given date."""
    def _parse(d: Any):
        if isinstance(d, (datetime, date)):
            return d
        if isinstance(d, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(d.strip(), fmt)
                except ValueError:
                    continue
        return None

    parsed = _parse(dt)
    if parsed is None:
        return None
    return (parsed.month - 1) // 3 + 1


def date_diff(date1: Any, date2: Any, unit: str = 'days') -> Optional[float]:
    """
    Calculate difference between two dates.

    Parameters:
        date1, date2: date/datetime/string
        unit: 'days', 'months', 'years', 'hours', 'seconds'
    Returns:
        difference (positive if date1 > date2)
    """
    def _to_date(d):
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
                        '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(d.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    d1 = _to_date(date1)
    d2 = _to_date(date2)
    if d1 is None or d2 is None:
        return None

    if unit == 'days':
        return (d1 - d2).days
    elif unit == 'months':
        m = (d1.year - d2.year) * 12 + (d1.month - d2.month)
        if d1.day < d2.day:
            m -= 1
        return m
    elif unit == 'years':
        y = d1.year - d2.year
        if (d1.month, d1.day) < (d2.month, d2.day):
            y -= 1
        return y
    elif unit == 'hours':
        # Convert to datetime for time difference
        dt1 = datetime.combine(d1, datetime.min.time())
        dt2 = datetime.combine(d2, datetime.min.time())
        return (dt1 - dt2).total_seconds() / 3600
    elif unit == 'seconds':
        dt1 = datetime.combine(d1, datetime.min.time())
        dt2 = datetime.combine(d2, datetime.min.time())
        return (dt1 - dt2).total_seconds()
    return (d1 - d2).days


def date_add(dt: Any, days: int = 0, months: int = 0, years: int = 0) -> Optional[date]:
    """
    Add days/months/years to a date.

    Parameters:
        dt: date/datetime/string
        days, months, years: offsets (can be negative)
    Returns:
        new date or None if parsing fails
    """
    def _parse(d: Any) -> Optional[date]:
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%Y-%m-%dT%H:%M:%S'):
                try:
                    return datetime.strptime(d.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    d = _parse(dt)
    if d is None:
        return None

    # Add days
    result = d + timedelta(days=days)

    # Add months
    if months != 0:
        total_months = result.month - 1 + months
        new_year = result.year + total_months // 12
        new_month = total_months % 12 + 1
        # Clip to last day of month if necessary
        max_day = _calendar.monthrange(new_year, new_month)[1]
        result = result.replace(year=new_year, month=new_month,
                                day=min(result.day, max_day))

    # Add years
    if years != 0:
        new_year = result.year + years
        max_day = _calendar.monthrange(new_year, result.month)[1]
        result = result.replace(year=new_year, day=min(result.day, max_day))

    return result


def date_format(dt: Any, fmt: str = "%d/%m/%Y") -> str:
    """
    Format date/datetime as string.

    Parameters:
        dt: date/datetime/string
        fmt: strftime format string
    Returns:
        formatted string, or str(dt) on failure
    """
    def _parse(d: Any):
        if isinstance(d, datetime):
            return d
        if isinstance(d, date):
            return datetime(d.year, d.month, d.day)
        if isinstance(d, str):
            for f in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%Y-%m-%dT%H:%M:%S',
                      '%Y-%m-%d %H:%M:%S'):
                try:
                    return datetime.strptime(d.strip(), f)
                except ValueError:
                    continue
        return None

    parsed = _parse(dt)
    if parsed is None:
        return str(dt)
    return parsed.strftime(fmt)


def workdays(date1: Any, date2: Any) -> int:
    """
    Count workdays (Monday-Friday) between two dates (excluding start, including end?).
    Returns positive if date1 > date2, negative otherwise.
    """
    import datetime as _dt

    def _p(d: Any) -> Optional[date]:
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    return datetime.strptime(d.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    d1, d2 = _p(date1), _p(date2)
    if d1 is None or d2 is None:
        return 0

    sign = 1
    if d1 < d2:
        d1, d2 = d2, d1
        sign = -1

    count = 0
    cur = d2 + _dt.timedelta(days=1)
    while cur <= d1:
        if cur.weekday() < 5:   # Monday=0 ... Friday=4
            count += 1
        cur += _dt.timedelta(days=1)
    return sign * count