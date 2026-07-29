# formula_utils/engine_core.py
# Core formula engine with dependency resolution, incremental evaluation, and budgeting

import ast
import hashlib
import json
import marshal
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union, Iterable

from .errors import FormulaError, ErrorCode, FormulaBudgetExceeded, FormulaComplexityError
from .types import (
    FormulaSetMeta, InputField, OutputField, IncrementalStats, Assertion, AuditLevel,
    ValidationResult
)
from .normalize import hash_formulas
from .parser import FormulaParser
from .security import FormulaValidator
from .topo import DependencyGraph


# ----------------------------------------------------------------------
# Mode constants
# ----------------------------------------------------------------------

MODE_RAISE = 1
MODE_NULL = 2
MODE_DEFAULT = 3


# ----------------------------------------------------------------------
# Sentinel for missing values
# ----------------------------------------------------------------------

_SENTINEL = object()


# ----------------------------------------------------------------------
# IncrementalContext
# ----------------------------------------------------------------------

class IncrementalContext:
    __slots__ = (
        "_engine_hash",     # hash của formula set → detect stale context
        "_inputs",          # inputs hiện tại (snapshot)
        "_outputs",         # outputs hiện tại (kết quả tính)
        "_ctx",             # full context (inputs + outputs + funcs) cho eval
        "_dirty",           # set of node names đang cần tính lại
        "_initialized",     # đã chạy calculate đầy đủ lần đầu chưa
        "_created_at",      # timestamp tạo context
        "_last_updated_at", # timestamp cập nhật gần nhất
        "_doc_id",          # optional: ID document để trace
    )

    def __init__(
        self,
        engine_hash: str,
        base_ctx: Dict[str, Any],   # giữ param cho tương thích, không dùng nữa
        doc_id: Optional[str] = None,
    ):
        self._engine_hash = engine_hash
        self._inputs: Dict[str, Any] = {}
        self._outputs: Dict[str, Any] = {}
        self._ctx: Dict[str, Any] = {}
        self._dirty: Set[str] = set()
        self._initialized: bool = False
        self._created_at: str = datetime.now(timezone.utc).isoformat()
        self._last_updated_at: str = self._created_at
        self._doc_id: Optional[str] = doc_id

    # ------------------------------------------------------------------
    # Serialization — lưu/restore từ Frappe cache / Redis
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """Serialize để lưu vào Frappe cache hoặc DB"""
        return {
            "engine_hash": self._engine_hash,
            "inputs": dict(self._inputs),
            "outputs": dict(self._outputs),
            "dirty": list(self._dirty),
            "initialized": self._initialized,
            "created_at": self._created_at,
            "last_updated_at": self._last_updated_at,
            "doc_id": self._doc_id,
        }

    @classmethod
    def from_dict(cls, engine: "FormulaEngineCore", data: Dict[str, Any]) -> "IncrementalContext":
        """Restore từ serialized dict. Raise nếu formula set đã thay đổi."""
        stored_hash = data.get("engine_hash", "")
        if stored_hash != engine._hash:
            raise FormulaError(
                f"Stale IncrementalContext: formula set đã thay đổi "
                f"(stored={stored_hash[:8]}…, current={engine._hash[:8]}…). "
                f"Hãy tạo context mới.",
                code=ErrorCode.STALE_CONTEXT,
            )
        ctx = cls(engine._hash, {}, doc_id=data.get("doc_id"))
        ctx._inputs = dict(data.get("inputs", {}))
        ctx._outputs = dict(data.get("outputs", {}))
        ctx._dirty = set(data.get("dirty", []))
        ctx._initialized = data.get("initialized", False)
        ctx._created_at = data.get("created_at", ctx._created_at)
        ctx._last_updated_at = data.get("last_updated_at", ctx._created_at)
        # Rebuild _ctx từ inputs + outputs (không cần base funcs)
        ctx._ctx.update(ctx._inputs)
        ctx._ctx.update(ctx._outputs)
        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _apply_inputs(self, inputs: Dict[str, Any]) -> Set[str]:
        changed: Set[str] = set()
        for k, v in inputs.items():
            old = self._inputs.get(k, _SENTINEL)
            try:
                is_same = (old is not _SENTINEL) and (old == v)
            except TypeError:
                is_same = False
            if not is_same:
                changed.add(k)
                self._inputs[k] = v
                self._ctx[k] = v
        return changed

    def _write_output(self, name: str, value: Any):
        self._outputs[name] = value
        self._ctx[name] = value

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def doc_id(self) -> Optional[str]:
        return self._doc_id

    @property
    def outputs(self) -> Dict[str, Any]:
        return dict(self._outputs)

    @property
    def inputs(self) -> Dict[str, Any]:
        return dict(self._inputs)

    def patch(self, field: str, value: Any) -> None:
        self._inputs[field] = value
        self._ctx[field] = value


# ----------------------------------------------------------------------
# FormulaEngineCore
# ----------------------------------------------------------------------

class FormulaEngineCore:
    ENGINE_VERSION = "31.0.0"  # unified v31 (MultiTableFormulaBuilder, composite sources, transform layer)

    def __init__(
        self,
        formulas: List[Dict[str, str]],
        *,
        safe_funcs: Optional[Dict] = None,
        on_error: str = "default",
        default_value: Any = 0,
        meta: Optional[FormulaSetMeta] = None,
        input_fields: Optional[List[InputField]] = None,
        output_fields: Optional[List[OutputField]] = None,
        assertions: Optional[List[Dict[str, Any]]] = None,
        max_iterable_size: Optional[int] = None,
        max_subscript_depth: int = 5,
        rounding_policy: Optional[Dict[str, Dict]] = None,
        strict: bool = True,
        validate_on_init: bool = False,
        # v16: Optional guards
        max_operations: Optional[int] = None,
        max_formula_count: Optional[int] = None,
        max_dependency_depth: Optional[int] = None,
        deterministic: bool = True,
    ):
        # Basic setup
        self._formulas = formulas
        self._meta = meta
        self._hash = hash_formulas(formulas)
        self._strict = strict

        # v16: Operation Budget
        self.max_operations = max_operations
        self._tl = threading.local()

        # v16: Complexity & Deterministic params
        self.max_formula_count = max_formula_count
        self.max_dependency_depth = max_dependency_depth
        self.deterministic = deterministic

        # Error handling mode
        if on_error == "raise":
            self._mode = MODE_RAISE
        elif on_error == "null":
            self._mode = MODE_NULL
        elif on_error == "default":
            self._mode = MODE_DEFAULT
        else:
            raise ValueError("on_error must be one of 'raise', 'null', 'default'")

        self._default = default_value
        self._last_errors: Dict[str, str] = {}

        # Import BASE_FUNCS here to avoid circular import
        from .funcs.registry import BASE_FUNCS

        base = BASE_FUNCS.copy()
        if safe_funcs:
            base.update(safe_funcs)
        self._runtime_env = base

        _is_deterministic = self.deterministic or bool(self._meta and self._meta.frozen)
        if _is_deterministic:
            self._runtime_env.pop("now", None)
            self._runtime_env.pop("today", None)
            # Make set operations deterministic
            self._runtime_env["unique"] = lambda it: sorted(set(it), key=str)
            self._runtime_env["count_unique"] = lambda iterable: len(set(iterable))

        self._max_iterable_size = max_iterable_size  # None = không giới hạn
        _effective_iter_size = max_iterable_size if max_iterable_size is not None else 2 ** 31
        self._max_subscript_depth = max_subscript_depth

        # Parser
        self._parser = FormulaParser(self._runtime_env, max_subscript_depth, _effective_iter_size)

        # Parse all formulas (v31: bytecode cache + regex dep detection)
        self._original_expr = {f["name"]: f["formula"] for f in formulas}
        self._ast_map = {}
        self._compiled = {}

        for f in formulas:
            name = f["name"]
            # Sử dụng parse_with_cache — cache hit trả về compiled bytecode ngay,
            # cache miss thì parse + compile rồi lưu vào cache
            self._compiled[name] = self._parser.parse_with_cache(
                f["formula"], f"<formula:{name}>"
            )

        # Build dependency graph (v31: regex-based fast path, no AST needed)
        self._graph = DependencyGraph()
        self._graph.build_from_exprs(self._original_expr)
        self._topo_order = self._graph.topological_sort()

        # v16: Complexity Guard
        self._validate_complexity()

        # Cache dependencies for fast lookup
        self._deps_cache = self._graph.reverse_graph  # name → parents
        self._reverse_deps = self._graph.graph        # name → children

        formula_name_set = set(self._topo_order)
        self._input_edges: Dict[str, Set[str]] = defaultdict(set)
        # Build input edges from formula text (regex, consistent with build_from_exprs)
        # _ast_map may be empty when using parse_with_cache — use original expressions instead
        import re as _re
        _id_re = _re.compile(r'[a-zA-Z_]\w*')
        _str_re = _re.compile(r"""(?:"[^"]*"|'[^']*')""")
        _attr_re = _re.compile(r'\.[a-zA-Z_]\w*')
        for fname, expr in self._original_expr.items():
            clean = _str_re.sub('""', expr)
            clean = _attr_re.sub('', clean)
            used_names = set(_id_re.findall(clean))
            for var in used_names:
                if var not in formula_name_set:
                    self._input_edges[var].add(fname)

        # Schema
        self._input_schema = {f.name: f for f in (input_fields or [])}
        self._output_schema = {f.name: f for f in (output_fields or [])}

        # Buckets and groups
        self._buckets = {}
        for f in formulas:
            bucket = f.get("bucket", "")
            if bucket:
                self._buckets[f["name"]] = bucket
        for name, out in self._output_schema.items():
            if out.bucket:
                self._buckets[name] = out.bucket

        self._groups = defaultdict(list)
        for f in formulas:
            group = f.get("group", "")
            self._groups[group].append(f["name"])

        # Assertions
        self._assertions: Dict[str, Assertion] = {}
        if assertions:
            for a in assertions:
                self.add_assertion(Assertion(
                    name=a.get("name", f"assert_{len(self._assertions) + 1}"),
                    expr=a["expr"],
                    message=a["message"],
                    severity=AuditLevel(a.get("severity", "ERROR")),
                    depends_on=a.get("depends_on"),
                ))

        # Base context
        self._base_ctx = dict(self._runtime_env)
        self._rounding_policy = rounding_policy

        self._eval_globals: Dict[str, Any] = dict(self._runtime_env)
        self._eval_globals["__builtins__"] = {}
        if _is_deterministic:
            self._eval_globals.pop("now", None)
            self._eval_globals.pop("today", None)

        # v14: validate toàn bộ formulas ngay khi khởi tạo (opt-in)
        self._validate_on_init = validate_on_init
        if validate_on_init:
            _validator = FormulaValidator(self._runtime_env.keys())
            _formula_names = set(self._topo_order)
            _input_names = set(self._input_schema.keys())
            _errors_found = []
            for f in formulas:
                _scope = _input_names | (_formula_names - {f["name"]})
                _r = _validator.validate(f["formula"], known_names=_scope if _scope else None)
                if not _r.ok:
                    _errors_found.append(f"[{f['name']}] {'; '.join(_r.errors)}")
            if _errors_found:
                from .errors import FormulaValidationError
                raise FormulaValidationError(
                    "Formula validation failed on init:\n" + "\n".join(_errors_found),
                    errors=_errors_found,
                )

    # ------------------------------------------------------------------
    # v16: Complexity Guard
    # ------------------------------------------------------------------

    def _validate_complexity(self) -> None:
        if self.max_formula_count is not None:
            n = len(self._formulas)
            if n > self.max_formula_count:
                raise FormulaComplexityError(
                    f"Too many formulas: {n} exceeds limit of {self.max_formula_count}. "
                    f"Consider splitting into multiple engines.",
                    metric="formula_count", value=n, limit=self.max_formula_count,
                )
        if self.max_dependency_depth is not None:
            depth = self._graph.max_depth()
            if depth > self.max_dependency_depth:
                raise FormulaComplexityError(
                    f"Dependency depth {depth} exceeds limit of {self.max_dependency_depth}. "
                    f"Flatten formula dependencies or increase max_dependency_depth.",
                    metric="depth", value=depth, limit=self.max_dependency_depth,
                )

    # ------------------------------------------------------------------
    # v16: Operation Budget
    # ------------------------------------------------------------------

    def _consume_op(self, cost: int = 1) -> None:
        if self.max_operations is None:
            return
        self._tl.__dict__.setdefault('_op_counter', 0)
        self._tl._op_counter += cost
        if self._tl._op_counter > self.max_operations:
            raise FormulaBudgetExceeded(
                f"Operation budget exceeded after {self._tl._op_counter} ops.",
                ops=self._tl._op_counter,
                limit=self.max_operations,
            )

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_metadata(self) -> Dict[str, Any]:
        _mode_map = {1: "raise", 2: "null", 3: "default"}
        meta_dict = None
        if self._meta:
            try:
                meta_dict = {
                    "id": getattr(self._meta, "id", None),
                    "name": getattr(self._meta, "name", None),
                    "version": getattr(self._meta, "version", None),
                    "description": getattr(self._meta, "description", None),
                    "frozen": getattr(self._meta, "frozen", False),
                }
            except AttributeError:
                meta_dict = str(self._meta)

        return {
            "engine_version": self.ENGINE_VERSION,
            "formula_count": len(self._formulas),
            "formula_names": sorted(self._original_expr.keys()),
            "input_fields": sorted(self._input_schema.keys()),
            "output_fields": sorted(self._output_schema.keys()),
            "topo_order": list(self._topo_order),
            "dag_depth": self._graph.max_depth(),
            "formula_hash": self._hash,
            "budget": self.max_operations,
            "max_formula_count": self.max_formula_count,
            "max_dependency_depth": self.max_dependency_depth,
            "max_iterable_size": self._max_iterable_size,
            "deterministic": self.deterministic,
            "on_error": _mode_map.get(self._mode, "default"),
            "groups": {k: list(v) for k, v in self._groups.items()},
            "meta": meta_dict,
        }

    # ── Engine Serialization (v31) ──────────────────────────────────────────

    def to_cache_bytes(self) -> bytes:
        """Serialize engine to bytes for fast restore.

        Marshals: formula names, original expressions, topo order,
        compiled bytecode, and dependency info into a single bytes blob.
        Restore with from_cache_bytes().

        Returns:
            bytes — packed engine state (marshal format)
        """
        payload = {
            "v": 2,
            "engine_version": self.ENGINE_VERSION,
            "names": list(self._original_expr.keys()),
            "exprs": {k: v for k, v in self._original_expr.items()},
            "topo": self._topo_order,
            "deps": {k: list(v) for k, v in self._deps_cache.items()},
            "bytecodes": {k: marshal.dumps(self._compiled[k]) for k in self._topo_order},
            # Store only serializable config, not runtime objects
            "mode": self._mode,
            "default": self._default,
            "strict": self._strict,
            "max_subscript_depth": self._max_subscript_depth,
            "rounding_policy": self._rounding_policy,
            "max_operations": self.max_operations,
            "deterministic": self.deterministic,
        }
        return marshal.dumps(payload)

    @classmethod
    def from_cache_bytes(
        cls,
        data: bytes,
        safe_funcs: Optional[Dict] = None,
        **overrides,
    ) -> "FormulaEngineCore":
        """Restore engine from serialized bytes.

        Args:
            data: bytes from to_cache_bytes()
            safe_funcs: runtime functions (cannot be serialized, must re-provide)
            **overrides: override any stored config (e.g. on_error, deterministic)

        Returns:
            FormulaEngineCore instance — ready to calculate()
        """
        payload = marshal.loads(data)

        if payload.get("v") != 2:
            raise ValueError(f"Unsupported cache version: {payload.get('v')}")

        # Create instance bypassing __init__ — we set everything manually
        obj = cls.__new__(cls)

        # Restore basic state
        obj._original_expr = payload["exprs"]
        obj._topo_order = payload["topo"]
        obj._hash = hash_formulas([
            {"name": k, "formula": v} for k, v in obj._original_expr.items()
        ])

        # Restore compiled bytecode
        obj._compiled = {}
        obj._ast_map = {}  # Empty — not needed for eval, only for explain/topo rebuild
        for name in obj._topo_order:
            obj._compiled[name] = marshal.loads(payload["bytecodes"][name])

        # Restore dependency cache
        obj._deps_cache = {
            k: set(v) for k, v in payload.get("deps", {}).items()
        }

        # Rebuild _input_edges from expressions (consistent with __init__)
        formula_name_set = set(obj._topo_order)
        obj._input_edges = defaultdict(set)
        import re as _re
        _id_re = _re.compile(r'[a-zA-Z_]\w*')
        _str_re = _re.compile(r"""(?:"[^"]*"|'[^']*')""")
        _attr_re = _re.compile(r'\.[a-zA-Z_]\w*')
        for fname, expr in obj._original_expr.items():
            clean = _str_re.sub('""', expr)
            clean = _attr_re.sub('', clean)
            used_names = set(_id_re.findall(clean))
            for var in used_names:
                if var not in formula_name_set:
                    obj._input_edges[var].add(fname)

        # Restore config
        obj._mode = payload.get("mode", MODE_DEFAULT)
        obj._default = payload.get("default", 0)
        obj._strict = payload.get("strict", True)
        obj._max_subscript_depth = payload.get("max_subscript_depth", 5)
        obj._rounding_policy = payload.get("rounding_policy")
        obj.max_operations = payload.get("max_operations")
        obj.deterministic = payload.get("deterministic", True)
        obj._input_schema = {}
        obj._output_schema = {}

        # Apply overrides
        for k, v in overrides.items():
            if k == "on_error":
                if v == "raise":
                    obj._mode = MODE_RAISE
                elif v == "null":
                    obj._mode = MODE_NULL
                else:
                    obj._mode = MODE_DEFAULT
            elif k == "deterministic":
                obj.deterministic = v
            elif k == "default_value":
                obj._default = v

        # Set up runtime env (cannot be serialized — contains callables)
        from .funcs.registry import BASE_FUNCS
        base = BASE_FUNCS.copy()
        if safe_funcs:
            base.update(safe_funcs)
        obj._runtime_env = base

        # Determine if deterministic
        _is_deterministic = obj.deterministic
        if _is_deterministic:
            obj._runtime_env.pop("now", None)
            obj._runtime_env.pop("today", None)
            obj._runtime_env["unique"] = lambda it: sorted(set(it), key=str)
            obj._runtime_env["count_unique"] = lambda iterable: len(set(iterable))

        # Misc
        obj._formulas = []
        obj._meta = None
        obj._tl = threading.local()
        obj.max_formula_count = None
        obj.max_dependency_depth = None
        obj._max_iterable_size = None
        obj._assertions = {}
        obj._groups = {}
        obj._last_errors = {}
        obj._graph = None  # Not serialized; rebuild if needed
        obj._parser = None  # Not serialized; created lazily if needed
        obj._eval_globals = {
            "__builtins__": {k: v for k, v in obj._runtime_env.items()},
        }

        return obj

    @property
    def last_errors(self) -> Dict[str, str]:
        """Trả về dict {formula_name: error_message} của lần calculate gần nhất."""
        return self._last_errors.copy()
    
    def add_assertion(self, assertion: Assertion):
        """Add runtime assertion"""
        tree = ast.parse(assertion.expr, mode="eval")
        from .parser import IfCallRewriter
        tree = IfCallRewriter().visit(tree)
        ast.fix_missing_locations(tree)
        from .security import SecurityValidator
        SecurityValidator(self._max_subscript_depth, self._max_iterable_size).visit(tree)
        assertion._compiled = compile(tree, f"<assertion:{assertion.name}>", "eval")
        self._assertions[assertion.name] = assertion

    def _make_validator(self) -> "FormulaValidator":
        return FormulaValidator(self._runtime_env.keys())

    def validate_formula(
        self,
        formula: str,
        known_names: Optional[Set[str]] = None,
    ) -> ValidationResult:
        validator = self._make_validator()
        scope: Optional[Set[str]] = None
        if known_names is not None:
            scope = set(known_names) | set(self._topo_order)
        elif self._topo_order:
            scope = set(self._topo_order)
        return validator.validate(formula, known_names=scope)

    def validate_all(
        self,
        known_names: Optional[Set[str]] = None,
    ) -> Dict[str, ValidationResult]:
        formulas_dict = {name: self._original_expr[name] for name in self._topo_order}
        scope: Optional[Set[str]] = None
        if known_names is not None:
            scope = set(known_names)
        validator = self._make_validator()
        return validator.validate_batch(formulas_dict, known_names=scope)

    def register_formula(
        self,
        name: str,
        formula: str,
        *,
        known_names: Optional[Set[str]] = None,
        validate: bool = True,
    ) -> ValidationResult:
        result = ValidationResult(ok=True, errors=[], warnings=[], normalized=formula, formula=formula)

        if validate:
            result = self.validate_formula(formula, known_names=known_names)
            result.raise_if_invalid(field_name=name)

        tree = self._parser.parse(formula)
        compiled = self._parser.compile(tree, f"<formula:{name}>")

        self._formulas = [f for f in self._formulas if f["name"] != name]
        self._formulas.append({"name": name, "formula": formula})
        self._original_expr[name] = formula
        self._ast_map[name] = tree
        self._compiled[name] = compiled
        self._hash = hash_formulas(self._formulas)

        # Rebuild DAG
        self._graph = DependencyGraph()
        self._graph.build(self._ast_map)
        self._topo_order = self._graph.topological_sort()
        self._deps_cache = self._graph.reverse_graph
        self._reverse_deps = self._graph.graph

        formula_name_set = set(self._topo_order)
        self._input_edges = defaultdict(set)
        for fname, ftree in self._ast_map.items():
            used = {n.id for n in ast.walk(ftree) if isinstance(n, ast.Name)}
            for var in used:
                if var not in formula_name_set:
                    self._input_edges[var].add(fname)

        return result

    def calculate(self, inputs: Dict[str, Any], strict: Optional[bool] = None) -> Dict[str, Any]:
        if self._input_schema:
            use_strict = strict if strict is not None else self._strict
            defaults = {
                name: f.default
                for name, f in self._input_schema.items()
                if not f.required and f.default is not None and name not in inputs
            }
            if defaults:
                inputs = {**defaults, **inputs}
            if use_strict:
                for name, fld in self._input_schema.items():
                    if fld.required and name not in inputs:
                        raise FormulaError(f'Missing required input: {name}', code=ErrorCode.MISSING_REQUIRED_INPUT)
        local = inputs.copy()
        _compiled = self._compiled
        _eval_globals = self._eval_globals
        _topo = self._topo_order
        _mode = self._mode
        _default = self._default
        if self.max_operations is not None:
            self._tl._op_counter = 0
        _consume = self._consume_op
        _original = self._original_expr
        _max_ops = self.max_operations

        self._last_errors = {}
        for name in _topo:
            if _max_ops is not None:
                _consume()
            try:
                local[name] = eval(_compiled[name], _eval_globals, local)
            except FormulaBudgetExceeded:
                raise
            except Exception as e:
                error_msg = str(e)
                self._last_errors[name] = error_msg

                if _mode == MODE_DEFAULT:
                    local[name] = _default
                elif _mode == MODE_NULL:
                    local[name] = None
                else:  # MODE_RAISE
                    raise FormulaError(
                        f'Evaluation failed for {repr(name)}',
                        field_name=name, formula=_original.get(name),
                        error=e, context=local, code=ErrorCode.INVALID_TYPE) from e
        if self._rounding_policy:
            for fld, policy in self._rounding_policy.items():
                if fld in local:
                    local[fld] = round(local[fld], policy.get('decimals', 0))
        return {name: local[name] for name in _topo}

    def calculate_batch(
        self,
        rows: Iterable[Dict[str, Any]],
        strict: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        return [self.calculate(row, strict=strict) for row in rows]

    def calculate_batch_with_memory(
        self,
        rows: Iterable[Dict[str, Any]],
        memory_keys: List[str] = None,
        initial_memory: Optional[Dict[str, Any]] = None,
        strict: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        if memory_keys is None:
            memory_keys = []

        memory = initial_memory or {}
        results = []

        for row_index, row in enumerate(rows):
            ctx_inputs = row.copy()
            for key in memory_keys:
                ctx_inputs[f"prev_{key}"] = memory.get(key, 0)

            res = self.calculate(ctx_inputs, strict=strict)

            for key in memory_keys:
                if key in res:
                    memory[key] = res[key]

            res['row_index'] = row_index
            results.append(res)

        return results

    async def calculate_async(self, inputs: Dict[str, Any], strict: Optional[bool] = None) -> Dict[str, Any]:
        import asyncio
        return await asyncio.to_thread(self.calculate, inputs, strict)

    # ------------------------------------------------------------------
    # Incremental evaluation
    # ------------------------------------------------------------------

    def create_context(
        self,
        initial_inputs: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
        strict: Optional[bool] = None,
    ) -> IncrementalContext:
        ictx = IncrementalContext(self._hash, self._base_ctx, doc_id=doc_id)
        inputs = initial_inputs or {}

        if self._input_schema:
            defaults = {
                name: f.default
                for name, f in self._input_schema.items()
                if not f.required and f.default is not None and name not in inputs
            }
            if defaults:
                inputs = {**defaults, **inputs}

        use_strict = strict if strict is not None else self._strict
        if use_strict:
            for name, fld in self._input_schema.items():
                if fld.required and name not in inputs:
                    raise FormulaError(
                        f"Missing required input: {name}",
                        code=ErrorCode.MISSING_REQUIRED_INPUT,
                    )

        ictx._apply_inputs(inputs)

        self._tl._op_counter = 0

        for name in self._topo_order:
            try:
                self._consume_op()
                val = eval(self._compiled[name], self._eval_globals, ictx._ctx)
            except FormulaBudgetExceeded:
                raise
            except Exception as e:
                if self._mode == MODE_RAISE:
                    raise FormulaError(
                        f"Evaluation failed for '{name}'",
                        field_name=name,
                        formula=self._original_expr.get(name),
                        error=e,
                        context=ictx._ctx,
                        code=ErrorCode.INVALID_TYPE,
                    ) from e
                val = None if self._mode == MODE_NULL else self._default
            ictx._write_output(name, val)

        if self._rounding_policy:
            for fld, policy in self._rounding_policy.items():
                if fld in ictx._outputs:
                    decimals = policy.get("decimals", 0)
                    ictx._write_output(fld, round(ictx._outputs[fld], decimals))

        ictx._initialized = True
        ictx._last_updated_at = datetime.now(timezone.utc).isoformat()
        return ictx

    def calculate_incremental(
        self,
        ictx: IncrementalContext,
        changed_inputs: Dict[str, Any],
        strict: Optional[bool] = None,
        return_stats: bool = False,
    ) -> Union[Dict[str, Any], Tuple[Dict[str, Any], IncrementalStats]]:
        t0 = time.perf_counter()

        if not ictx._initialized:
            raise FormulaError(
                "IncrementalContext chưa được khởi tạo. Hãy gọi create_context() trước.",
                code=ErrorCode.CONTEXT_NOT_INITIALIZED,
            )
        if ictx._engine_hash != self._hash:
            raise FormulaError(
                "Stale IncrementalContext: formula set đã thay đổi. Tạo context mới.",
                code=ErrorCode.STALE_CONTEXT,
            )

        stats = IncrementalStats(total_nodes=len(self._topo_order))

        actually_changed = ictx._apply_inputs(changed_inputs)
        stats.changed_inputs = len(actually_changed)

        if not actually_changed:
            stats.skipped_nodes = stats.total_nodes
            stats.elapsed_ms = (time.perf_counter() - t0) * 1000
            result = dict(ictx._outputs)
            return (result, stats) if return_stats else result

        affected_formulas: Set[str] = self.get_affected_nodes(actually_changed)
        stats.affected_nodes = len(affected_formulas)

        recalc_count = 0
        skip_count = 0

        self._tl._op_counter = 0

        for name in self._topo_order:
            if name not in affected_formulas:
                skip_count += 1
                continue

            recalc_count += 1
            try:
                self._consume_op()
                val = eval(self._compiled[name], self._eval_globals, ictx._ctx)
            except FormulaBudgetExceeded:
                raise
            except Exception as e:
                if self._mode == MODE_RAISE:
                    raise FormulaError(
                        f"Evaluation failed for '{name}'",
                        field_name=name,
                        formula=self._original_expr.get(name),
                        error=e,
                        context=ictx._ctx,
                        code=ErrorCode.INVALID_TYPE,
                    ) from e
                val = None if self._mode == MODE_NULL else self._default
            ictx._write_output(name, val)

        if self._rounding_policy:
            for fld, policy in self._rounding_policy.items():
                if fld in affected_formulas and fld in ictx._outputs:
                    decimals = policy.get("decimals", 0)
                    ictx._write_output(fld, round(ictx._outputs[fld], decimals))

        stats.recalculated_nodes = recalc_count
        stats.skipped_nodes = skip_count
        ictx._last_updated_at = datetime.now(timezone.utc).isoformat()
        stats.elapsed_ms = (time.perf_counter() - t0) * 1000

        result = dict(ictx._outputs)
        return (result, stats) if return_stats else result

    def recalculate_full(
        self,
        ictx: IncrementalContext,
        new_inputs: Optional[Dict[str, Any]] = None,
        strict: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if new_inputs is not None:
            ictx._inputs.clear()
            ictx._ctx.clear()
            ictx._apply_inputs(new_inputs)
        else:
            ictx._ctx = dict(ictx._inputs)

        if self.max_operations is not None:
            self._tl._op_counter = 0

        for name in self._topo_order:
            if self.max_operations is not None:
                self._consume_op()
            try:
                val = eval(self._compiled[name], self._eval_globals, ictx._ctx)
            except FormulaBudgetExceeded:
                raise
            except Exception as e:
                if self._mode == MODE_RAISE:
                    raise FormulaError(
                        f"Evaluation failed for '{name}'",
                        field_name=name,
                        formula=self._original_expr.get(name),
                        error=e,
                        context=ictx._ctx,
                        code=ErrorCode.INVALID_TYPE,
                    ) from e
                val = None if self._mode == MODE_NULL else self._default
            ictx._write_output(name, val)

        if self._rounding_policy:
            for fld, policy in self._rounding_policy.items():
                if fld in ictx._outputs:
                    decimals = policy.get("decimals", 0)
                    ictx._write_output(fld, round(ictx._outputs[fld], decimals))

        ictx._initialized = True
        ictx._engine_hash = self._hash
        ictx._last_updated_at = datetime.now(timezone.utc).isoformat()
        return dict(ictx._outputs)

    def get_affected_nodes(self, changed_inputs: Set[str]) -> Set[str]:
        formula_names = set(self._topo_order)
        seed: Set[str] = set()
        for var in changed_inputs:
            if var in formula_names:
                seed.add(var)
            else:
                seed.update(self._input_edges.get(var, set()))
        if not seed:
            return set()
        return self._graph.get_affected(seed) & formula_names