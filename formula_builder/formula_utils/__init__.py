# formula_utils/__init__.py
# Formula Engine v30.0.0
# Public API exports

from .errors import (
    ErrorCode,
    FormulaError,
    SchemaError,
    FormulaBudgetExceeded,
    FormulaComplexityError,
    FormulaLimitError,
    FormulaRuntimeError,
    FormulaValidationError,
    FormulaDeterministicError,
    FormulaAssertionError,
    _error_type_slug,
)

from .types import (
    AuditLevel,
    SnapshotTag,
    SnapshotStatus,
    ExplainStep,
    ExplainResult,
    InputIssue,
    ScenarioComparison,
    Assertion,
    AssertionViolation,
    TraceNode,
    AuditSession,
    AuditReport,
    ImmutableSnapshot,
    EngineMetaBlock,
    EngineContextBlock,
    DagStateBlock,
    TraceEntry,
    ExecutionTraceBlock,
    AuditTrailBlock,
    EnterpriseSnapshot,
    FormulaSetMeta,
    InputField,
    OutputField,
    TopoSortResult,
    SccTopoResult,
    SccLinearAuditEntry,
    SccLinearSolveResult,
    IncrementalStats,
    ValidationResult,
)

from .normalize import (
    normalize_formula,
    match_criteria,
    safe_str,
    hash_formulas,
    hash_dict,
)

from .funcs.registry import BASE_FUNCS
from .funcs.agg import (
    sumif, sumifs, countif, countifs, averageif,
    sum_by_type, unique_key_sum_by_type, unique_sum,
    group_sum, group_count, group_avg, rf
)
from .funcs.math import (
    safe_div, percent_of, clamp, between, to_number, isnumber,
)
from .funcs.text import (
    concat, text_join, left, right, mid, upper, lower, trim,
    replace, substitute, find_text, len_text, textjoin,
)
from .funcs.number_to_words import (
    number_to_words,
)
from .funcs.date import (
    now, today, year, month, day, date_diff, date_add, date_format,
    quarter, workdays,
)
from .funcs.logic import (
    ifs, switch, IF, iif, coalesce, is_blank, not_blank,
)
from .funcs.lookup import (
    vlookup, xlookup, index, match, choose, filter_array, last, first, nth,
    sorted_array, map_key, unique, count_unique, flatten, sum_dict,
)

from .parser import FormulaParser
from .security import SecurityValidator, FormulaValidator
from .topo import (
    DependencyGraph,
    TopoSorter,
    topo_sort,
    topo_sort_with_info,
    scc_topo_sort,
    scc_topo_sort_with_info,
    scc_topo_sort_data,
    scc_topo_sort_flat,
    SccTopoSorter,
)
from .scc_linear import (
    SccLinearSolver,
    solve_linear_on_graph,
)

from .engine_core import (
    FormulaEngineCore,
    IncrementalContext,
    MODE_RAISE,
    MODE_NULL,
    MODE_DEFAULT,
)

from .engine_trace import FormulaEngineTrace
from .engine_audit import FormulaEngineAudit
from .engine_public import FormulaEngine

from .time_bucket import (
    TB_FORMAT,
    generate_time_buckets,
    generate_time_buckets_flat,
    year_buckets,
    get_period,
    get_period_by_date,
    get_period_offset,
    same_period_last_year,
    TimeBucket,
)

from .allocation import (
    AllocationEngine,
    allocate,
    allocate_inplace,
    allocate_fast,
    AllocationLine,
    AllocationResult,
)

from .snapshot import (
    SnapshotRegistry,
    SnapshotManager,
)

# Version — unified across all modules (Phase 2.5)
__version__ = "30.0.0"
__engine_version__ = "30.0.0"
__description__ = (
    "Formula Engine v30.0 — Phase 2: Architecture refactored. "
    "api/formula_builder.py split into _helpers, _engine_cache, _ai_core modules. "
    "Security: filter_expr validated via _validate_filter_expr() (AST sandbox). "
    "AI: system prompt hardcoded + sanitize response. "
    "Performance: engine LRU cache 128 entries. "
    "Rate limit: removed for evaluate/validate, keep only for ai_suggest. "
    "DataSource: BaseDataSourceHandler ABC added. "
    "get_live_context: DB-side filter optimization. "
    "Kế thừa v29.1: all FIX 5-6, 80+ BASE_FUNCS, IncrementalContext, "
    "Enterprise Snapshot, AllocationEngine, SCC Linear Solver."
)

__all__ = [
    # Errors
    "ErrorCode",
    "FormulaError",
    "SchemaError",
    "FormulaBudgetExceeded",
    "FormulaComplexityError",
    "FormulaLimitError",
    "FormulaRuntimeError",
    "FormulaValidationError",
    "FormulaDeterministicError",
    "FormulaAssertionError",
    "_error_type_slug",
    # Enums
    "AuditLevel",
    "SnapshotTag",
    "SnapshotStatus",
    # Dataclasses
    "ExplainStep",
    "ExplainResult",
    "InputIssue",
    "ScenarioComparison",
    "Assertion",
    "AssertionViolation",
    "TraceNode",
    "AuditSession",
    "AuditReport",
    "ImmutableSnapshot",
    "EngineMetaBlock",
    "EngineContextBlock",
    "DagStateBlock",
    "TraceEntry",
    "ExecutionTraceBlock",
    "AuditTrailBlock",
    "EnterpriseSnapshot",
    "FormulaSetMeta",
    "InputField",
    "OutputField",
    "TopoSortResult",
    "SccTopoResult",
    "SccLinearAuditEntry",
    "SccLinearSolveResult",
    "IncrementalStats",
    "ValidationResult",
    "TimeBucket",
    "AllocationLine",
    "AllocationResult",
    # Functions
    "hash_formulas",
    "hash_dict",
    "normalize_formula",
    "match_criteria",
    "safe_str",
    "vlookup",
    "xlookup",
    "sumif",
    "sumifs",
    "countif",
    "countifs",
    "averageif",
    "number_to_words",
    "concat",
    "text_join",
    "left",
    "right",
    "mid",
    "upper",
    "lower",
    "trim",
    "replace",
    "substitute",
    "find_text",
    "len_text",
    "ifs",
    "switch",
    "iif",
    "coalesce",
    "now",
    "today",
    "year",
    "month",
    "day",
    "date_diff",
    "safe_div",
    "sum_by_type",
    "unique_key_sum_by_type",
    "unique_sum",
    "index",
    "filter_array",
    "match",
    "choose",
    "textjoin",
    "last",
    "sorted_array",
    "map_key",
    "group_sum",
    "group_count",
    "group_avg",
    "rf",
    "percent_of",
    "clamp",
    "is_blank",
    "not_blank",
    "isnumber",
    "to_number",
    "between",
    "date_add",
    "date_format",
    "quarter",
    "workdays",
    "first",
    "nth",
    "sum_dict",
    "unique",
    "count_unique",
    "flatten",
    "generate_time_buckets",
    "generate_time_buckets_flat",
    "year_buckets",
    "get_period",
    "get_period_by_date",
    "get_period_offset",
    "same_period_last_year",
    "topo_sort",
    "topo_sort_with_info",
    "scc_topo_sort",
    "scc_topo_sort_with_info",
    "scc_topo_sort_data",
    "scc_topo_sort_flat",
    "solve_linear_on_graph",
    "allocate",
    "allocate_inplace",
    "allocate_fast",
    # Classes
    "DependencyGraph",
    "IncrementalContext",
    "FormulaValidator",
    "FormulaParser",
    "FormulaEngineCore",
    "FormulaEngineTrace",
    "FormulaEngineAudit",
    "FormulaEngine",
    "SnapshotRegistry",
    "SnapshotManager",
    "TopoSorter",
    "SccTopoSorter",
    "AllocationEngine",
    "SccLinearSolver",
    # Constants
    "BASE_FUNCS",
    "TB_FORMAT",
    "MODE_RAISE",
    "MODE_NULL",
    "MODE_DEFAULT",
    # Version
    "__version__",
    "__engine_version__",
    "__description__",
]