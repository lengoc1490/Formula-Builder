# formula_utils/funcs/registry.py
# Registry of all built-in functions for the formula engine

from typing import Dict, Any

# Import from submodules
from .math import (
    _safe_min, _safe_max, _safe_sum,
    abs, round, roundup, rounddown, floor, ceil,
    power, sqrt, ln, log10, pi, sin, cos, tan,
    asin, acos, atan, atan2, degrees, radians,
    exp, log, len, length, zip, int, float, str, bool,
    safe_div, percent_of, clamp, isnumber, to_number, between,
)

from .text import (
    concat, concatenate, text_join, textjoin, left, right, mid,
    upper, lower, trim, replace, substitute, find, len_text,
)

from .number_to_words import (
    number_to_words,
)


from .date import (
    now, today, year, month, day, date_diff, date_add, date_format,
    quarter, workdays,
)

from .agg import (
    _safe_count, _safe_average, count, countnum, counta,
    sumif, sumifs, countif, countifs, averageif,
    sum_by_type, unique_key_sum_by_type, unique_sum,
    unique, count_unique, flatten, rf
)

from .logic import (
    and_, or_, not_, IF, IIF, IFS, SWITCH,
    coalesce, is_blank, not_blank,
)

from .lookup import (
    vlookup, xlookup, index, match, choose, filter_array,
    last, latest, earliest, first, nth, sorted_array, sort,
    map_key, group_sum, group_by_sum, group_count, group_by_count,
    group_avg, sum_dict,
)

# Import from time_bucket (will be defined in time_bucket.py)
from ..time_bucket import (
    TB_FORMAT,
    generate_time_buckets as _tb_time_buckets,
    in_time_bucket as _tb_in_time_bucket,
    get_bucket_label as _tb_get_bucket_label,
    get_period as _tb_get_period,
    period_offset as _tb_period_offset,
    same_period_last_year as _tb_same_period_last_year,
    year_buckets,
)

# Import from topo
from ..topo import topo_sort_data, topo_sort_flat, scc_topo_sort_data, scc_topo_sort_flat, SccTopoSorter

# Import from scc_linear
from ..scc_linear import solve_linear_on_graph, SccLinearSolver

# Import from allocation
from ..allocation import allocate, AllocTuple, AllocationEngine

# ----------------------------------------------------------------------
# BASE_FUNCS dictionary
# ----------------------------------------------------------------------

BASE_FUNCS: Dict[str, Any] = {
    # Logic
    'and_': and_,
    'or_': or_,
    'not_': not_,

    # Conditionals
    'IF': IF,
    'IIF': IIF,
    'IFS': IFS,
    'SWITCH': SWITCH,

    # Math
    'abs': abs,
    'round': round,
    'roundup': roundup,
    'rounddown': rounddown,
    'floor': floor,
    'ceil': ceil,
    'power': power,
    'sqrt': sqrt,
    'ln': ln,
    'log10': log10,
    'pi': pi,
    'sin': sin,
    'cos': cos,
    'tan': tan,
    'asin': asin,
    'acos': acos,
    'atan': atan,
    'atan2': atan2,
    'degrees': degrees,
    'radians': radians,
    'exp': exp,
    'log': log,
    'min': _safe_min,
    'max': _safe_max,
    'sum': _safe_sum,
    'len': len,
    'length': length,
    'zip': zip,

    # Type conversion
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,

    # Lookup
    'vlookup': vlookup,
    'xlookup': xlookup,

    # Conditional aggregation
    'sumif': sumif,
    'sumifs': sumifs,
    'countif': countif,
    'countifs': countifs,
    'averageif': averageif,

    # Array operations
    'count': _safe_count,
    'countnum': countnum,
    'counta': _safe_count,
    'average': _safe_average,
    'unique': unique,
    'count_unique': count_unique,
    'flatten': flatten,

    # Advanced array operations
    'sum_by_type': sum_by_type,
    'unique_key_sum_by_type': unique_key_sum_by_type,
    'unique_sum': unique_sum,
    'index': index,
    'match': match,
    'filter_array': filter_array,
    'choose': choose,
    'rf': rf,

    # Complex data operations
    'last': last,
    'latest': latest,
    'earliest': earliest,
    'first': first,
    'nth': nth,

    # Text
    'concat': concat,
    'concatenate': concatenate,
    'text_join': text_join,
    'textjoin': textjoin,
    'left': left,
    'right': right,
    'mid': mid,
    'upper': upper,
    'lower': lower,
    'trim': trim,
    'replace': replace,
    'substitute': substitute,
    'find': find,
    'len_text': len_text,
    'number_to_words': number_to_words,

    # Utility
    'coalesce': coalesce,
    'safe_div': safe_div,
    'safe_str': lambda x: str(x or ""),

    # Date/Time
    'now': now,
    'today': today,
    'year': year,
    'month': month,
    'day': day,
    'date_diff': date_diff,

    # v15 functions
    'sorted_array': sorted_array,
    'sort': sort,
    'map_key': map_key,
    'group_sum': group_sum,
    'group_by_sum': group_by_sum,
    'group_count': group_count,
    'group_by_count': group_by_count,
    'group_avg': group_avg,
    'percent_of': percent_of,
    'clamp': clamp,
    'is_blank': is_blank,
    'not_blank': not_blank,
    'isnumber': isnumber,
    'to_number': to_number,
    'between': between,
    'date_add': date_add,
    'date_format': date_format,
    'quarter': quarter,
    'workdays': workdays,
    'sum_dict': sum_dict,

    # Time Bucket v3 (v21)
    'time_buckets': _tb_time_buckets,
    'in_time_bucket': _tb_in_time_bucket,
    'get_bucket_label': _tb_get_bucket_label,
    'get_period': _tb_get_period,
    'period_offset': _tb_period_offset,
    'same_period_last_year': _tb_same_period_last_year,
    'year_buckets': year_buckets,
    'TB_FORMAT': TB_FORMAT,

    # Topo Sort
    'topo_sort_data': topo_sort_data,
    'topo_sort_flat': topo_sort_flat,

    # SCC Topo Sort
    'scc_topo_sort_data': scc_topo_sort_data,
    'scc_topo_sort_flat': scc_topo_sort_flat,

    # SCC Linear Solver
    'solve_linear_on_graph': solve_linear_on_graph,
    'SccLinearSolver': SccLinearSolver,

    # Allocation
    'allocate': allocate,
    'AllocTuple': AllocTuple,
    'AllocationEngine': AllocationEngine,
}