# ═══════════════════════════════════════════════════════════════════════════
# FILE: formula_builder/api/batch_binding_resolver.py
# Batch Binding Resolver — Formula Builder v30.1
# ═══════════════════════════════════════════════════════════════════════════
"""Batch resolver that eliminates N+1 queries by grouping and caching.

MOTIVATION:
    When resolving many Formula Variable Bindings (e.g. 50+ for a BOM with
    17 items - 3 data sources), calling each handler individually results in
    N+1 database queries — one per binding.

    This module provides `BatchBindingResolver` which:
      1. COLLECT: scans all bindings to identify what data is needed
      2. GROUP: groups bindings by (source_type, query_fingerprint)
      3. EXECUTE: runs 1 batch query per group instead of N individual queries
      4. INJECT: maps batch results back to individual binding variable names

ARCHITECTURE:
    ┌─ resolve_all_batch(bindings, doc) ─────────────────────┐
    │                                                         │
    │  1. Split: batchable vs non-batchable                   │
    │     - batchable: handler has @batchable decorator       │
    │     - non-batchable: fallback to resolve_bindings_with_deps │
    │                                                         │
    │  2. Group batchable by fingerprint                      │
    │     - Same (source_type, doctype, fields) → 1 group     │
    │     → 1 SQL query with WHERE ... IN (...)               │
    │                                                         │
    │  3. Execute each group → 1 batch query                  │
    │     - If handler has resolve_batch(): use it            │
    │     - Otherwise: call handler individually (no batch)    │
    │                                                         │
    │  4. Merge: batch results + non-batchable results        │
    │                                                         │
    └─────────────────────────────────────────────────────────┘

USAGE:
    from formula_builder.api.batch_binding_resolver import BatchBindingResolver

    resolver = BatchBindingResolver()
    results = resolver.resolve_all_batch(bindings, doc=quotation_item)
    # → {"item1__weight": 1.257, "item1__price": 113000, ...}

BENCHMARK (17 Bom Items, 3 data sources each = 51 bindings):
    Without batch: ~51 individual queries (1 per binding)
    With batch:    ~4-5 queries (grouped by doctype)
    Reduction:     ~90%
"""

from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

import frappe

from formula_builder.api.data_source_registry import (
    get_handler,
    resolve_bindings_with_deps,
)
from formula_builder.security import safe_eval

# Hàm được phép trong transform formula — khớp với safe_scope mà _apply_transform
# đưa vào (value + resolved_so_far). Whitelist này phải luôn ⊇ các builtin thực
# tế trong scope; các hàm khác sẽ fail ở eval (NameError) → fallback như cũ.
_TRANSFORM_ALLOWED_FUNCS: frozenset = frozenset({
    "int", "float", "str", "bool", "len", "abs", "min", "max", "round",
})

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_fingerprint(*parts: str) -> str:
    """Create a stable fingerprint from parts for grouping.

    Same parts → same fingerprint → same batch group.
    """
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def _is_batchable(source_type: str) -> bool:
    """Check if a handler supports batch resolution."""
    handler = get_handler(source_type)
    if handler is None:
        return False
    return getattr(handler, 'batchable', False)


def _get_batch_handler(source_type: str) -> Optional[Callable]:
    """Get the batch resolve function for a handler, if available."""
    handler = get_handler(source_type)
    if handler is None:
        return None
    return getattr(handler, 'resolve_batch', None)


def _get_fingerprint_fn(source_type: str) -> Optional[Callable]:
    """Get the fingerprint function for a handler, if available."""
    handler = get_handler(source_type)
    if handler is None:
        return None
    return getattr(handler, 'fingerprint_fn', None)


# ── Query template resolver ─────────────────────────────────────────────────

def _resolve_template(val: Any, doc, resolved_so_far: dict) -> Any:
    """Resolve template strings like {inputs.xxx} or {resolved.xxx} in values."""
    if not isinstance(val, str):
        return val
    if val.startswith("{inputs.") and val.endswith("}"):
        key = val[len("{inputs."):-1]
        return resolved_so_far.get(key)
    if val.startswith("{resolved.") and val.endswith("}"):
        key = val[len("{resolved."):-1]
        return resolved_so_far.get(key)
    if val.startswith("{doc.") and val.endswith("}"):
        return doc.get(val[len("{doc."):-1]) if doc else None
    return val


def _resolve_filters(filters_raw: list, doc, resolved_so_far: dict) -> list:
    """Resolve template variables in filter lists."""
    resolved = []
    for f in filters_raw:
        if isinstance(f, list) and len(f) == 3:
            resolved.append([
                f[0],
                f[1],
                _resolve_template(f[2], doc, resolved_so_far),
            ])
        else:
            resolved.append(f)
    return resolved


# ── TRANSFORM LAYER (v31 Phase 1) ────────────────────────────────────────────

def _apply_transform(value: Any, binding: dict, resolved_so_far: dict) -> Any:
    """Apply post-resolve transformation to a value.

    Reads `transform` from source_config and applies the configured
    transformations in order: multiply → divide → add → formula → round → cast.

    The transform config lives in source_config.transform:
      {
        "formula": "value * (1 + tax_rate)",   # Formula using 'value' variable
        "multiply": 1000,                       # Simple multiply
        "divide": 100,                          # Simple divide
        "add": 50,                             # Offset
        "round": 2,                            # Decimal places
        "cast": "int"                          # Type cast
      }

    Template variables in formula are resolved against resolved_so_far.
    Returns the transformed value (or original if no transform config).
    """
    if value is None:
        return value

    cfg_raw = binding.get("source_config", "{}")
    if isinstance(cfg_raw, str):
        try:
            cfg = json.loads(cfg_raw)
        except (json.JSONDecodeError, TypeError):
            return value
    elif isinstance(cfg_raw, dict):
        cfg = cfg_raw
    else:
        return value

    transform = cfg.get("transform")
    if not transform or not isinstance(transform, dict):
        return value

    try:
        # 1. Multiply
        if "multiply" in transform:
            value = float(value) * float(transform["multiply"])

        # 2. Divide
        if "divide" in transform and float(transform["divide"]) != 0:
            value = float(value) / float(transform["divide"])

        # 3. Add offset
        if "add" in transform:
            value = float(value) + float(transform["add"])

        # 4. Formula evaluation
        if "formula" in transform and transform["formula"]:
            formula = str(transform["formula"])
            if "value" in formula:
                # Resolve template variables in the formula
                for key, val in resolved_so_far.items():
                    if f"{{{key}}}" in formula or key in formula:
                        formula = formula.replace(f"{{{key}}}", str(val))

                # Pivot RCE 2026-08-16: formula là user-controlled
                # (transform.formula trong source_config) → validate + compile
                # 1 lần (safe_eval), eval nhanh trên compiled code. Không eval
                # trần chuỗi — resolved_so_far injected vào formula có thể chứa
                # payload RCE, safe_eval chặn.
                try:
                    expr = safe_eval.compile_expression(
                        formula,
                        allowed_functions=_TRANSFORM_ALLOWED_FUNCS,
                        policy=safe_eval.TRANSFORM_POLICY,
                    )
                except ValueError:
                    # Formula không hợp lệ → bỏ qua formula eval (giữ nguyên value),
                    # vẫn áp dụng round/cast bên dưới như trước đây khi eval fail.
                    expr = None

                if expr is not None:
                    # Simple eval with restricted scope for value
                    safe_scope = {"value": value}
                    # Add resolved values as lookup
                    for k, v in resolved_so_far.items():
                        if not k.startswith("_"):
                            safe_scope[k] = v

                    try:
                        value = expr.eval(safe_scope)
                    except Exception:
                        # Fallback: return untransformed
                        pass

        # 5. Round
        if "round" in transform:
            places = int(transform["round"])
            value = round(float(value), places)

        # 6. Type cast
        cast_type = transform.get("cast", "")
        if cast_type == "int":
            value = int(float(value))
        elif cast_type == "float":
            value = float(value)
        elif cast_type == "str":
            value = str(value)

    except (ValueError, TypeError, ZeroDivisionError):
        # If transform fails, return original value
        pass

    return value


# ═══════════════════════════════════════════════════════════════════════════
# BATCH RESOLVER — core
# ═══════════════════════════════════════════════════════════════════════════

class BatchBindingResolver:
    """Resolve Formula Variable Bindings with batch query optimization.

    Eliminates N+1 queries by grouping bindings with the same source_type
    and query fingerprint into single batch database calls.

    Lifecycle:
        1. resolve_all_batch(bindings, doc) → Dict[name, value]
        2. Internal: _split_batchable → _group_by_fingerprint → _execute_groups
        3. Merge with non-batchable results

    Cache:
        Per-request in-memory cache (frappe.local)._batch_resolver_cache
        Set cache_ttl > 0 for Redis-based caching (optional).
    """

    def __init__(self, cache_ttl: int = 0):
        """Initialize resolver.

        Args:
            cache_ttl: Redis cache TTL in seconds. 0 = request-level only.
        """
        self.cache_ttl = cache_ttl
        self._request_cache: Dict[str, Any] = {}

    # ── Public API ──────────────────────────────────────────────────────

    def resolve_all_batch(
        self,
        bindings: List[dict],
        doc=None,
        pre_resolved: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve all bindings, batching where possible.

        Args:
            bindings: List of Formula Variable Binding dicts.
            doc: The current Frappe document (optional).
            pre_resolved: Already-resolved variables to seed the context.

        Returns:
            Dict mapping variable_name → resolved_value.
        """
        if not bindings:
            return {}

        resolved: Dict[str, Any] = dict(pre_resolved or {})

        # 1. Split batchable vs non-batchable
        batchable, non_batchable = self._split_batchable(bindings)

        # 2. Resolve batchable first (they may be depended on by non-batchable)
        if batchable:
            batch_results = self._resolve_batchable(batchable, doc, resolved)
            resolved.update(batch_results)

        # 3. Resolve non-batchable with dependencies (uses existing DAG resolver)
        if non_batchable:
            non_batch_results = resolve_bindings_with_deps(non_batchable, doc)
            resolved.update(non_batch_results)

        # 4. (v31 Phase 1) Apply transform layer to all resolved values
        binding_map = {b["variable_name"]: b for b in bindings}
        for var_name in list(resolved.keys()):
            if var_name in binding_map:
                resolved[var_name] = _apply_transform(
                    resolved[var_name], binding_map[var_name], resolved
                )

        return resolved

    # ── Split logic ─────────────────────────────────────────────────────

    def _split_batchable(
        self, bindings: List[dict]
    ) -> Tuple[List[dict], List[dict]]:
        """Split bindings into (batchable, non_batchable).

        A binding is batchable if:
        - Its source_type handler has the @batchable attribute
        - Its batch_group field is set (explicit opt-in per binding)
        """
        batchable = []
        non_batchable = []

        for b in bindings:
            source_type = b.get("source_type", "")
            if _is_batchable(source_type):
                batchable.append(b)
            else:
                non_batchable.append(b)

        return batchable, non_batchable

    # ── Group logic ─────────────────────────────────────────────────────

    def _resolve_batchable(
        self,
        batchable: List[dict],
        doc,
        resolved_so_far: dict,
    ) -> Dict[str, Any]:
        """Group and execute batch queries for batchable bindings."""
        groups = self._group_by_fingerprint(batchable)

        results: Dict[str, Any] = {}
        for (source_type, fingerprint), group_bindings in groups.items():
            try:
                group_results = self._execute_one_group(
                    source_type, fingerprint, group_bindings, doc,
                    resolved_so_far,
                )
                results.update(group_results)
            except Exception as e:
                frappe.log_error(
                    title=f"BatchBindingResolver: group failed ({source_type}/{fingerprint})",
                    message=str(e),
                )
                # Fallback: resolve individually
                for b in group_bindings:
                    try:
                        handler = get_handler(source_type)
                        if handler:
                            results[b["variable_name"]] = handler(
                                b, doc, resolved_so_far
                            )
                    except Exception:
                        results[b["variable_name"]] = b.get("default_value")

        return results

    def _group_by_fingerprint(
        self, bindings: List[dict]
    ) -> Dict[Tuple[str, str], List[dict]]:
        """Group bindings by (source_type, fingerprint).

        Two bindings end up in the same group when:
        - Same source_type
        - Same fingerprint (computed by the handler's fingerprint_fn)
        - OR same batch_group field value
        """
        groups: Dict[Tuple[str, str], List[dict]] = defaultdict(list)

        for b in bindings:
            source_type = b.get("source_type", "")

            # Try explicit batch_group from binding first
            batch_group = b.get("batch_group", "")
            if batch_group:
                fp = batch_group
            else:
                # Use handler's fingerprint function
                fp_fn = _get_fingerprint_fn(source_type)
                if fp_fn:
                    try:
                        cfg = json.loads(b.get("source_config", "{}"))
                        fp = fp_fn(cfg)
                    except Exception:
                        fp = _make_fingerprint(
                            source_type,
                            b.get("source_config", ""),
                        )
                else:
                    # Default: group by source_type only
                    fp = source_type

            groups[(source_type, fp)].append(b)

        return groups

    # ── Preview logic (A4 — Phase 1) ────────────────────────────────────

    def _strategy_for(self, source_type: str) -> str:
        """Dự đoán strategy mà `_execute_one_group` sẽ dùng cho nhóm.

        Đúng thứ tự ưu tiên của execution thật:
          - handler có `resolve_batch`  → "resolve_batch"
          - handler có `resolve_batch_query` → "resolve_batch_query"
          - còn lại                      → "execute_individual" (N+1 fallback)
        """
        if _get_batch_handler(source_type):
            return "resolve_batch"
        handler = get_handler(source_type)
        if handler and getattr(handler, "resolve_batch_query", None):
            return "resolve_batch_query"
        return "execute_individual"

    def preview_groups(self, bindings: List[dict]) -> Dict[str, Any]:
        """Xem trước grouping batch cho danh sách binding — KHÔNG execute handler.

        Mô phỏng đúng pipeline của `resolve_all_batch`:
          1. `_split_batchable` → (batchable, non_batchable)
          2. batchable → `_group_by_fingerprint` → mỗi nhóm 1 strategy
             (giống `_execute_one_group`: resolve_batch / resolve_batch_query /
             execute_individual — nhóm rơi vào execute_individual = N+1).
          3. non-batchable → từng binding chạy qua `resolve_bindings_with_deps`
             (mỗi binding 1 handler call).

        Args:
            bindings: danh sách binding dict (đã khớp scope).

        Returns:
            Dict: summary + groups + individual_bindings. Định dạng khớp contract
            JS dialog preview trong FVB form (A4).
        """
        batchable, non_batchable = self._split_batchable(bindings)

        groups: List[Dict[str, Any]] = []
        individual_vars: List[Dict[str, Any]] = []
        for (source_type, fp), group_bindings in self._group_by_fingerprint(batchable).items():
            strategy = self._strategy_for(source_type)
            # Nhóm batchable nhưng không có resolve_batch/resolve_batch_query
            # → execution thật rơi xuống `_execute_individual` (N+1).
            if strategy == "execute_individual":
                for b in group_bindings:
                    individual_vars.append({
                        "variable_name": b.get("variable_name"),
                        "source_type": source_type,
                        "reason": "nhóm batchable nhưng handler không có resolve_batch "
                                  "→ rơi vào _execute_individual (N+1)",
                    })
            groups.append({
                "source_type": source_type,
                "fingerprint": fp,
                "strategy": strategy,
                "binding_count": len(group_bindings),
                "variables": [b.get("variable_name") for b in group_bindings],
                "explicit_batch_group": bool(group_bindings[0].get("batch_group")),
            })

        # Non-batchable: từng binding resolve độc lập qua deps resolver.
        for b in non_batchable:
            individual_vars.append({
                "variable_name": b.get("variable_name"),
                "source_type": b.get("source_type", ""),
                "reason": "handler không batchable → resolve_bindings_with_deps từng binding",
            })

        # Ước lượng số query (gần đúng):
        #   nhóm batch       → 1 query
        #   nhóm individual  → 1 query / binding
        #   non-batchable    → 1 handler call / binding
        batch_group_count = 0
        estimated_queries = 0
        for g in groups:
            if g["strategy"] == "execute_individual":
                estimated_queries += g["binding_count"]
            else:
                batch_group_count += 1
                estimated_queries += 1
        estimated_queries += len(non_batchable)

        total_bindings = len(bindings)
        summary = {
            "total_bindings": total_bindings,
            "batch_groups": batch_group_count,
            "total_groups": len(groups),
            "individual_bindings": len(individual_vars),
            "estimated_queries": estimated_queries,
            # Càng xa 1:1 thì batch càng đáng giá (≈ 1/(total) giảm được nếu 100% batchable)
            "potential_query_reduction": round(
                (1 - (estimated_queries / max(total_bindings, 1))) * 100, 1
            ),
        }

        return {
            "summary": summary,
            "groups": groups,
            "individual_bindings": individual_vars,
        }

    # ── Execute logic ───────────────────────────────────────────────────

    def _execute_one_group(
        self,
        source_type: str,
        fingerprint: str,
        bindings: List[dict],
        doc,
        resolved_so_far: dict,
    ) -> Dict[str, Any]:
        """Execute one batch group.

        Strategy (in order of preference):
        1. Handler has resolve_batch(bindings, doc, resolved) → use it
        2. Handler has resolve_batch_query(bindings) → use pre-query
        3. Call handler individually (no batching possible for this group)
        """
        # Strategy 1: Handler provides resolve_batch
        batch_handler = _get_batch_handler(source_type)
        if batch_handler:
            return batch_handler(bindings, doc, resolved_so_far)

        # Strategy 2: Handler provides resolve_batch_query for pre-query
        handler = get_handler(source_type)
        pre_query_fn = getattr(handler, 'resolve_batch_query', None)
        if pre_query_fn:
            return self._execute_with_pre_query(
                pre_query_fn, bindings, doc, resolved_so_far, handler,
            )

        # Strategy 3: Fallback — call handler individually
        return self._execute_individual(bindings, doc, resolved_so_far)

    def _execute_with_pre_query(
        self,
        pre_query_fn: Callable,
        bindings: List[dict],
        doc,
        resolved_so_far: dict,
        handler: Callable,
    ) -> Dict[str, Any]:
        """Execute a pre-query to fetch all data, then distribute to bindings.

        pre_query_fn(bindings, doc, resolved) → Dict[key, value]
        Each binding specifies how to extract its value from the pre-query result.
        """
        try:
            pre_data = pre_query_fn(bindings, doc, resolved_so_far)
        except Exception as e:
            frappe.log_error(
                f"Batch pre-query failed: {e}",
                "BatchBindingResolver",
            )
            return self._execute_individual(bindings, doc, resolved_so_far)

        results = {}
        for b in bindings:
            name = b["variable_name"]
            cfg = json.loads(b.get("source_config", "{}"))
            key_field = cfg.get("batch_key", cfg.get("key_field", "item_code"))
            key_value = cfg.get("batch_key_value") or cfg.get(key_field)

            if key_value and key_value in pre_data:
                results[name] = pre_data[key_value]
            else:
                # Fallback to individual handler
                try:
                    results[name] = handler(b, doc, resolved_so_far)
                except Exception:
                    results[name] = b.get("default_value")

        return results

    def _execute_individual(
        self,
        bindings: List[dict],
        doc,
        resolved_so_far: dict,
    ) -> Dict[str, Any]:
        """Call each handler individually (no batching)."""
        results = {}
        for b in bindings:
            source_type = b.get("source_type", "")
            handler = get_handler(source_type)
            if handler is None:
                results[b["variable_name"]] = b.get("default_value")
                continue
            try:
                val = handler(b, doc, resolved_so_far)
                results[b["variable_name"]] = (
                    val if val is not None else b.get("default_value")
                )
            except Exception:
                results[b["variable_name"]] = b.get("default_value")
        return results


# ═══════════════════════════════════════════════════════════════════════════
# CONVENIENCE: Single-call API
# ═══════════════════════════════════════════════════════════════════════════

# Module-level singleton for per-request reuse
def _get_request_resolver() -> BatchBindingResolver:
    """Get or create a per-request BatchBindingResolver from frappe.local."""
    if not hasattr(frappe.local, '_batch_binding_resolver'):
        frappe.local._batch_binding_resolver = BatchBindingResolver()
    return frappe.local._batch_binding_resolver


def resolve_all_bindings_batch(
    bindings: List[dict],
    doc=None,
    pre_resolved: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience function: resolve all bindings with batch optimization.

    Uses per-request singleton for caching.

    Args:
        bindings: List of binding dicts.
        doc: Current Frappe document.
        pre_resolved: Pre-resolved variables.

    Returns:
        Dict[variable_name, resolved_value]
    """
    resolver = _get_request_resolver()
    return resolver.resolve_all_batch(bindings, doc, pre_resolved)


# ═══════════════════════════════════════════════════════════════════════════
# A4 — Preview batch groups (Phase 1 — platform)
# ═══════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def preview_batch_groups(
    doctype: str = "",
    applies_to_field: str = "",
    include_inactive: int = 0,
) -> Dict[str, Any]:
    """Xem trước grouping batch của binding active theo scope — KHÔNG execute.

    Scope binding lấy theo đúng luật filter scope dùng chung
    (`binding_scope.get_scope_bindings` — cùng semantics như `get_live_context`):
      global + khớp doctype + khớp doctype/field.

    Với mỗi binding báo strategy dự kiến như `resolve_all_batch` sẽ chạy:
      - resolve_batch        → 1 batch query cho cả nhóm
      - resolve_batch_query  → 1 pre-query + distribute
      - execute_individual   → N+1 (từng binding gọi handler riêng)

    Args:
        doctype: doctype scope ("" = global + mọi doctype-khớp).
        applies_to_field: fieldname scope ("" = không lọc theo field).
        include_inactive: 1 → kể cả binding is_active=0.

    Returns:
        Dict theo contract JS (summary + groups + individual_bindings).
        Khi lỗi trả về {"error": <message>}.
    """
    from formula_builder.api.binding_scope import BINDING_FIELDS, get_scope_bindings

    try:
        bindings = get_scope_bindings(
            doctype=doctype or "",
            field=applies_to_field or "",
            include_inactive=bool(int(include_inactive or 0)),
            fields=list(BINDING_FIELDS) + ["batch_group", "is_active"],
        )
    except Exception as e:
        frappe.log_error(
            title="preview_batch_groups: fetch scope bindings failed",
            message=str(e),
        )
        return {"error": f"Không đọc được scope bindings: {e}"}

    # Preview dùng resolver mới (không sờ tới request-cache / singleton).
    preview = BatchBindingResolver().preview_groups(bindings)
    preview["scope"] = {
        "doctype": doctype or "",
        "applies_to_field": applies_to_field or "",
        "include_inactive": bool(int(include_inactive or 0)),
    }
    return preview
