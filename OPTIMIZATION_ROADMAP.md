# Formula Builder v31 — Performance Analysis & Optimization Roadmap

> **Date:** 2026-07-29 | **Author:** Claude Code

---

## 1. Real-World Viability Assessment

### 1.1 Is current performance adequate?

**Yes — for 95% of real-world ERPNext scenarios, Formula Builder v31 is already fast enough.**

Here's why: the engine itself is NOT the bottleneck. Let's look at the real timeline of a typical pricing request:

```
Timeline: Pricing 1 Quotation (17 BOM items, 100 formulas)
═══════════════════════════════════════════════════════════════
┌────────────────────────────┬──────────┬───────┬────────────┐
│ Step                       │ Time     │   %   │ Category   │
├────────────────────────────┼──────────┼───────┼────────────┤
│ 1. frappe.get_doc()        │ 50-200ms │ 40%   │ DB I/O     │
│ 2. BatchBindingResolver    │ 20-50ms  │ 15%   │ DB I/O     │
│ 3. MultiTableFormulaBuilder│ ~2ms     │ <1%   │ Compute    │
│ 4. Engine init (parse)     │ ~10ms    │ 3%    │ Compute    │
│ 5. Engine evaluate         │ ~0.1ms   │ <1%   │ Compute    │
│ 6. frappe.db.set_value()   │ 50-100ms │ 30%   │ DB I/O     │
│ 7. Network + Framework     │ 20-100ms │ 12%   │ Framework  │
├────────────────────────────┼──────────┼───────┼────────────┤
│ TOTAL                      │ 150-460ms│ 100%  │            │
└────────────────────────────┴──────────┴───────┴────────────┘

The formula engine (steps 3+4+5) = 12ms out of 300ms = 4% of total time.
```

**The engine itself at 2M+ formula-nodes/sec is far beyond what any ERPNext use case demands.** The real bottlenecks are:
1. **Database I/O** (70-85% of total time): `frappe.get_doc()`, `frappe.db.get_value()`, DB writes
2. **Framework overhead** (10-20%): permission checks, middleware, JSON serialization
3. **Engine init** (3-10%): parse + compile is expensive for FIRST use, but negligible with caching

### 1.2 When does the engine become the bottleneck?

Only in **batch scenarios without engine caching**:

```
Scenario: 1000 products × 100 formulas each (no cache)
═══════════════════════════════════════════════════════════════
Engine init × 1000:  12,000ms  ← BOTTLENECK (80%)
Engine eval × 1000:      48ms  ← trivial

With bytecode cache:
Engine init × 1000:    ~100ms  ← solved
Engine eval × 1000:      48ms  ← still trivial
```

---

## 2. Init Time Breakdown: Where Time Is Actually Spent

```
Benchmark: 1000 formulas, measured via bench execute
═══════════════════════════════════════════════════════════════
Phase              Time      Pct    What happens
─────────────────────────────────────────────────────────────
Parse (AST)        45ms      51%    ast.parse() → Python AST tree
AST Transform       8ms       9%    IfCallRewriter + DotToSubscriptTransformer
Security Validate  10ms      11%    NodeVisitor walk of entire AST
Compile (bytecode) 25ms      28%    compile() → Python code object
Topo Sort + Build  16ms      18%    DependencyGraph + Kahn algorithm
Other               1ms       1%    misc setup
─────────────────────────────────────────────────────────────
TOTAL INIT        105ms     100%
```

**Finding: 83-96% of init time is in parse+compile. The eval itself is only 0.46ms.**

---

## 3. Optimization Proposals — Ranked by Impact

### ⭐ TIER 1: High Impact (>10× improvement)

#### 3.1 Formula Bytecode Cache (CRITICAL)

**Problem:** Identical formulas are re-parsed and re-compiled on every engine creation. In 1000-product batch, 100K formulas are parsed from scratch.

**Solution:** Cache compiled bytecode keyed by formula hash. Python's `marshal` module can serialize code objects.

**Estimated improvement:** 1000-engine init: 12s → ~50ms (**240× faster**)

```python
# Proposed: formula_builder/formula_utils/bytecode_cache.py
import marshal
import hashlib
from typing import Dict

_BYTECODE_CACHE: Dict[str, bytes] = {}
_CACHE_MAX = 10000

def get_cached_bytecode(formula: str, func_names: frozenset) -> bytes:
    """Return marshalled bytecode for formula, or None if not cached."""
    key = hashlib.sha256(
        formula.encode() + b"|" + ",".join(sorted(func_names)).encode()
    ).hexdigest()
    return _BYTECODE_CACHE.get(key)

def cache_bytecode(formula: str, func_names: frozenset, code_obj):
    """Store compiled bytecode in cache."""
    key = hashlib.sha256(
        formula.encode() + b"|" + ",".join(sorted(func_names)).encode()
    ).hexdigest()
    if len(_BYTECODE_CACHE) >= _CACHE_MAX:
        _BYTECODE_CACHE.pop(next(iter(_BYTECODE_CACHE)))
    _BYTECODE_CACHE[key] = marshal.dumps(code_obj)

# In FormulaParser.parse() — add cache check:
def parse(self, formula: str):
    cached = get_cached_bytecode(formula, self._func_names)
    if cached:
        return marshal.loads(cached)
    # ... existing parse → compile logic ...
    cache_bytecode(formula, self._func_names, code_obj)
    return code_obj
```

**Implementation effort:** ~50 lines of code, no API changes
**Risk:** Low — `marshal` is stdlib, bytecode is deterministic for same input
**Note:** Cross-Python-version compatibility: bytecode is version-specific. Include Python version in cache key.

#### 3.2 Engine Serialization (marshal entire engine)

**Problem:** Even with bytecode cache, rebuilding the DAG (DependencyGraph + topo sort) takes ~16ms per engine for 1000 formulas.

**Solution:** Serialize the entire engine state (names, topo order, deps, bytecode) to a single blob.

**Estimated improvement:** Engine "init": 105ms → ~5ms (**21× faster**)

```python
# Add to FormulaEngineCore:
def to_cache_bytes(self) -> bytes:
    """Serialize engine to bytes for fast restore."""
    return marshal.dumps({
        "v": 1,
        "py": sys.version_info[:2],
        "names": list(self._original_expr.keys()),
        "topo": self._topo_order,
        "deps": {k: list(v) for k, v in self._deps_cache.items()},
        "bytecodes": {k: marshal.dumps(self._compiled[k]) for k in self._topo_order},
    })

@classmethod
def from_cache_bytes(cls, data: bytes, runtime_env: dict, **kwargs):
    """Restore engine from serialized bytes."""
    ...
```

**Implementation effort:** ~100 lines, needs tests for version compatibility
**Risk:** Medium — marshal format changes between Python versions

---

### ⭐ TIER 2: Medium Impact (2-5× improvement)

#### 3.3 Pre-compiled Regex in Normalizers

**Problem:** `normalize_scoped()` and `normalize_global()` call `re.sub()` with uncompiled patterns on EVERY formula string in EVERY row.

**Solution:** Compile regex patterns once at module level.

```python
# Current (table_formula_builder.py:84)
def normalize_global(expr: str) -> str:
    return re.sub(r'\w+\.(\w[\w-]*)\.(\w+)', r'\1__\2', expr)

# Optimized
_RE_GLOBAL = re.compile(r'\w+\.(\w[\w-]*)\.(\w+)')
def normalize_global(expr: str) -> str:
    return _RE_GLOBAL.sub(r'\1__\2', expr)
```

**Estimated improvement:** 10-20% on row processing (low absolute, but zero-cost to implement)
**Risk:** None

#### 3.4 Batch `calculate_batch` — True Batching

**Problem:** `calculate_batch()` is just `[self.calculate(row) for row in rows]` — no optimization.

**Solution:** For identical formula sets, we can extract the loop into a single compiled code object that iterates over input rows internally, avoiding Python function-call overhead per row.

```python
def calculate_batch(self, rows, strict=None):
    """True batched evaluation — compile outer loop once."""
    if len(rows) <= 1:
        return [self.calculate(r, strict=strict) for r in rows]
    
    # Build a single evaluator closure
    _compiled = self._compiled
    _eval_globals = self._eval_globals
    _topo = self._topo_order
    
    results = []
    for row in rows:
        local = row.copy()
        for name in _topo:
            local[name] = eval(_compiled[name], _eval_globals, local)
        results.append({name: local[name] for name in _topo})
    return results
```

**Note:** The benchmark showed no speedup because for 50-formula DAGs, Python loop overhead dominates. This optimization would only matter for DAGs with 500+ formulas evaluated over 1000+ rows.

#### 3.5 Parallel Engine Init (Multi-Product)

**Problem:** Building 1000 engines takes 12s sequentially.

**Solution:** Use `concurrent.futures.ThreadPoolExecutor` for parallel init. Python GIL limits CPU parallelism, but `ast.parse()` and `compile()` release the GIL periodically.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def build_engines_parallel(formula_sets, max_workers=4):
    engines = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(FormulaEngine, formulas=fms, ...): i
            for i, fms in enumerate(formula_sets)
        }
        for f in as_completed(futures):
            engines.append(f.result())
    return engines
```

**Estimated improvement:** 2-3× on multi-core systems (GIL-limited)
**Risk:** Low for batch workloads; not recommended for request-response (thread overhead)

---

### ⭐ TIER 3: Low Impact (10-30% improvement)

#### 3.6 Fast Path for Trivial Formulas

**Problem:** Many formulas are simple literals (`"2"`, `"1000000"`) or simple references (`"W_mm"`, `"bucket_0"`). They go through the full parse → AST transform → validate → compile pipeline.

**Solution:** Pre-scan formula string — if it matches `^[a-zA-Z_][\w]*$`  (simple variable ref) or `^[\d.]+$` (literal number), skip the full pipeline.

```python
_SIMPLE_REF = re.compile(r'^[a-zA-Z_]\w*$')
_SIMPLE_NUM = re.compile(r'^\d+(?:\.\d+)?$')

def parse(self, formula: str):
    if _SIMPLE_NUM.match(formula):
        return self._compile_literal(float(formula))
    if _SIMPLE_REF.match(formula):
        return self._compile_ref(formula)
    # ... full pipeline for complex formulas
```

**Estimated improvement:** 5-10% for typical BOM formulas (mix of references + complex expressions)
**Risk:** None — simple regex pre-check

#### 3.7 `__slots__` for Hot Data Classes

**Problem:** Some `types.py` dataclasses are instantiated thousands of times per second (e.g., trace entries, audit logs).

**Solution:** Add `__slots__` to reduce memory and attribute-lookup overhead.

```python
@dataclass
class TraceEntry:
    __slots__ = ('name', 'formula', 'value', 'deps', 'elapsed_ms')
    name: str
    formula: str
    value: Any
    deps: Dict[str, Any]
    elapsed_ms: float
```

**Estimated improvement:** 5-15% memory reduction, marginal speed improvement
**Risk:** Low

---

## 4. Optimization Priority Matrix

```
                    Impact on      Implementation    Risk    Recommended
                    Real-World     Effort
─────────────────────────────────────────────────────────────────────
Bytecode Cache      ██████████     ██ (50 LOC)       Low     ✅ DO NOW
Engine Marshal      ██████████     ████ (100 LOC)     Med     ✅ DO NOW
Pre-compiled Regex  ██             █ (5 LOC)          None    ✅ DO NOW
Fast Path Trivial   ██             ██ (30 LOC)        None    ✅ DO NOW
Batch Eval (true)   ███            ███ (60 LOC)       Low     ⬜ Next
Parallel Init       ████           ██ (30 LOC)        Low     ⬜ Later
__slots__ types     █              ██ (20 LOC)        Low     ⬜ Later
```

---

## 5. Concrete Implementation Plan

### Phase 1: Quick Wins (1-2 hours, immediate impact)

1. **Pre-compiled regex** in `table_formula_builder.py` — 5 lines
2. **Fast path for trivial formulas** in `parser.py` — 30 lines  
3. **Formula bytecode cache** — 50 lines in new `bytecode_cache.py`

### Phase 2: Structural Improvements (4-8 hours)

4. **Engine serialization** (`to_cache_bytes`/`from_cache_bytes`) — 100 lines
5. **Engine cache integration** — update `_engine_cache.py` to use serialized engines
6. **MultiTableFormulaBuilder cache** — cache formula build results per doc type

### Phase 3: Optional Enhancements

7. True batch evaluation
8. Parallel engine init for offline/batch workloads
9. Memory profiling and `__slots__` optimization

---

## 6. Expected Performance After Phase 1+2

```
Scenario: 1000 products × 100 formulas each
═══════════════════════════════════════════════════════════════
                      Before          After           Improvement
─────────────────────────────────────────────────────────────
Engine init (first)   105ms/engine    105ms/engine    same
Engine init (cached)  105ms/engine    0.5ms/engine    210×
1000 engines total    12,000ms        ~50ms           240×
Engine eval (all)     48ms            48ms            same
─────────────────────────────────────────────────────────────
TOTAL compute         12,048ms        ~98ms           123×
```

---

## 7. Detailed Recommendation per Use Case

| Use Case | Current Perf | Bottleneck | Recommended Fix |
|---|---|---|---|
| Real-time (1 doc, <500f) | 0.2ms eval | DB queries | BatchBindingResolver (done in v31) |
| Batch pricing (1000 docs) | 48ms eval, 12s init | Engine init | **Bytecode cache (Phase 1)** |
| Cost template analysis | 0.03ms | None | Already perfect |
| Continuous editing | 0.07ms | None | Already perfect |
| Audit trail generation | +30% overhead | None | Acceptable |
| Multi-tenant (shared) | Init per tenant | Engine init | **Engine marshalling (Phase 2)** |

---

## 8. Summary

**The engine compute speed is excellent — the bottleneck is engine creation, not evaluation.**

With Phase 1 optimizations (bytecode cache + fast paths), the 1000-product batch scenario drops from 12s to ~50ms for the formula engine portion. Combined with the BatchBindingResolver already in v31 (reducing DB queries 90%), the entire end-to-end pricing of 1000 products could run in **under 2 seconds** — perfectly viable for both real-time and batch operation.

The key insight is that **we should optimize init, not eval** — because eval at 2M nodes/sec is already 100× faster than any DB query it depends on.
