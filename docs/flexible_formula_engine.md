# FlexibleFormulaEngine — Tính nhiều bảng trong một DAG

Engine cấp cao, gộp **nhiều child table + công thức cấp header** vào **một lượt tính duy nhất**, có sắp thứ tự phụ thuộc. Là cầu nối giữa `FormulaEngine` (lõi) và chứng từ ERP thật (Sales Order, Quotation, BOM…).

- **File:** `formula_builder/flexible_formula_engine.py`
- **Class:** `FlexibleFormulaEngine`, `EngineConfig`, `ChildTableConfig`, `CalculationResult`, `ERPNextAdapter`
- **Không phụ thuộc `frappe`** — dùng được ngoài bench, test được không cần site
- **Không tự viết lại engine** — bọc (composition) một `FormulaEngine`, ⛔ **không kế thừa**

---

## 1. Khi nào dùng

| Dùng khi | ⛔ Không dùng khi |
|---|---|
| Có **nhiều dòng** cùng một công thức (bảng dòng hàng, thuế, phụ phí) | Chỉ có vài biến rời rạc |
| Cần **cộng dồn lên header** từ các dòng | Công thức độc lập, không phụ thuộc nhau |
| Cần **một thứ tự tính** đúng cho cả bảng + header | Cần chạy trên Frappe DocType mà chưa có adapter |
| Cần **UI phản ứng** (sửa 1 ô, tính lại phần bị ảnh hưởng) | |

---

## 2. Kiến trúc — bọc, ⛔ không kế thừa

```
FormulaEngineCore      (engine_core.py)    ← lõi: parser, DAG, eval, an toàn
   └─ FormulaEngineTrace   (engine_trace.py)
        └─ FormulaEngineAudit  (engine_audit.py)
             └─ FormulaEngine      (engine_public.py)   ← API công khai của lõi

FlexibleFormulaEngine  (flexible_formula_engine.py)     ← ⛔ KHÔNG kế thừa lớp nào
   └── tự tạo & gọi 1 FormulaEngine bên trong
```

**Vì sao bọc mà không kế thừa:** nhờ vậy engine giữ được **toàn bộ** tính năng của lõi (DAG, topo sort, an toàn, ngân sách thao tác, ghim độ chính xác…) mà ⛔ không phải chép lại. Sửa lõi thì engine hưởng luôn.

**Hệ quả cần nhớ:** engine **dựng lại** một `FormulaEngine` mỗi lần tính, vì công thức phụ thuộc dữ liệu đầu vào (xem §3). Đây là chủ ý, ⛔ không phải lãng phí.

### Thứ tự tính = DAG

Thứ tự **⛔ không phải thứ tự dòng**, cũng ⛔ không phải thứ tự khai báo — lõi dựng **đồ thị phụ thuộc** rồi sắp **topo**. Nên `subtotal` luôn tính trước `grandtotal` dù khai báo thứ tự nào.

### Số lượt tính — 1 hay 2, tuỳ cấu hình

Mặc định là **1 lượt**. Engine chỉ chạy thêm **lượt hai có mục tiêu** khi cấu hình **thật sự** có công thức đọc dữ liệu bảng dòng (dạng `sum(r.get('amount',0) for r in items)`).

| Cấu hình | Số lượt chạy | Vì sao |
|---|---|---|
| ⛔ Không có `child_tables` (chỉ `global_formulas` + biến scalar) | **1** | Không có bảng dòng nào để đọc ⇒ ⛔ không thể có consumer |
| Có bảng, nhưng header tham chiếu **biến dòng** (`K1 + K2`) | **1** | Đã có cạnh DAG tường minh, ⛔ không cần lượt hai |
| Có bảng, header **đọc `output_field`** của dòng | **2** | Phải đợi bảng tính xong mới đọc được — xem §6 |

*(Số đo thật — đếm số lần dựng `FormulaEngine` cho mỗi loại cấu hình.)*

Lượt hai **⛔ không chạy lại toàn bộ**: nó chỉ nhận đúng **công thức đọc-dòng** cộng **mọi công thức nằm sau chúng** trong DAG (`grandtotal = subtotal + …` phải tính lại theo, kẻo lỗi chỉ chạy từ chỗ này sang chỗ khác). Các công thức còn lại giữ nguyên kết quả lượt 1.

> ✅ **Vì sao an toàn cho cấu hình cũ:** điều kiện kích hoạt là *"có ít nhất một công thức nhắc tới `table_key`"*. Cấu hình ⛔ không dùng mẫu đó ⇒ tập consumer **rỗng** ⇒ thoát sớm, **không dựng engine thứ hai**, kết quả **y hệt** trước bản vá. Đã đo: cấu hình kiểu `alumglass` B6 (chỉ `global_formulas`, `child_tables=[]`) chạy **đúng 1 lượt**.

---

## 3. Hai chế độ tính — điểm cốt lõi

Đây là thứ dễ hiểu sai nhất, và cũng là lý do engine tồn tại.

| | `calculate()` | `create_incremental_context()` |
|---|---|---|
| **Cách xử lý cột của dòng** | **Thay bằng giá trị literal** vào công thức | **Đổi tên cột thành biến** |
| `qty * price` với dòng `K1` (qty=2, price=100) | thành `2 * 100` | thành `qty_K1 * price_K1` |
| Dùng cho | Tính hàng loạt, lưu DB | **UI phản ứng**, sửa 1 ô tính lại |
| Kết quả | `CalculationResult` | `(IncrementalContext, FormulaEngine, name_to_table)` |

**Vì sao chế độ 2 phải khác:** nếu ghim `2 * 100` thành literal thì khi người dùng sửa `qty` thành 5, công thức **⛔ không còn biến nào** để cập nhật — máy ⛔ không biết chỗ nào cần thay. Giữ tên biến (`qty_K1`) thì việc sửa 1 ô trở thành gán 1 biến, và máy tính lại **đúng phần bị ảnh hưởng** (§8).

> ⚠️ **Hai chế độ phải cho cùng một kết quả.** Trước đây chúng ⛔ không như vậy: `create_incremental_context()` chỉ truyền 4/13 tham số cấu hình nên **rơi mất `rounding_policy`** ⇒ UI hiện một số, lưu xuống một số khác. **Đã vá** — nay cả hai đường dùng chung một bộ tham số.

---

## 4. Cấu trúc dữ liệu

### `ChildTableConfig` — cấu hình một bảng

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `table_key` | `str` | ✅ | Khoá của bảng trong `inputs` (vd `"items"`) |
| `formula_field` | `str` | ✅ | Field chứa **công thức** của từng dòng |
| `id_field` | `str` | ✅ | Field định danh dòng → thành **tên biến** (`K1`, `K2`…) |
| `row_fields` | `List[str]` | — | Cột đưa vào công thức. **Rỗng = tự dò** mọi cột số/bool |
| `output_field` | `str` | — | Field ghi kết quả trở lại dòng (sửa **tại chỗ**) |
| `prefix` | `str` | — | Tiền tố tên biến, dùng khi 2 bảng có `id_field` trùng nhau |
| `skip_empty_formula` | `bool` | — | `True` (mặc định) = bỏ qua dòng trống; `False` = báo lỗi |
| `assertions` | `List[dict]` | — | Ràng buộc riêng của bảng (§9) |

### `EngineConfig` — cấu hình chung

| Trường | Kiểu | Mặc định | Mô tả |
|---|---|---|---|
| `child_tables` | `List[ChildTableConfig]` | `[]` | Các bảng |
| `global_formulas` | `List[dict]` | `[]` | Công thức cấp header: `{"name":..., "formula":...}` |
| `extra_context` | `Dict` | `{}` | Biến tĩnh; **`inputs` ghi đè được** |
| `on_error` | `"raise"`/`"null"`/`"default"` | `"default"` | Cách xử lý lỗi (§10) |
| `default_value` | `Any` | `0` | Giá trị thay thế khi `on_error="default"` |
| `deterministic` | `bool` | `True` | `True` ⇒ **chặn** `now`/`today`, `unique` sắp xếp ổn định |
| `max_operations` | `int` | `None` | Ngân sách thao tác (chống công thức bùng nổ) |
| `rounding_policy` | `Dict[str, dict]` | `{}` | `{"tên_biến": {"decimals": 2}}` |
| `assertions` | `List[dict]` | `[]` | Ràng buộc toàn cục |
| `custom_functions` | `Dict[str, Callable]` | `{}` | Hàm riêng — **đè được hàm có sẵn** của lõi |
| `input_fields` / `output_fields` | `List` | `[]` | Lược đồ vào/ra (metadata) |
| `strict` | `bool` | `False` | Bật kiểm tra biến bắt buộc |

> ⚠️ `custom_functions` **đè** `BASE_FUNCS` của lõi. Đây là cơ chế để app tự định nghĩa lại một hàm (ví dụ `roundup` theo ngữ nghĩa Excel) mà ⛔ không phải sửa lõi.

### `CalculationResult` — kết quả trả về

```python
r = engine.calculate(inputs)

r.values            # {tên: giá trị} — TẤT CẢ (kể cả biến dòng K1, K2)
r.row_results       # {"items": {"K1": 200, "K2": 150}} — khoá KHÔNG có prefix
r.errors            # {tên: thông báo lỗi}
r.warnings          # ["tên_assertion: thông báo"] — ràng buộc mức WARNING

r.get("subtotal")            # lấy 1 giá trị
r.table("items")             # {"K1": 200, "K2": 150}
r.to_frappe_update(["subtotal", "grandtotal"])   # dict sẵn sàng cho db.set_value
```

---

## 5. Ví dụ 1 — Cơ bản

```python
from formula_builder.flexible_formula_engine import (
    FlexibleFormulaEngine, EngineConfig, ChildTableConfig,
)

engine = FlexibleFormulaEngine(EngineConfig(
    child_tables=[ChildTableConfig(
        table_key    = "items",
        formula_field= "formula",      # cột chứa công thức của từng dòng
        id_field     = "line_ref",     # "K1"/"K2" → tên biến
        row_fields   = ["qty", "price"],
        output_field = "amount",
    )],
    global_formulas=[
        {"name": "subtotal",   "formula": "K1 + K2"},        # ← xem §6
        {"name": "grandtotal", "formula": "subtotal * 1.1"},
    ],
))

result = engine.calculate({"items": [
    {"line_ref": "K1", "qty": 2, "price": 100, "formula": "qty * price"},
    {"line_ref": "K2", "qty": 3, "price": 50,  "formula": "qty * price"},
]})
```

Kết quả **thật** (đã chạy kiểm):

```python
result.values       # {"K1": 200, "K2": 150, "subtotal": 350, "grandtotal": 385.00000000000006}
result.row_results  # {"items": {"K1": 200, "K2": 150}}
result.table("items")   # {"K1": 200, "K2": 150}
```

⚠️ `385.00000000000006` ⛔ không phải lỗi — dấu phẩy động nhị phân. Cần tiền đẹp thì dùng `rounding_policy` (§7).

---

## 6. Header đọc `output_field` của dòng — nay **chạy được**, nhưng vẫn **giòn**

Đây là **cái bẫy nguy hiểm nhất** của engine. Đọc kỹ trước khi viết công thức header.

### Đã vá — nhưng hiểu đúng bản chất

Trước đây mẫu dưới đây **luôn sai**, và nay **đã chạy đúng**:

```python
global_formulas=[{"name": "subtotal", "formula": "sum(r.get('amount',0) for r in items)"}]
```

| Lần gọi | **Trước bản vá** | **Sau bản vá** | Đúng phải là |
|---|---|---|---|
| 1 | **0** ❌ | **350** ✅ | 350 |
| 2 (dùng lại cùng đối tượng dòng) | **350** — đúng **do may** | **350** ✅ | 350 |
| 3 (`qty` K1 sửa thành 10) | **350** ❌ **số CŨ** | **1150** ✅ | 1150 |

Đối chứng cách viết bền (`K1 + K2`) cho cùng ca 3: **1150** — khớp.

**Vì sao trước đây sai:** `output_field` được ghi vào dòng **sau khi** lượt DAG duy nhất đã chạy xong. Nhìn từ trong công thức, `r.get('amount')` ⛔ chưa có gì ⇒ trả `0`. Lần gọi sau thì dòng (vốn bị sửa tại chỗ) còn **số của lần trước** ⇒ trả số cũ.

**Vì sao nay đúng:** engine phát hiện công thức này **đọc bảng dòng**, nên chạy thêm **lượt hai** chỉ cho nó — lúc đó bảng đã tính xong và `output_field` đã có giá trị (§2).

### ⚠️ Vì sao vẫn nên viết theo biến dòng

Bản vá làm mẫu này **chạy đúng**, ⛔ không làm nó **bền**. Còn nguyên hai chỗ giòn:

| Chỗ giòn | Hậu quả |
|---|---|
| ⛔ Chỉ đọc được `output_field` của bảng **đã tính xong trong cùng lượt** | Đọc `output_field` của bảng **khác** vẫn ra **0** — ⛔ không có lượt hai xếp hàng giữa hai bảng |
| Tên cột trong `.get('amount', …)` phải khớp **chính xác** `output_field` | Đổi một trong hai (ví dụ `amount` → `line_amount`) là **im lặng trả về 0** |

Thêm nữa, mẫu này **⛔ không có cạnh DAG tường minh**: engine phải "đoán" qua việc dò định danh trùng tên bảng. Tham chiếu biến dòng thì quan hệ phụ thuộc **hiện ngay trên đồ thị**, và `get_dependency_graph()` nhìn thấy (§14).

### ✅ Cách viết bền

```python
# Tham chiếu biến dòng — tên = id_field của dòng
global_formulas=[
    {"name": "subtotal", "formula": "K1 + K2"},
]
```

Nhiều dòng, ⛔ không biết trước số dòng ⇒ đặt tên biến rõ ràng bằng `prefix` rồi cộng dồn ở lớp gọi, hoặc dùng công thức dòng để tự cộng (`items.py`):

> **Quy tắc:** ưu tiên **đặt tên biến** và tham chiếu tên. `output_field` là **đầu ra để lưu/ghi lại**; đọc lại nó chỉ nên là **lối thoát hiểm** cho công thức cũ, ⛔ không phải cách viết mặc định.

---

## 7. Ví dụ 2 — `rounding_policy` và `custom_functions`

```python
engine = FlexibleFormulaEngine(EngineConfig(
    global_formulas=[{"name": "total", "formula": "qty * rate"}],
    rounding_policy={"total": {"decimals": 0}},        # làm tròn 0 chữ số
))
engine.calculate({"qty": 3, "rate": 2.6}).get("total")   # → 8.0
```

Đường **UI phản ứng** phải cho **cùng** kết quả:

```python
ctx, core, _ = engine.create_incremental_context({"qty": 3, "rate": 2.6})
ctx.outputs.get("total")     # → 8.0   (khớp calculate())
```

> Trước đây đường thứ hai ra **7.800000000000001** vì rơi mất `rounding_policy`. Đã vá.

**Hàm riêng, đè hàm lõi:**

```python
import math

def roundup_excel(x, d=0):          # ROUNDUP kiểu Excel: làm tròn RA XA 0
    f = 10 ** int(d)
    s = x * f
    return (math.ceil(s) if s >= 0 else math.floor(s)) / f

EngineConfig(custom_functions={"roundup": roundup_excel}, ...)
```

> ⚠️ `custom_functions` **đè** `BASE_FUNCS`. Hàm cùng tên trong lõi bị thay **hoàn toàn** — trùng tên ⛔ không có nghĩa là trùng hành vi, nên phải kiểm lại ngữ nghĩa trước khi đè.

---

## 8. Ví dụ 3 — UI phản ứng (`create_incremental_context`)

```python
ctx, core, name_to_table = engine.create_incremental_context({"items": [...])
# ctx.outputs : {"K1": 200, "K2": 150, "subtotal": 350, "grandtotal": 385.00000000000006}
# name_to_table : {"K1": "items", "K2": "items"}   ← biến nào thuộc bảng nào
```

Quy ước tên biến cột: **`{cột}_{id_dòng}`** → `qty_K1`, `price_K1`.

**Sửa 1 ô rồi tính lại:**

```python
out, stats = core.calculate_incremental(ctx, {"qty_K1": 5}, return_stats=True)

out     # {"K1": 500, "K2": 150, "subtotal": 650, "grandtotal": 715.0000000000001}
stats   # total=4  changed=1  affected=3  skipped=1
```

`stats` cho thấy máy **chỉ tính lại phần bị ảnh hưởng** (`K2` được bỏ qua).

> ⚠️ `ctx.patch(tên, giá_trị)` **chỉ gán biến**, ⛔ **không tính lại**. Muốn ra số mới phải gọi `calculate_incremental()`. Nhầm chỗ này thì UI hiện số cũ mà ⛔ không báo lỗi.

---

## 9. Ví dụ 4 — Nhiều kịch bản

```python
results = engine.multi_scenario(
    base_inputs = {"items": [...]},
    scenarios   = {
        "base":   {},
        "gapdoi": {"items": [{"line_ref": "K1", "qty": 8, ...}, ...]},
    },
)
results["base"].get("subtotal")     # 350
results["gapdoi"].get("subtotal")   # 950
```

Mỗi kịch bản nhận **bản sao** dữ liệu dòng (chỉ với bảng có `output_field`), nên kịch bản sau ⛔ không nhìn thấy kết quả kịch bản trước. Engine được **tái dùng** khi các kịch bản cho ra cùng bộ công thức; đổi dữ liệu dòng ⇒ tự dựng engine mới.

---

## 10. Ràng buộc (`assertions`)

Kiểm tra điều kiện **sau khi tính xong**. ⛔ **Không bao giờ thay đổi giá trị đã tính** — chỉ ghi nhận.

```python
EngineConfig(
    global_formulas=[{"name": "k", "formula": "q - 5"}],
    assertions=[{
        "name":     "duong",
        "expr":     "k > 0",
        "message":  "k phải dương",
        "severity": "WARNING",          # hoặc "ERROR"
    }],
)
```

| `severity` | Đi vào | Có `raise` không |
|---|---|---|
| `WARNING` | `result.warnings` | ⛔ Không bao giờ |
| `ERROR` | `result.errors` | Chỉ khi `on_error="raise"` |

Kết quả thật (`q=3` ⇒ `k=-2`, vi phạm):

```python
result.get("k")   # -2                          ← giá trị ⛔ KHÔNG bị đổi
result.warnings   # ["duong: k phải duong"]     ← severity WARNING
result.errors     # {}                          ← ⛔ không thành lỗi
```

Với `severity="ERROR"` + `on_error="default"`: vào `errors`, **⛔ không raise**, giá trị vẫn `-2`.

Hai trường hợp **tự bỏ qua** (⛔ không báo oan): assertion nhắc biến chưa có, và assertion `depends_on` chưa thoả.

---

## 11. Ký tự HTML trong công thức

Công thức đi qua đường HTML (dán từ web/Word, hoặc Frappe escape khi hiển thị) có thể tới engine dưới dạng `a &gt; b`. Engine **tự gỡ** ở cửa vào.

```python
EngineConfig(global_formulas=[{"name": "kq", "formula": "a &gt; b"}])
engine.calculate({"a": 10, "b": 5}).get("kq")    # → True
```

| Công thức gõ | Chạy được |
|---|---|
| `a &gt; b` · `a &lt; b` · `a &gt;= b` · `a &lt;= b` | ✅ |
| `IF(a &gt;= b, a, b)` · `a &gt; b and b &lt; c` | ✅ |
| `a&nbsp;+&nbsp;b` | ✅ (đưa `\xa0` về khoảng trắng thường) |
| `“x”` (nháy cong dán từ Word) | ✅ (đưa về nháy thẳng) |
| `&#999…9;` (charref số hỏng, > 4300 chữ số) | ✅ bị thay bằng `U+FFFD`, ⛔ **không** kéo theo `&gt;` cùng công thức bị bỏ quên |

**Vì sao phải gỡ ở lõi, ⛔ không chỉ ở lớp hiển thị:** bộ dò phụ thuộc nhận diện định danh bằng `[a-zA-Z_]\w*`. Chuỗi `a &gt; b` chứa định danh **`gt`**; `&lt;` chứa **`lt`**; `&amp;` chứa **`amp`**. Nếu ai đó đặt tên công thức là `gt`/`lt`/`amp` thì sẽ sinh **cạnh phụ thuộc MA** ⇒ sai thứ tự tính ⇒ **sai số im lặng**. Gỡ entity ⛔ không phải việc thẩm mỹ.

⚠️ **Charref số hỏng — một lỗi im lặng đã bịt (2026-10-12):** `html.unescape` ném `ValueError` khi gặp charref **số** dài quá ngưỡng `sys.set_int_max_str_digits` (mặc định 4300 chữ số) — nó đổi chuỗi sang `int` **trước** khi kịp kiểm giá trị có nằm trong dải Unicode hay không. Bản đầu nuốt lỗi rồi **giữ nguyên cả chuỗi**: một charref hỏng nằm ở bất kỳ đâu khiến `&gt;` **cùng công thức** ⛔ không được gỡ ⇒ công thức chạy **sai im lặng**, ⛔ không lỗi nào nổi lên. Nay charref hỏng bị vô hiệu trước (`U+FFFD`; charref chỉ phình ra bằng số 0 thì bỏ số 0 — ⛔ không đổi giá trị) rồi gỡ entity **lại**. ⛔ Đây ⛔ không phải chuyện `&` trần: `AT&T`, `a&b`, `&&`, `&#`, `&zzz;`, `&gt` … `html.unescape` trả về bình thường, ⛔ không ca nào ném.

**Hai hàm dùng được:**

```python
from formula_builder.formula_utils import html_unescape_formula, html_escape_formula
```

### Chiều RA giao diện — quan trọng

⛔ **Đừng escape ở Python rồi để JS escape lần nữa.** `formula_builder.js` đã có `_esc()` escape `& < > "` trước khi đổ vào `innerHTML`. Escape thêm một lần nữa ⇒ người dùng **đọc thấy** `a &amp;gt; b`.

| Loại | Xử lý |
|---|---|
| **DỮ LIỆU** — `ExplainStep.formula`, `TraceNode.formula` | Giữ **RAW**; JS escape khi hiển thị |
| **THÔNG BÁO** — `FormulaError.formula` → hộp thoại Frappe | **Escape ở Python** (Frappe ⛔ không tự escape `msgprint`) |

`explain()`, `explain_all()`, `preview_resolved_formulas()` có tham số `escape_html` (**mặc định `False`** = RAW). Nơi render thẳng HTML mà ⛔ không tự escape (template in ấn, markdown) thì truyền `escape_html=True`.

---

## 12. Lỗi và cảnh báo

```python
EngineConfig(on_error="default", default_value=0)
```

| `on_error` | Công thức lỗi ⇒ | Ghi vào |
|---|---|---|
| `"raise"` | **Ném** `FormulaError` | — |
| `"null"` | giá trị = `None` | `result.errors` |
| `"default"` | giá trị = `default_value` | `result.errors` |

Engine ⛔ **không** suy lỗi từ "giá trị là `None`" — công thức **hợp lệ** trả `None` (thiếu khoá trong `row.get('x')`, `min()` trên list rỗng) ⛔ **không** bị báo lỗi oan.

---

## 13. Tích hợp Frappe

`ERPNextAdapter` là lớp trừu tượng (ABC) đóng gói mọi thứ phụ thuộc Frappe, để engine chính giữ được tính **không phụ thuộc frappe**. Cần tự viết lớp con:

```python
from formula_builder.flexible_formula_engine import ERPNextAdapter

class FrappeERPNextAdapter(ERPNextAdapter):
    def get_doc(self, doctype, docname):
        return frappe.get_doc(doctype, docname)

    def get_global_vars(self):        # biến toàn cục (loại CONSTANT)
        ...

    def rows_to_dicts(self, doc, child_field):
        rows = doc.get(child_field) or []
        return [r.as_dict() if hasattr(r, "as_dict") else dict(r) for r in rows]
```

Sau đó `adapter.calculate_doc(engine=..., doc=..., child_table_map=..., scalar_fields=..., output_scalar=...)` sẽ: gom input từ doc → tính → ghi scalar lên doc → ghi kết quả dòng về từng row.

> ⚠️ Ví dụ `global_formulas` trong docstring của `ERPNextAdapter` dùng `sum(r.get('amount',0) for r in items)`. Mẫu đó **nay chạy đúng** (nhờ lượt hai — §6), nhưng vẫn **giòn**: phụ thuộc tên cột khớp chính xác `output_field`, và ⛔ không đọc được bảng khác. Ưu tiên tham chiếu biến dòng (`K1 + K2`).

**Dùng trong hook:**

```python
# hooks.py
doc_events = {
    "Sales Order": {"before_save": "myapp.pricing.recalculate_doc"},
}
```

---

## 14. Tra cứu API

| Hàm | Trả về | Việc |
|---|---|---|
| `calculate(inputs)` | `CalculationResult` | Tính toàn bộ: bảng + header |
| `create_incremental_context(inputs)` | `(ctx, core, name_to_table)` | Dựng ngữ cảnh cho UI phản ứng |
| `validate_formulas(inputs, extra_known_vars=None)` | `{tên: [lỗi]}` | Kiểm cú pháp **tĩnh**, ⛔ không tính |
| `explain(tên, inputs, escape_html=False)` | `ExplainResult` | Soi từng bước tính của **một** công thức |
| `explain_all(inputs, escape_html=False)` | `{tên: ExplainResult}` | Soi tất cả |
| `multi_scenario(base_inputs, scenarios)` | `{kịch_bản: CalculationResult}` | Nhiều kịch bản "nếu…thì…" |
| `get_dependency_graph(inputs)` | `{tên: [phụ_thuộc]}` | Dữ liệu vẽ đồ thị phụ thuộc |
| `preview_resolved_formulas(inputs, escape_html=False)` | `[{name, formula, original, changed}]` | Xem công thức **sau khi** thay giá trị |

**Ví dụ kết quả thật:**

```python
engine.preview_resolved_formulas({"items":[{"line_ref":"K1","qty":2,"price":100,"formula":"qty * price"}]})
# [{"name":"K1","formula":"2 * 100","original":"qty * price","changed":True},
#  {"name":"subtotal","formula":"K1 + K2","original":"K1 + K2","changed":False}, ...]

engine.get_dependency_graph({...})
# {"K1": [], "subtotal": [], "vat": ["subtotal"], "grandtotal": ["subtotal", "vat"]}

engine.validate_formulas({"items":[{"line_ref":"K1","qty":2,"price":100,"formula":"qty * * price"}]})
# {"K1": ["Cú pháp không hợp lệ: invalid syntax (dòng 1, cột 7)"], ...}
```

---

## 15. Cạm bẫy — danh sách kiểm

| # | Cạm bẫy | Cách tránh |
|---|---|---|
| 1 | Header đọc `output_field` của dòng | Nay **chạy được** nhưng **giòn** — ưu tiên **biến dòng** (`K1 + K2`), §6 |
| 2 | Dùng lại cùng đối tượng dòng cho lần tính sau | Nay **đúng** (dòng bị mutate in-place được ghi lại) — nhưng vẫn nên truyền **dict mới** |
| 3 | `ctx.patch()` rồi tưởng số đã cập nhật | Phải gọi `calculate_incremental()` — §8 |
| 4 | Hai bảng có `id_field` trùng nhau | Đặt `prefix` khác nhau |
| 5 | Tên công thức trùng `table_key` | Engine **báo lỗi** ngay (`ValueError`) |
| 6 | Hai công thức cùng `name` | Cái sau **ghi đè im lặng** — tên phải duy nhất |
| 7 | Escape HTML hai lần | Giữ RAW ở Python, để JS escape — §11 |
| 8 | Đè hàm lõi qua `custom_functions` mà ⛔ không kiểm ngữ nghĩa | So lại hành vi, nhất là với số âm |
| 9 | Quên `on_error="raise"` khi cần chặn lỗi cứng | Lỗi bị **nuốt** vào `result.errors` |

**Thực hành tốt**

- Đặt `id_field` là thứ **duy nhất & ổn định** (`line_ref`), ⛔ đừng dùng `idx` (đổi khi chèn/xoá dòng).
- Dùng `validate_formulas()` trong `before_save` để chặn công thức hỏng trước khi lưu.
- Dùng `preview_resolved_formulas()` khi công thức ra sai — xem ngay nó đã bị thay gì.
- Bật `deterministic=True` (mặc định) cho mọi thứ liên quan tiền.
- `rounding_policy` cho các biến tiền để tránh `385.00000000000006`.

---

## 16. Nhật ký sửa lỗi

Các lỗi của chính engine này đã được sửa, kèm bổ sung xử lý HTML entity.

| Lỗi | Trước | Sau |
|---|---|---|
| Hai đường tính lệch nhau | `calculate()` = `8.0`, incremental = `7.800000000000001` | **Cả hai = `8.0`** |
| Dựng engine thừa | **2** engine cho 1 lần chạy sạch | **1** |
| Công thức hợp lệ trả `None` | Báo lỗi **oan** | ⛔ Không báo |
| `assertions` | Được khai, **⛔ chưa bao giờ chạy** | **Chạy thật** (§10) |
| Cột chỉ có ở dòng sau | Bị **bỏ sót** | Nhận diện đủ |
| `&nbsp;`, nháy cong | **Crash** `SyntaxError: U+00A0` | Chạy được |
| `&gt;` / `&lt;` | `SyntaxError` | Chạy được |
| Header đọc `output_field` của dòng | **0** (lần đầu), hoặc **số CŨ** (lần sau) — sai im lặng ở tiền | **Đúng** — chạy thêm lượt hai (§6) |
| Assertion kiểm số của công thức đọc-dòng | Báo lỗi **oan** (`subtotal > 0` thấy 0) | Chạy lại ở lượt hai ⇒ ⛔ hết oan |

**Còn giòn, chưa sửa** (cần job riêng): công thức header ⛔ **vẫn không đọc được `output_field` của một bảng khác** trong cùng lượt tính — lượt hai chỉ xếp hàng cho bảng đã tính xong, ⛔ không giải được thứ tự phụ thuộc **giữa hai bảng**. Cách viết bền vẫn là tham chiếu biến dòng (§6).

**Ghi chú kỹ thuật:** việc dò "công thức nào đọc bảng dòng" dùng chung hàm `extract_identifiers()` trong `formula_utils/topo.py` với việc dựng cạnh DAG. ⛔ Cố ý **không** cài lại regex ở hai nơi: hai bản song song sẽ trôi lệch nhau ⇒ thứ tự tính theo một bộ cạnh, còn phát hiện "cần tính lại" theo bộ khác ⇒ **sai số im lặng**.
