# formula_utils/time_bucket.py
# Time bucket generation and navigation utilities

from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
import calendar as _calendar


# ============================================================================
# Label format presets
# ============================================================================

TB_FORMAT: Dict[str, str] = {
    # Built-in presets (pass as label_format= parameter)
    "short":       "{type_short}{index}",          # Q1, M3, W12, H1
    "short_year":  "{type_short}{index}-{year}",   # Q1-2025, M3-2025
    "short_year2": "{type_short}{index}-{year2}",  # Q1-25,   M3-25
    "full":        "{type_full} {index} {year}",   # Quarter 1 2025
    "slash_year":  "{type_short}{index}/{year}",   # Q1/2025
    "slash_year2": "{type_short}{index}/{year2}",  # Q1/25
    "padded":      "{type_short}{index02}",        # Q01, M03, W12
    "padded_year": "{type_short}{index02}-{year}", # Q01-2025
    "date_range":  "{from_date} → {to_date}",
}

# Type display tokens per bucket type
_TB_TYPE_SHORT = {'year': 'Y', 'half': 'H', 'quarter': 'Q', 'month': 'M', 'week': 'W'}
_TB_TYPE_FULL = {
    'year': 'Year', 'half': 'Half',
    'quarter': 'Quarter', 'month': 'Month', 'week': 'Week',
}


# ============================================================================
# Helper functions
# ============================================================================

def _tb_apply_format(
    fmt: str,
    *,
    type_key: str,
    index: int,
    year: int,
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Apply a label format string, substituting all tokens."""
    # Resolve preset name → actual format string
    resolved = TB_FORMAT.get(fmt, fmt)
    return (
        resolved
        .replace("{year}", str(year))
        .replace("{year2}", str(year)[-2:])
        .replace("{index}", str(index))
        .replace("{index02}", f"{index:02d}")
        .replace("{type_short}", _TB_TYPE_SHORT.get(type_key, type_key.upper()[0]))
        .replace("{type_full}", _TB_TYPE_FULL.get(type_key, type_key.capitalize()))
        .replace("{from_date}", from_date)
        .replace("{to_date}", to_date)
    )


def _tb_fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _tb_parse(d: Any) -> Optional[date]:
    """Parse ISO string / date / datetime → date. Returns None on failure."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                pass
    return None


def _tb_week_bounds(year: int, week_start: str = "monday") -> List[Tuple[date, date]]:
    """Return list of (start, end) date pairs for all ISO weeks in year."""
    if week_start == "monday":
        jan4 = date(year, 1, 4)
        cur = jan4 - timedelta(days=jan4.weekday())
    else:
        jan1 = date(year, 1, 1)
        offset = (jan1.weekday() + 1) % 7
        cur = jan1 - timedelta(days=offset)
    bounds: List[Tuple[date, date]] = []
    while True:
        w_start = cur
        w_end = cur + timedelta(days=6)
        if w_start.year > year:
            break
        if w_end.year >= year and w_start.year <= year:
            bounds.append((w_start, w_end))
        cur += timedelta(weeks=1)
    return bounds


def _tb_encode_name(type_key: str, index: int, year: int,
                    cross_year_ref: Optional[int] = None) -> str:
    base = f"{_TB_TYPE_SHORT[type_key]}{index}" if type_key != 'year' else f"Y{year}"
    if cross_year_ref is not None and year != cross_year_ref:
        return f"{base}@{year}"
    return base


def _tb_resolve_name(name: str, type_key: str, ref_year: int,
                     week_start: str = "monday") -> Optional["TimeBucket"]:
    if not name:
        return None
    # Split off @year if present
    if "@" in name:
        raw, yr_str = name.rsplit("@", 1)
        try:
            target_year = int(yr_str)
        except ValueError:
            target_year = ref_year
    else:
        raw = name
        target_year = ref_year

    # Parse index from raw like "Q1", "M12", "W53", "Y2025"
    if raw.startswith("Y"):
        return get_period("year", 0, target_year, week_start=week_start)
    prefix = raw[0]
    try:
        idx = int(raw[1:])
    except (ValueError, IndexError):
        return None
    # reverse map prefix → type_key
    _REV = {v: k for k, v in _TB_TYPE_SHORT.items()}
    resolved_type = _REV.get(prefix, type_key)
    return get_period(resolved_type, idx, target_year, week_start=week_start)


# ============================================================================
# TimeBucket dataclass
# ============================================================================

@dataclass
class TimeBucket:
    name: str
    short_label: str
    full_label: str
    type: str
    index: int
    year: int
    from_date: str
    to_date: str
    prev_name: Optional[str] = None   # "Q4@2024" or "Q4" (same year)
    next_name: Optional[str] = None

    @property
    def label(self) -> str:
        """Alias → short_label."""
        return self.short_label

    @property
    def value(self) -> str:
        """Alias → name. HTML select value."""
        return self.name

    @property
    def prev_period(self) -> Optional["TimeBucket"]:
        """Previous period as a full TimeBucket object."""
        if self.prev_name is None:
            return None
        return _tb_resolve_name(self.prev_name, self.type, self.year)

    @property
    def next_period(self) -> Optional["TimeBucket"]:
        """Next period as a full TimeBucket object."""
        if self.next_name is None:
            return None
        return _tb_resolve_name(self.next_name, self.type, self.year)

    def to_dict(self, *, full: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "short_label": self.short_label,
            "full_label": self.full_label,
            "type": self.type,
            "index": self.index,
            "year": self.year,
            "from_date": self.from_date,
            "to_date": self.to_date,
        }
        if full:
            d["prev_name"] = self.prev_name
            d["next_name"] = self.next_name
        return d

    def to_ui(self) -> Dict[str, str]:
        return {
            "value": self.name,
            "label": self.short_label,
            "short_label": self.short_label,
            "full_label": self.full_label,
            "from_date": self.from_date,
            "to_date": self.to_date,
        }

    def to_filter(self) -> Dict[str, str]:
        return {
            "period": self.name,
            "from_date": self.from_date,
            "to_date": self.to_date,
        }

    def to_entry(self) -> Dict[str, Any]:
        return {
            "period": self.name,
            "period_label": self.short_label,
            "period_full": self.full_label,
            "from_date": self.from_date,
            "to_date": self.to_date,
            "year": self.year,
            "index": self.index,
        }

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, TimeBucket):
            return self.name == other.name and self.year == other.year
        if isinstance(other, str):
            return self.name == other or self.short_label == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.name, self.year))

    def __repr__(self) -> str:
        return f"TimeBucket({self.name!r}, {self.from_date} → {self.to_date})"

    def __contains__(self, item: Any) -> bool:
        """Support: '2025-03-15' in bucket"""
        dt = _tb_parse(item)
        if dt is None:
            return False
        fd, td = _tb_parse(self.from_date), _tb_parse(self.to_date)
        return fd is not None and td is not None and fd <= dt <= td


# ============================================================================
# Generator functions
# ============================================================================

def generate_time_buckets(
    year: int,
    types: Optional[List[str]] = None,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
    name_format: Optional[str] = None,
) -> Dict[str, Any]:
    _VALID = {'year', 'half', 'quarter', 'month', 'week'}
    if types is None:
        types = list(_VALID)
    else:
        invalid = set(types) - _VALID
        if invalid:
            raise ValueError(
                f"generate_time_buckets: invalid types {invalid}. Valid: {_VALID}"
            )

    _lbl_fmt = label_format or "short"
    _full_fmt = full_format or "{type_full} {index} {year}"
    _name_fmt = name_format or "short"   # name stays stable by default

    def _make(type_key: str, index: int, fd: date, td: date,
              prev_idx: int, prev_year: int,
              next_idx: int, next_year: int) -> TimeBucket:
        from_iso = _tb_fmt(fd)
        to_iso = _tb_fmt(td)
        name = _tb_apply_format(_name_fmt, type_key=type_key, index=index,
                                 year=year, from_date=from_iso, to_date=to_iso)
        slabel = _tb_apply_format(_lbl_fmt, type_key=type_key, index=index,
                                   year=year, from_date=from_iso, to_date=to_iso)
        flabel = _tb_apply_format(_full_fmt, type_key=type_key, index=index,
                                   year=year, from_date=from_iso, to_date=to_iso)
        # prev/next names — include @year when cross-year
        p_idx_ = prev_idx if type_key != 'year' else 0
        n_idx_ = next_idx if type_key != 'year' else 0
        prev_nm = _tb_encode_name(type_key, p_idx_, prev_year, cross_year_ref=year)
        next_nm = _tb_encode_name(type_key, n_idx_, next_year, cross_year_ref=year)
        # Year bucket: name is always "Y{year}"
        if type_key == 'year':
            name = f"Y{year}"
            slabel = _tb_apply_format(_lbl_fmt, type_key='year', index=year,
                                       year=year, from_date=from_iso, to_date=to_iso)
            flabel = _tb_apply_format(_full_fmt, type_key='year', index=year,
                                       year=year, from_date=from_iso, to_date=to_iso)
            prev_nm = f"Y{year-1}"
            next_nm = f"Y{year+1}"
        return TimeBucket(
            name=name, short_label=slabel, full_label=flabel,
            type=type_key, index=index, year=year,
            from_date=from_iso, to_date=to_iso,
            prev_name=prev_nm, next_name=next_nm,
        )

    result: Dict[str, Any] = {}

    # Year
    if 'year' in types:
        result['year'] = _make(
            'year', year, date(year, 1, 1), date(year, 12, 31),
            year - 1, year - 1, year + 1, year + 1,
        )

    # Half
    if 'half' in types:
        _hdata = [
            (1, date(year, 1, 1), date(year, 6, 30)),
            (2, date(year, 7, 1), date(year, 12, 31)),
        ]
        result['halves'] = [
            _make('half', i, fd, td,
                  prev_idx=i-1 if i>1 else 2, prev_year=year if i>1 else year-1,
                  next_idx=i+1 if i<2 else 1, next_year=year if i<2 else year+1)
            for i, fd, td in _hdata
        ]

    # Quarter
    if 'quarter' in types:
        _qdata = [
            (1, date(year, 1, 1), date(year, 3, 31)),
            (2, date(year, 4, 1), date(year, 6, 30)),
            (3, date(year, 7, 1), date(year, 9, 30)),
            (4, date(year, 10, 1), date(year, 12, 31)),
        ]
        result['quarters'] = [
            _make('quarter', i, fd, td,
                  prev_idx=i-1 if i>1 else 4, prev_year=year if i>1 else year-1,
                  next_idx=i+1 if i<4 else 1, next_year=year if i<4 else year+1)
            for i, fd, td in _qdata
        ]

    # Month
    if 'month' in types:
        result['months'] = [
            _make('month', m,
                  date(year, m, 1),
                  date(year, m, _calendar.monthrange(year, m)[1]),
                  prev_idx=m-1 if m>1 else 12, prev_year=year if m>1 else year-1,
                  next_idx=m+1 if m<12 else 1, next_year=year if m<12 else year+1)
            for m in range(1, 13)
        ]

    # Week
    if 'week' in types:
        bounds = _tb_week_bounds(year, week_start)
        n_weeks = len(bounds)
        prev_yr_weeks = len(_tb_week_bounds(year - 1, week_start))
        weeks: List[TimeBucket] = []
        for w, (ws, we) in enumerate(bounds, start=1):
            pi = w - 1 if w > 1 else prev_yr_weeks
            py = year if w > 1 else year - 1
            ni = w + 1 if w < n_weeks else 1
            ny = year if w < n_weeks else year + 1
            weeks.append(_make('week', w, ws, we,
                               prev_idx=pi, prev_year=py,
                               next_idx=ni, next_year=ny))
        result['weeks'] = weeks

    return result


def generate_time_buckets_flat(
    year: int,
    types: Optional[List[str]] = None,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
    as_dict: bool = False,
    as_ui: bool = False,
    as_filter: bool = False,
    as_entry: bool = False,
) -> List[Any]:
    d = generate_time_buckets(year, types,
                               week_start=week_start,
                               label_format=label_format,
                               full_format=full_format)
    flat: List[TimeBucket] = []
    for key in ['year', 'halves', 'quarters', 'months', 'weeks']:
        val = d.get(key)
        if val is None:
            continue
        flat.extend(val) if isinstance(val, list) else flat.append(val)

    if as_ui:
        return [b.to_ui() for b in flat]
    if as_filter:
        return [b.to_filter() for b in flat]
    if as_entry:
        return [b.to_entry() for b in flat]
    if as_dict:
        return [b.to_dict() for b in flat]
    return flat


def year_buckets(
    year: Optional[int] = None,
    offset: int = 0,
    types: Optional[List[str]] = None,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
) -> Dict[str, Any]:
    base = year if year is not None else date.today().year
    return generate_time_buckets(
        base + offset, types,
        week_start=week_start,
        label_format=label_format,
        full_format=full_format,
    )


def get_period(
    period_type: str,
    index: int,
    year: int,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
) -> Optional[TimeBucket]:
    d = generate_time_buckets(year, types=[period_type],
                               week_start=week_start,
                               label_format=label_format,
                               full_format=full_format)
    _key_map = {'year': 'year', 'half': 'halves', 'quarter': 'quarters',
                'month': 'months', 'week': 'weeks'}
    val = d.get(_key_map.get(period_type, period_type))
    if val is None:
        return None
    if isinstance(val, TimeBucket):
        return val
    for b in val:
        if b.index == index:
            return b
    return None


def get_period_by_date(
    d: Any,
    period_type: str,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
) -> Optional[TimeBucket]:
    dt = _tb_parse(d)
    if dt is None:
        return None
    bkts = generate_time_buckets(dt.year, types=[period_type],
                                  week_start=week_start,
                                  label_format=label_format,
                                  full_format=full_format)
    _key_map = {'year': 'year', 'half': 'halves', 'quarter': 'quarters',
                'month': 'months', 'week': 'weeks'}
    val = bkts.get(_key_map.get(period_type, period_type))
    items = [val] if isinstance(val, TimeBucket) else (val or [])
    for b in items:
        if dt in b:
            return b
    return None


def get_period_offset(
    bucket: Any,
    offset: int,
    *,
    week_start: str = "monday",
    label_format: Optional[str] = None,
    full_format: Optional[str] = None,
) -> Optional[TimeBucket]:
    # Parse input
    if isinstance(bucket, dict):
        b_type = bucket.get('type', '')
        b_index = int(bucket.get('index', 1))
        b_year = int(bucket.get('year', date.today().year))
    elif isinstance(bucket, TimeBucket):
        b_type = bucket.type
        b_index = bucket.index
        b_year = bucket.year
    elif isinstance(bucket, str):
        # Try to resolve from encoded name like "Q1" or "Q4@2024"
        resolved = _tb_resolve_name(bucket, '', date.today().year, week_start)
        if resolved is None:
            return None
        b_type, b_index, b_year = resolved.type, resolved.index, resolved.year
    else:
        return None

    if offset == 0:
        return get_period(b_type, b_index, b_year, week_start=week_start,
                          label_format=label_format, full_format=full_format)

    kw = dict(week_start=week_start, label_format=label_format, full_format=full_format)

    if b_type == 'year':
        return get_period('year', 0, b_year + offset, **kw)

    if b_type == 'week':
        # Walk through actual ISO week sequence
        cur = get_period('week', b_index, b_year, week_start=week_start)
        if cur is None:
            return None
        step = 1 if offset > 0 else -1
        for _ in range(abs(offset)):
            ref_name = cur.next_name if step > 0 else cur.prev_name
            if ref_name is None:
                return None
            nxt = _tb_resolve_name(ref_name, 'week', cur.year, week_start)
            if nxt is None:
                return None
            cur = nxt
        return get_period('week', cur.index, cur.year, **kw)

    # half / quarter / month — arithmetic offset
    _n: Dict[str, int] = {'half': 2, 'quarter': 4, 'month': 12}
    n_per_year = _n[b_type]
    abs_idx = b_year * n_per_year + (b_index - 1) + offset
    new_year = abs_idx // n_per_year
    new_index = (abs_idx % n_per_year) + 1
    return get_period(b_type, new_index, new_year, **kw)


def same_period_last_year(
    bucket: Any,
    years_back: int = 1,
    **kwargs,
) -> Optional[TimeBucket]:
    if isinstance(bucket, TimeBucket):
        b_type = bucket.type
    elif isinstance(bucket, dict):
        b_type = bucket.get('type', '')
    else:
        return None
    _n = {'year': 1, 'half': 2, 'quarter': 4, 'month': 12, 'week': 52}
    periods_back = _n.get(b_type, 1) * years_back
    return get_period_offset(bucket, -periods_back, **kwargs)


# ============================================================================
# Wrappers for BASE_FUNCS (used in funcs/registry.py)
# ============================================================================

def _tb_time_buckets(year: int, bucket_type: str = "all",
                     label_format: Optional[str] = None) -> Any:
    if bucket_type == "all":
        return generate_time_buckets(year, label_format=label_format)
    _MAP = {'quarter': 'quarters', 'month': 'months',
            'week': 'weeks', 'half': 'halves', 'year': 'year'}
    key = _MAP.get(bucket_type, bucket_type)
    d = generate_time_buckets(year, types=[bucket_type], label_format=label_format)
    val = d.get(key)
    if isinstance(val, list):
        return val
    return [val] if val else []


def _tb_in_time_bucket(d: Any, bucket: Any) -> bool:
    dt = _tb_parse(d)
    if dt is None:
        return False
    if isinstance(bucket, TimeBucket):
        return dt in bucket
    if isinstance(bucket, dict):
        fd, td = _tb_parse(bucket.get('from_date')), _tb_parse(bucket.get('to_date'))
        return fd is not None and td is not None and fd <= dt <= td
    return False


def _tb_get_bucket_label(d: Any, bucket_type: str,
                         label_type: str = "short") -> str:
    b = get_period_by_date(d, bucket_type)
    if b is None:
        return ""
    if label_type == "full":
        return b.full_label
    if label_type == "name":
        return b.name
    return b.short_label


def _tb_get_period(period_type: str, index: int, year: int,
                   label_format: Optional[str] = None) -> Optional[Any]:
    return get_period(period_type, index, year, label_format=label_format)


def _tb_period_offset(bucket: Any, offset: int,
                      label_format: Optional[str] = None) -> Optional[Any]:
    return get_period_offset(bucket, offset, label_format=label_format)


def _tb_same_period_last_year(bucket: Any, years_back: int = 1) -> Optional[Any]:
    return same_period_last_year(bucket, years_back)

def year_buckets(
    year:         Optional[int] = None,
    offset:       int           = 0,
    types:        Optional[List[str]] = None,
    *,
    week_start:   str  = "monday",
    label_format: Optional[str] = None,
    full_format:  Optional[str] = None,
) -> Dict[str, Any]:
    base = year if year is not None else date.today().year
    return generate_time_buckets(
        base + offset, types,
        week_start=week_start,
        label_format=label_format,
        full_format=full_format,
    )


time_buckets = _tb_time_buckets
in_time_bucket = _tb_in_time_bucket
get_bucket_label = _tb_get_bucket_label
get_period = _tb_get_period
period_offset = _tb_period_offset
same_period_last_year = _tb_same_period_last_year
