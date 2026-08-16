# Safe Expression Evaluation — `security/safe_eval.py`

> **Pivot RCE (2026-08-16):** Formula Builder có 3 chỗ `eval()` trần chuỗi
> **user-controlled** (từ `source_config` trên UI) → fix ĐƯA VÀO app qua wrapper
> `safe_eval`. Module mới: `formula_builder/security/safe_eval.py`.
>
> **Nguyên tắc:** validate **1 lần** lúc build/compile (tái sử dụng
> `SecurityValidator`/`FormulaValidator` có sẵn — KHÔNG viết validator trùng),
> eval **nhanh** hot loop trên compiled code object đã qua validate — KHÔNG
> AST-interpreter node-by-node, KHÔNG validate lại mỗi lần eval.

---

## 1. Vấn đề

Trước pivot, 3 config sau đây (đều nằm trong `source_config`, người dùng nhập
trên UI Formula Builder) được đưa thẳng vào `eval()` trần:

| Vị trí | Config | Handler |
| --- | --- | --- |
| `child_table_aggregate` | `filter_expr` (lọc rows) | `api/data_source_registry.py` |
| `conditional` | `branches[].condition` (rẽ nhánh) | `api/data_source_registry.py` |
| mọi source type | `transform.formula` (biến đổi giá trị) | `api/batch_binding_resolver.py` |

Vector tấn công không cần builtin: attribute traversal kiểu
`().__class__.__mro__[1].__subclasses__()` vẫn thoát sandbox dù
`eval(code, {"__builtins__": {}}, scope)` vì literal object tự cung cấp
`__class__`. `safe_eval` chặn ở **tầng AST** trước khi compile.

## 2. Thiết kế

### 2.1 Compile-once / execute-many

```
compile_expression(expr, allowed_functions, policy)  → SafeExpression
  1. strip + ast.parse(mode="eval")                    (SyntaxError → ValueError)
  2. _validate_ast(tree, policy)                       (chặn node/name/attr/call/subscript)
  3. compile(tree)                                     → code object
  4. cache theo (expr, policy.signature())             → lần sau hit, không validate lại

SafeExpression.eval(scope)                             → eval(code, {"__builtins__": {}}, scope)
  - globals cố định rỗng → KHÔNG có builtin thật
  - mọi name/function phải từ scope (locals) do caller đưa vào
```

### 2.2 Policy (`ExpressionPolicy`)

| Tham số | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `allow_attribute` | `True` | cho phép `obj.attr` (vd `row.qty`) |
| `allowed_attributes` | `None` | set khóa trắng → chỉ cho attr trong set; `None` = mọi attr non-dunder |
| `forbid_subscript` | `False` | chặn `obj[...]` (dùng cho `filter_expr`) |
| `forbid_method_calls` | `True` | chặn `obj.method()` |
| `allowed_functions` | `None` | whitelist tên hàm gọi được; `None` = không giới hạn (không khuyến nghị) |
| `forbidden_names` | `_FORBIDDEN_NAMES` | set tên cấm bổ sung |
| `max_subscript_depth` | `5` | giới hạn `a[0][1][2]...` lồng nhau |
| `max_iter_size` | `2**31` | giới hạn list/set/tuple literal |

3 policy cài sẵn:

- `DEFAULT_POLICY` — attr + subscript đều cho phép, chặn method call.
- `FILTER_POLICY` (`forbid_subscript=True`) — `filter_expr` dùng `row.field`,
  không dùng `row['field']`.
- `CONDITION_POLICY` — `conditional` cần subscript (scope dạng dict/list).
- `TRANSFORM_POLICY` — arithmetic + attr đọc cho `transform.formula`.

### 2.3 Chặn ở tầng AST (`_validate_ast`)

- **Node type cấm tuyệt đối:** `Import`, `ImportFrom`, `Exec`, `Eval`,
  `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, `Delete`, `Global`, `Nonlocal`,
  `Await`, `Yield`, `YieldFrom`, `Lambda`, `DictComp`, `SetComp`, `Assign`,
  `AugAssign`, `AnnAssign`, `NamedExpr`.
- **Tên cấm:** `SecurityValidator.FORBIDDEN_NAMES` + `getattr`/`setattr`/`delattr`
  (attribute traversal qua getattr).
- **Dunder attribute:** mọi `.xxx` bắt đầu `__` → chặn (`().__class__`, `x.__globals__`).
- **Method call:** `obj.method()` → chặn khi `forbid_method_calls=True`.
- **Call phức tạp:** call qua subscript/lambda → chặn.
- **Function whitelist:** `allowed_functions` → hàm ngoài danh sách bị chặn.
- **Subscript:** theo `forbid_subscript` + `max_subscript_depth`.

### 2.4 Reuse validator có sẵn

- `_FORBIDDEN_NAMES = SecurityValidator.FORBIDDEN_NAMES | {getattr,setattr,delattr}`.
- `validate_formula_sources(expressions, runtime_env=...)` dùng
  `FormulaParser.parse()` (chính là gate mà `__init__`/`register_formula` dùng:
  normalize + IfCallRewriter + DotToSubscriptTransformer + SecurityValidator +
  genexp + func whitelist) — phục vụ gate cache-restore engine.

### 2.5 Cache

- Key: `(expr, policy.signature())` — mọi tham số chính sách nằm trong signature.
- LRU đơn giản: `_CACHE_MAX = 2048`, lock thread-safe.
- `clear_cache()` gọi khi Formula Builder Settings thay đổi (whitelist hàm).

## 3. Vị trí tích hợp

| Chỗ | Thay đổi |
| --- | --- |
| `api/data_source_registry.py` `_compile_filter_expr()` | validate + compile `filter_expr` (FILTER_POLICY + `get_allowed_funcs()` whitelist) |
| `api/data_source_registry.py` conditional | validate + compile `branches[].condition` (CONDITION_POLICY + `_CONDITION_ALLOWED_FUNCS`) |
| `api/batch_binding_resolver.py` `_apply_transform()` | validate + compile `transform.formula` (TRANSFORM_POLICY + `_TRANSFORM_ALLOWED_FUNCS`) |
| `formula_utils/engine_core.py` `from_cache_bytes()` | gate validate tại restore: recompile toàn bộ từ source đã validate (bytecode serialized KHÔNG tin) |
| `formula_utils/engine_public.py` `from_cache_dict()` | giữ bytecode đã validate từ `__init__`, bỏ overwrite bằng `compiled_serial` |

## 4. Audit eval sites (2026-08-16)

| File:Dòng | Input | User-controlled? | Trạng thái |
| --- | --- | --- | --- |
| `api/data_source_registry.py` filter_expr (~584) | `source_config.filter_expr` | ✅ | ĐÃ VÁ → `safe_eval` FILTER_POLICY |
| `api/data_source_registry.py` condition (~1075) | `source_config.branches[].condition` | ✅ | ĐÃ VÁ → `safe_eval` CONDITION_POLICY |
| `api/batch_binding_resolver.py` transform (~199) | `source_config.transform.formula` | ✅ | ĐÃ VÁ → `safe_eval` TRANSFORM_POLICY |
| `formula_utils/engine_core.py` 776/878/953/1005 | compiled code từ `FormulaParser.parse_with_cache` (đã validate) | ❌ internal | Gate sẵn ở build; thêm gate recompile tại `from_cache_bytes` |
| `formula_utils/engine_public.py` 452 | compiled code từ `__init__`/`parse_with_cache` (đã validate) | ❌ internal | Gate sẵn ở build; bỏ trust `compiled_serial` tại `from_cache_dict` |
| `formula_utils/engine_core.py` `add_assertion` (~674) | `assertion.expr` | config internal, đã qua SecurityValidator | Đã validate từ trước |

**Ghi chú engine:** dù bytecode engine là validated, cache-restore trước đây load
`marshal.loads` trực tiếp → bytecode giả mạo trong cache không qua validate. Đã vá:
`from_cache_bytes` recompile toàn bộ từ `_original_expr` qua `FormulaParser.parse()`
(validate lại source), `from_cache_dict` giữ bytecode `__init__`. Kẻ tấn công có
cache giả mạo cũng chỉ làm engine chạy đúng source đã validate — không chèn bytecode lạ.

## 5. Backward-compat & performance

- **Không đổi API/source_type:** 15 source_type cũ + `config_io` giữ nguyên.
- **106 test standalone pass** (`test_config_io` 14 + `test_platform_source_types` 40
  + `test_fb1_revised` 52) + **37 test `TestSafeEval`** pass.
- **Benchmark:** `~7.4–8.3M nodes/s` (baseline yêu cầu 2.0–2.5M) — override chỉ ở
  chỗ user-controlled (build time), hot loop engine không đổi.
- **Golden 22,717,289** (A2 baseline) không bị ảnh hưởng — không đổi engine math.

## 6. Test bảo mật (mẫu payload)

```python
from formula_builder.security import safe_eval

# Đều phải raise ValueError
for payload in (
    "__import__('os').system('id')",
    "().__class__.__mro__",
    "[].__class__.__base__",
    "eval('1+1')", "exec('x=1')",
    "open('/etc/passwd')", "os.system('id')",
    "lambda x: x", "import os",
    "getattr(obj, 'x')", "'abc'.upper()",
    "(x := 1)", "funcs[0]('x')",
):
    safe_eval.compile_expression(payload)  # ValueError
```

Test đầy đủ: `formula_builder/tests/test_security.py::TestSafeEval` (37 cases).
