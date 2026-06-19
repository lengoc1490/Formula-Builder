# formula_utils/engine_trace.py
# Trace engine - extends core with optional trace capability

from typing import Dict, Any, Optional, Set, Union, Tuple

from .engine_core import FormulaEngineCore, IncrementalContext
from .types import IncrementalStats


class FormulaEngineTrace(FormulaEngineCore):
    """Formula engine with optional trace capabilities."""

    def calculate(
        self,
        inputs: Dict[str, Any],
        trace_fields: Optional[Set[str]] = None,
        explain_ui: bool = False,
        strict: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Calculate with optional trace."""
        # Fast path - no trace: use optimized core calculate
        if trace_fields is None:
            return super().calculate(inputs, strict=strict)

        # Calculate normally
        result = super().calculate(inputs, strict=strict)

        # Build trace: merge inputs + outputs
        merged = dict(inputs)
        merged.update(result)

        trace_data = {}
        for name in trace_fields & set(self._topo_order):
            deps = {dep: merged.get(dep) for dep in self._deps_cache.get(name, set())}
            trace_data[name] = {
                "formula": self._original_expr.get(name, ""),
                "deps": deps,
                "result": result.get(name)
            }

        result["trace"] = trace_data

        if explain_ui:
            result["explain_ui"] = self._human_explain(trace_data)

        return result

    def _human_explain(self, trace_data: Dict) -> str:
        """Human-readable trace explanation."""
        lines = []
        for name in sorted(trace_data):
            info = trace_data[name]
            deps_str = ", ".join(f"{k}={v}" for k, v in info.get("deps", {}).items())
            lines.append(f"{name} = {info['formula']} → {info['result']} ({deps_str})")
        return '\n'.join(lines)

    def calculate_incremental(
        self,
        ictx: IncrementalContext,
        changed_inputs: Dict[str, Any],
        strict: Optional[bool] = None,
        return_stats: bool = False,
        trace_fields: Optional[Set[str]] = None,
        explain_ui: bool = False,
    ) -> Union[Dict[str, Any], Tuple[Dict[str, Any], IncrementalStats]]:
        """Incremental calculation with optional trace."""
        out = super().calculate_incremental(ictx, changed_inputs, strict=strict, return_stats=return_stats)

        if trace_fields is None:
            return out

        # Unpack stats if present
        if return_stats:
            result, stats = out
        else:
            result = out
            stats = None

        # Build trace using current ctx of ictx
        trace_data = {}
        for name in trace_fields & set(self._topo_order):
            deps = {dep: ictx._ctx.get(dep) for dep in self._deps_cache.get(name, set())}
            trace_data[name] = {
                "formula": self._original_expr.get(name, ""),
                "deps": deps,
                "result": ictx._outputs.get(name),
            }

        result["trace"] = trace_data
        if explain_ui:
            result["explain_ui"] = self._human_explain(trace_data)

        return (result, stats) if return_stats else result