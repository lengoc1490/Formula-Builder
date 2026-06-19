# formula_utils/engine_public.py
# Public FormulaEngine class - full featured with explain, snapshot, cache, scenarios

import marshal
import sys
import time
from collections import deque
from typing import Dict, Any, Optional, Set, List, Tuple, Union

from .engine_audit import FormulaEngineAudit
from .engine_core import IncrementalContext
from .types import (
    ExplainResult, ExplainStep, InputIssue, ScenarioComparison,
    EnterpriseSnapshot, SnapshotTag, SnapshotStatus,
    ExecutionTraceBlock, TraceEntry, IncrementalStats,
    ValidationResult, TopoSortResult, SccTopoResult,
)
from .errors import FormulaError, ErrorCode, _error_type_slug
from .snapshot import SnapshotManager
from .normalize import hash_dict
from .topo import topo_sort, topo_sort_with_info, topo_sort_data, topo_sort_flat
from .topo import scc_topo_sort, scc_topo_sort_with_info, scc_topo_sort_data, scc_topo_sort_flat
from .allocation import allocate, allocate_inplace, allocate_fast, AllocationResult, AllocTuple
from .scc_linear import solve_linear_on_graph, SccLinearSolveResult
from .time_bucket import (
    generate_time_buckets, generate_time_buckets_flat, year_buckets,
    get_period, get_period_by_date, get_period_offset, same_period_last_year,
)


class FormulaEngine(FormulaEngineAudit):
    """
    Complete formula engine with all features:
    - explain() / explain_all()
    - diff_inputs() / validate_inputs()
    - calculate_scenarios() / compare_scenarios()
    - calculate_safe()
    - snapshot() / snapshot_with_trace() / snapshot_revise()
    - to_cache_dict() / from_cache_dict()
    - static time bucket methods
    - static topo sort methods (bound as instance methods)
    - static allocation methods
    - static linear solver
    """

    # ------------------------------------------------------------------
    # Explain
    # ------------------------------------------------------------------

    def explain(
        self,
        field: str,
        inputs: Dict[str, Any],
        strict: Optional[bool] = None,
    ) -> ExplainResult:
        """Explain how a formula field is calculated."""
        if field not in self._original_expr:
            raise FormulaError(
                f"Field '{field}' không phải formula name. "
                f"Các formula hiện có: {', '.join(sorted(self._original_expr.keys()))}",
                code=ErrorCode.UNKNOWN,
            )

        full_result = self.calculate(inputs, strict=strict)
        merged = {**inputs, **full_result}

        def _get_ancestors(fname: str) -> Set[str]:
            visited: Set[str] = set()
            queue = deque([fname])
            while queue:
                cur = queue.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                for dep in self._deps_cache.get(cur, set()):
                    if dep in self._original_expr:
                        queue.append(dep)
            return visited

        ancestors = _get_ancestors(field)
        relevant_topo = [n for n in self._topo_order if n in ancestors]

        depth_map: Dict[str, int] = {field: 0}
        queue = deque([field])
        while queue:
            cur = queue.popleft()
            for dep in self._deps_cache.get(cur, set()):
                if dep in self._original_expr and dep not in depth_map:
                    depth_map[dep] = depth_map[cur] + 1
                    queue.append(dep)

        steps = []
        for name in relevant_topo:
            direct_deps = self._deps_cache.get(name, set())
            dep_vals = {d: merged.get(d) for d in sorted(direct_deps)}
            steps.append(ExplainStep(
                name=name,
                formula=self._original_expr.get(name, ""),
                value=merged.get(name),
                deps=dep_vals,
                depth=depth_map.get(name, 0),
                is_root=(name == field),
            ))

        inputs_used: Dict[str, Any] = {}
        for input_var, formula_set in self._input_edges.items():
            if formula_set & ancestors and input_var in inputs:
                inputs_used[input_var] = inputs[input_var]

        return ExplainResult(
            field=field,
            value=full_result.get(field),
            steps=steps,
            inputs_used=inputs_used,
        )

    def explain_all(
        self,
        inputs: Dict[str, Any],
        strict: Optional[bool] = None,
    ) -> Dict[str, ExplainResult]:
        """Explain all formula fields."""
        full_result = self.calculate(inputs, strict=strict)
        merged = {**inputs, **full_result}

        def _get_ancestors(fname: str) -> Set[str]:
            visited: Set[str] = set()
            queue = deque([fname])
            while queue:
                cur = queue.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                for dep in self._deps_cache.get(cur, set()):
                    if dep in self._original_expr:
                        queue.append(dep)
            return visited

        results: Dict[str, ExplainResult] = {}
        for fld in self._topo_order:
            ancestors = _get_ancestors(fld)
            relevant_topo = [n for n in self._topo_order if n in ancestors]

            depth_map: Dict[str, int] = {fld: 0}
            q2 = deque([fld])
            while q2:
                cur = q2.popleft()
                for dep in self._deps_cache.get(cur, set()):
                    if dep in self._original_expr and dep not in depth_map:
                        depth_map[dep] = depth_map[cur] + 1
                        q2.append(dep)

            steps = []
            for name in relevant_topo:
                direct_deps = self._deps_cache.get(name, set())
                dep_vals = {d: merged.get(d) for d in sorted(direct_deps)}
                steps.append(ExplainStep(
                    name=name,
                    formula=self._original_expr.get(name, ""),
                    value=merged.get(name),
                    deps=dep_vals,
                    depth=depth_map.get(name, 0),
                    is_root=(name == fld),
                ))

            inputs_used: Dict[str, Any] = {}
            for input_var, formula_set in self._input_edges.items():
                if formula_set & ancestors and input_var in inputs:
                    inputs_used[input_var] = inputs[input_var]

            results[fld] = ExplainResult(
                field=fld,
                value=full_result.get(fld),
                steps=steps,
                inputs_used=inputs_used,
            )
        return results

    # ------------------------------------------------------------------
    # Diff inputs
    # ------------------------------------------------------------------

    def diff_inputs(
        self,
        old_inputs: Dict[str, Any],
        new_inputs: Dict[str, Any],
    ) -> Set[str]:
        changed: Set[str] = set()
        all_keys = set(old_inputs.keys()) | set(new_inputs.keys())
        for key in all_keys:
            old_val = old_inputs.get(key)
            new_val = new_inputs.get(key)
            if old_val != new_val:
                changed.add(key)
        return changed

    def diff_inputs_values(
        self,
        old_inputs: Dict[str, Any],
        new_inputs: Dict[str, Any],
    ) -> Dict[str, tuple]:
        result: Dict[str, tuple] = {}
        all_keys = set(old_inputs.keys()) | set(new_inputs.keys())
        for key in all_keys:
            old_val = old_inputs.get(key)
            new_val = new_inputs.get(key)
            if old_val != new_val:
                result[key] = (old_val, new_val)
        return result

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------

    def validate_inputs(
        self,
        inputs: Dict[str, Any],
        strict_types: bool = False,
    ) -> List[InputIssue]:
        issues: List[InputIssue] = []

        for name, fld in self._input_schema.items():
            if fld.required and name not in inputs:
                issues.append(InputIssue(
                    field=name,
                    issue=f"Trường bắt buộc '{name}' chưa được cung cấp.",
                    value=None,
                    severity="error",
                    expected="bắt buộc có giá trị",
                ))

        for name, value in inputs.items():
            field_schema = self._input_schema.get(name)
            if field_schema is None:
                continue

            if field_schema.dtype is not None and value is not None:
                if not isinstance(value, field_schema.dtype):
                    try:
                        field_schema.dtype(value)
                        sev = "warning"
                        msg = (f"Giá trị '{value}' không đúng kiểu {field_schema.dtype.__name__}, "
                               f"nhưng có thể tự động convert.")
                    except (ValueError, TypeError):
                        sev = "error" if strict_types else "warning"
                        msg = (f"Giá trị '{value}' không thể chuyển sang "
                               f"{field_schema.dtype.__name__}.")
                    issues.append(InputIssue(
                        field=name, issue=msg, value=value,
                        severity=sev, expected=field_schema.dtype.__name__,
                    ))

            if isinstance(value, (int, float)):
                if hasattr(field_schema, 'min_value') and field_schema.min_value is not None:
                    if value < field_schema.min_value:
                        issues.append(InputIssue(
                            field=name,
                            issue=f"Giá trị {value:,} nhỏ hơn min_value={field_schema.min_value:,}.",
                            value=value, severity="warning",
                            expected=f">= {field_schema.min_value}",
                        ))
                if hasattr(field_schema, 'max_value') and field_schema.max_value is not None:
                    if value > field_schema.max_value:
                        issues.append(InputIssue(
                            field=name,
                            issue=f"Giá trị {value:,} lớn hơn max_value={field_schema.max_value:,}.",
                            value=value, severity="warning",
                            expected=f"<= {field_schema.max_value}",
                        ))

            if hasattr(field_schema, 'allowed_values') and field_schema.allowed_values:
                if value not in field_schema.allowed_values:
                    issues.append(InputIssue(
                        field=name,
                        issue=f"Giá trị '{value}' không nằm trong danh sách cho phép.",
                        value=value, severity="error",
                        expected=f"một trong: {field_schema.allowed_values}",
                    ))

        return issues

    # ------------------------------------------------------------------
    # Multi-scenario
    # ------------------------------------------------------------------

    def calculate_scenarios(
        self,
        scenarios: Dict[str, Dict[str, Any]],
        strict: Optional[bool] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return {
            name: self.calculate(inp, strict=strict)
            for name, inp in scenarios.items()
        }

    def compare_scenarios(
        self,
        scenarios: Dict[str, Dict[str, Any]],
        fields: Optional[List[str]] = None,
        base_scenario: Optional[str] = None,
        strict: Optional[bool] = None,
    ) -> ScenarioComparison:
        all_results = self.calculate_scenarios(scenarios, strict=strict)

        sc_names = list(scenarios.keys())
        if not sc_names:
            return ScenarioComparison(scenarios=[], fields=[], results={}, delta={})

        base = base_scenario or sc_names[0]
        sample_result = next(iter(all_results.values()), {})
        compare_fields = fields if fields else [
            f for f in self._topo_order if f in sample_result
        ]

        delta: Dict[str, Dict[str, Any]] = {}
        base_result = all_results.get(base, {})
        for fld in compare_fields:
            delta[fld] = {}
            base_val = base_result.get(fld)
            for sc in sc_names:
                if sc == base:
                    continue
                sc_val = all_results.get(sc, {}).get(fld)
                if isinstance(base_val, (int, float)) and isinstance(sc_val, (int, float)):
                    d = sc_val - base_val
                    pct = round(d / abs(base_val) * 100, 2) if base_val != 0 else None
                    delta[fld][sc] = {"delta": d, "pct": pct}
                else:
                    delta[fld][sc] = {"delta": None, "pct": None}

        return ScenarioComparison(
            scenarios=sc_names,
            fields=compare_fields,
            results=all_results,
            delta=delta,
            base_scenario=base,
        )

    # ------------------------------------------------------------------
    # Safe calculate (never raises)
    # ------------------------------------------------------------------

    def calculate_safe(
        self,
        inputs: Dict[str, Any],
        strict: Optional[bool] = None,
    ) -> Dict[str, Any]:
        try:
            result = self.calculate(inputs, strict=strict)
            result["_ok"] = True
            result["_error"] = ""
            result["_error_type"] = ""
            return result
        except Exception as e:
            out: Dict[str, Any] = {}
            for name in self._topo_order:
                out[name] = self._default
            out["_ok"] = False
            out["_error"] = str(e)
            out["_error_type"] = _error_type_slug(e)
            return out

    # ------------------------------------------------------------------
    # Snapshot methods
    # ------------------------------------------------------------------

    def snapshot(
        self,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        tag: SnapshotTag = SnapshotTag.ESTIMATE,
        status: SnapshotStatus = SnapshotStatus.DRAFT,
        created_by: str = "system",
        dirty_nodes: Optional[List[str]] = None,
        calc_mode: str = "full",
        parent_snapshot: Optional[EnterpriseSnapshot] = None,
        notes: Optional[str] = None,
        source_doc: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> EnterpriseSnapshot:
        return SnapshotManager.create(
            engine=self,
            inputs=inputs,
            outputs=outputs,
            tag=tag,
            status=status,
            created_by=created_by,
            dirty_nodes=dirty_nodes,
            calc_mode=calc_mode,
            parent_snapshot=parent_snapshot,
            notes=notes,
            source_doc=source_doc,
            approved_by=approved_by,
        )

    def snapshot_with_trace(
        self,
        inputs: Dict[str, Any],
        business_inputs: Optional[Dict[str, Any]] = None,
        tag: SnapshotTag = SnapshotTag.ESTIMATE,
        status: SnapshotStatus = SnapshotStatus.DRAFT,
        created_by: str = "system",
        previous_values: Optional[Dict[str, Any]] = None,
        dirty_nodes: Optional[List[str]] = None,
        calc_mode: str = "full",
        parent_snapshot: Optional[EnterpriseSnapshot] = None,
        notes: Optional[str] = None,
        source_doc: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], EnterpriseSnapshot]:
        topo_order = list(getattr(self, '_topo_order', []))
        deps_cache = getattr(self, '_deps_cache', {})
        orig_expr = getattr(self, '_original_expr', {})
        compiled = getattr(self, '_compiled', {})
        eval_globals = getattr(self, '_eval_globals', {})
        prev = dict(previous_values or {})

        if dirty_nodes is not None:
            dirty_set = set(dirty_nodes)
        else:
            dirty_set = set(topo_order)

        ctx: Dict[str, Any] = dict(inputs)
        entries: List[TraceEntry] = []
        total_start = time.perf_counter()

        for name in topo_order:
            if name not in compiled:
                continue

            is_dirty = name in dirty_set
            if not is_dirty:
                entries.append(TraceEntry(
                    field=name,
                    formula=orig_expr.get(name, ""),
                    old_value=prev.get(name),
                    new_value=ctx.get(name, prev.get(name)),
                    triggered_by=[],
                    dep_values={},
                    exec_time_ms=0.0,
                    skipped=True,
                ))
                continue

            dep_names = list(deps_cache.get(name, set()))
            dep_vals = {d: ctx.get(d) for d in dep_names}
            triggered = [d for d in dep_names if ctx.get(d) != prev.get(d)]

            old_val = prev.get(name)
            t_start = time.perf_counter()
            try:
                new_val = eval(compiled[name], eval_globals, ctx)
            except Exception:
                new_val = getattr(self, '_default', 0)
            exec_ms = (time.perf_counter() - t_start) * 1000

            ctx[name] = new_val
            entries.append(TraceEntry(
                field=name,
                formula=orig_expr.get(name, ""),
                old_value=old_val,
                new_value=new_val,
                triggered_by=triggered,
                dep_values=dep_vals,
                exec_time_ms=exec_ms,
                skipped=False,
            ))

        total_ms = (time.perf_counter() - total_start) * 1000
        evaluated = sum(1 for e in entries if not e.skipped)
        skipped = sum(1 for e in entries if e.skipped)

        outputs = {k: ctx[k] for k in topo_order if k in ctx}
        exec_trace_block = ExecutionTraceBlock(
            fields_evaluated=evaluated,
            fields_skipped=skipped,
            total_exec_ms=total_ms,
            entries=entries,
        )

        snap = SnapshotManager.create(
            engine=self,
            inputs=business_inputs if business_inputs is not None else inputs,
            outputs=outputs,
            tag=tag,
            status=status,
            created_by=created_by,
            exec_trace=exec_trace_block,
            dirty_nodes=dirty_nodes,
            calc_mode=calc_mode,
            parent_snapshot=parent_snapshot,
            notes=notes,
            source_doc=source_doc,
            approved_by=approved_by,
        )
        return outputs, snap

    def snapshot_revise(
        self,
        previous_snapshot: EnterpriseSnapshot,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        tag: SnapshotTag = SnapshotTag.ACTUAL,
        status: SnapshotStatus = SnapshotStatus.DRAFT,
        created_by: str = "system",
        exec_trace: Optional[ExecutionTraceBlock] = None,
        dirty_nodes: Optional[List[str]] = None,
        calc_mode: str = "full",
        notes: Optional[str] = None,
        source_doc: Optional[str] = None,
    ) -> EnterpriseSnapshot:
        return SnapshotManager.revise(
            engine=self,
            previous_snapshot=previous_snapshot,
            inputs=inputs,
            outputs=outputs,
            tag=tag,
            status=status,
            created_by=created_by,
            exec_trace=exec_trace,
            dirty_nodes=dirty_nodes,
            calc_mode=calc_mode,
            notes=notes,
            source_doc=source_doc,
        )

    @staticmethod
    def compare_snapshots(
        snap1: EnterpriseSnapshot,
        snap2: EnterpriseSnapshot,
    ) -> Dict[str, Any]:
        return SnapshotManager.compare(snap1, snap2)

    # ------------------------------------------------------------------
    # Cache serialization
    # ------------------------------------------------------------------

    def to_cache_dict(self) -> Dict[str, Any]:
        compiled_serial = {}
        for name, code_obj in self._compiled.items():
            compiled_serial[name] = marshal.dumps(code_obj)

        meta_serial = None
        if self._meta:
            try:
                meta_serial = {
                    "id": getattr(self._meta, "id", None),
                    "name": getattr(self._meta, "name", None),
                    "version": getattr(self._meta, "version", None),
                    "description": getattr(self._meta, "description", None),
                    "frozen": getattr(self._meta, "frozen", False),
                }
            except AttributeError:
                meta_serial = None

        return {
            "_cache_version": "v17",
            "_engine_hash": self._hash,
            "_engine_version": self.ENGINE_VERSION,
            "_python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "formulas": list(self._formulas),
            "topo_order": list(self._topo_order),
            "original_expr": dict(self._original_expr),
            "compiled_serial": compiled_serial,
            "on_error": {1: "raise", 2: "null", 3: "default"}.get(self._mode, "default"),
            "default_value": self._default,
            "deterministic": self.deterministic,
            "max_operations": self.max_operations,
            "max_formula_count": self.max_formula_count,
            "max_dependency_depth": self.max_dependency_depth,
            "max_iterable_size": self._max_iterable_size,
            "meta": meta_serial,
        }

    @classmethod
    def from_cache_dict(cls, d: Dict[str, Any], **override_kwargs) -> "FormulaEngine":
        cache_ver = d.get("_cache_version", "")
        if cache_ver != "v17":
            raise FormulaError(
                f"Cache version '{cache_ver}' không tương thích với engine v17. "
                "Hãy rebuild cache.",
                code=ErrorCode.UNKNOWN,
            )
        cached_py = d.get("_python_version", "")
        cur_py = f"{sys.version_info.major}.{sys.version_info.minor}"
        if cached_py and cached_py != cur_py:
            raise FormulaError(
                f"Cache được build trên Python {cached_py}, "
                f"đang chạy Python {cur_py}. Hãy rebuild cache.",
                code=ErrorCode.UNKNOWN,
            )

        init_kwargs = {
            "on_error": override_kwargs.get("on_error", d.get("on_error", "default")),
            "default_value": override_kwargs.get("default_value", d.get("default_value", 0)),
            "deterministic": override_kwargs.get("deterministic", d.get("deterministic", True)),
            "max_operations": override_kwargs.get("max_operations", d.get("max_operations")),
            "max_formula_count": override_kwargs.get("max_formula_count", d.get("max_formula_count")),
            "max_dependency_depth": override_kwargs.get("max_dependency_depth", d.get("max_dependency_depth")),
            "max_iterable_size": override_kwargs.get("max_iterable_size", d.get("max_iterable_size")),
        }
        engine = cls(formulas=d["formulas"], **init_kwargs)

        if d.get("compiled_serial"):
            try:
                for name, serial in d["compiled_serial"].items():
                    engine._compiled[name] = marshal.loads(serial)
            except (ValueError, EOFError, TypeError):
                pass
        return engine

    # ------------------------------------------------------------------
    # Topo sort methods (bound to instance for convenience)
    # ------------------------------------------------------------------

    def topo_sort(
        self,
        items: List[Any],
        id_fn: callable,
        deps_fn: callable,
    ) -> List[Any]:
        return topo_sort(items, id_fn, deps_fn)

    def topo_sort_with_info(
        self,
        items: List[Any],
        id_fn: callable,
        deps_fn: callable,
    ) -> TopoSortResult:
        return topo_sort_with_info(items, id_fn, deps_fn)

    def scc_topo_sort(
        self,
        items: List[Any],
        id_fn: callable,
        deps_fn: callable,
    ) -> List[Any]:
        return scc_topo_sort(items, id_fn, deps_fn)

    def scc_topo_sort_with_info(
        self,
        items: List[Any],
        id_fn: callable,
        deps_fn: callable,
    ) -> SccTopoResult:
        return scc_topo_sort_with_info(items, id_fn, deps_fn)

    # ------------------------------------------------------------------
    # Allocation methods
    # ------------------------------------------------------------------

    def allocate(
        self,
        sources: List[Dict[str, Any]],
        targets: List[Dict[str, Any]],
        method: str = "equal",
        **kwargs,
    ) -> AllocationResult:
        return allocate(sources, targets, method, **kwargs)

    def allocate_inplace(
        self,
        sources: List[Dict[str, Any]],
        targets,
        out_key: str = "allocated",
        **kwargs,
    ) -> Tuple[Dict[Any, float], Dict[Any, float], List[str]]:
        return allocate_inplace(sources, targets, out_key, **kwargs)

    def allocate_fast(
        self,
        sources: List[Dict[str, Any]],
        targets: List[Dict[str, Any]],
        method: str = "equal",
        **kwargs,
    ) -> Tuple[List[AllocTuple], Dict[Any, float], Dict[Any, float], List[str]]:
        return allocate_fast(sources, targets, method, **kwargs)

    # ------------------------------------------------------------------
    # Linear solver
    # ------------------------------------------------------------------

    def solve_linear_on_graph(
        self,
        items: List[Any],
        id_fn: callable,
        deps_fn: callable,
        b_fn: callable,
        coeff_fn: callable,
        output_fn: callable,
        **kwargs,
    ) -> SccLinearSolveResult:
        return solve_linear_on_graph(
            items, id_fn, deps_fn, b_fn, coeff_fn, output_fn, **kwargs
        )

    # ------------------------------------------------------------------
    # Time bucket static methods
    # ------------------------------------------------------------------

    @staticmethod
    def get_time_buckets(
        year: int,
        types: Optional[List[str]] = None,
        *,
        week_start: str = "monday",
        label_format: Optional[str] = None,
        full_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        return generate_time_buckets(year, types,
                                     week_start=week_start,
                                     label_format=label_format,
                                     full_format=full_format)

    @staticmethod
    def get_time_buckets_flat(
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
        return generate_time_buckets_flat(
            year, types,
            week_start=week_start, label_format=label_format, full_format=full_format,
            as_dict=as_dict, as_ui=as_ui, as_filter=as_filter, as_entry=as_entry,
        )

    @staticmethod
    def year_buckets(
        year: Optional[int] = None,
        offset: int = 0,
        types: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        return year_buckets(year, offset, types, **kwargs)

    @staticmethod
    def get_period(period_type: str, index: int, year: int, **kwargs) -> Optional[Any]:
        return get_period(period_type, index, year, **kwargs)

    @staticmethod
    def get_period_by_date(d: Any, period_type: str, **kwargs) -> Optional[Any]:
        return get_period_by_date(d, period_type, **kwargs)

    @staticmethod
    def get_period_offset(bucket: Any, offset: int, **kwargs) -> Optional[Any]:
        return get_period_offset(bucket, offset, **kwargs)

    @staticmethod
    def same_period_last_year(bucket: Any, years_back: int = 1, **kwargs) -> Optional[Any]:
        return same_period_last_year(bucket, years_back, **kwargs)