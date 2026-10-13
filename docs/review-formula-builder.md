# Nhận xét Formula Builder — bản rà soát kỹ thuật

**Ngày:** 2026-10-12
**Nền rà soát:** nhánh `develop`, HEAD `7c689f0` *"fix lỗi nâng cấp formula builder"*
(14 tệp · +2 979 / −139 dòng). Cây làm việc **sạch** tại thời điểm rà.
**Phiên bản lõi:** `ENGINE_VERSION = "31.0.0"` — `formula_utils/engine_core.py:195`
**Quy mô:** 110 tệp `.py` trong gói · 39 180 dòng toàn kho · 17 tệp test · **520** hàm test

**Cách kiểm:** đọc mã nguồn + **đo bằng máy** (bench Python 3.10.12). Mọi kết luận có số liệu
đều ghi rõ cách đo. Chỗ nào chỉ suy từ đọc mã thì ghi 🔎 để phân biệt với ✅ đo được.

---

## 0. Tóm tắt cho người quyết định

| # | Mức | Vấn đề | Chỗ | Ảnh hưởng hiện tại |
|---|---|---|---|---|
| 1 | 🟡 | Khoá cache engine **thiếu tham số hành vi** (`on_error`, `default_value`, `deterministic`) | `api/_engine_cache.py:28-40`, `:77-107` | Tiềm ẩn — 2 nơi gọi đều dùng mặc định |
| 2 | 🟡 | Docstring cache hứa **nhanh 21×**, đo được **chậm 5×** | `api/_engine_cache.py:1-7` | Sai số liệu đang lưu hành |
| 3 | 🟡 | Bẫy `loadTestsFromModule`: hàm `test_*` cấp module bị **bỏ qua im lặng** | `tests/` | 8 ca regression của bản vá từng vô hình — **đã vá trong commit này** |
| 4 | 🟡 | Khai `requires-python >=3.14` + ruff `py314` nhưng bench chạy **3.10.12** | `pyproject.toml:7,25` | "Xanh trên máy" ⛔ không suy ra "xanh trên CI" |
| 5 | 🟡 | Đăng ký source type có **2 đường**, đường sau **đè im lặng** | `api/source_type_registry.py:520-534`, `api/data_source_registry.py:1482` | Bản vá fingerprint có thể mất tác dụng |
| 6 | 🟡 | 160 `except Exception` + 4 bare `except:` + 7 `except: pass` trong lõi | `formula_utils/`, `api/` | Nuốt lỗi |
| 7 | 🟢 | 7 lệnh `print()` trong **thư viện** | `formula_utils/allocation.py:339-365` | Rác log production |
| 8 | 🟢 | Tài liệu cũ còn ghi v30 trong khi lõi đã v31 | `docs/FINAL_AUDIT_v30.md:1`, `docs/AUDIT_REPORT.md` | Người đọc ⛔ không biết bản nào đúng |
| 9 | 🟢 | `data_source_registry.py` 3 233 dòng; 1 hàm 313 dòng | `:1482` | Khó review |

**Không có lỗi 🔴 nào đang sống.** Bản vá "lượt hai có mục tiêu" đúng thiết kế và đã được
kiểm chứng độc lập (mục 4).

---

## 1. Kiến trúc

### 1.1 Chuỗi kế thừa và quan hệ

```
FormulaEngineCore            engine_core.py    — parse, topo, tính, ghi kết quả
      ↑ kế thừa
FormulaEngineTrace           engine_trace.py   — thêm vết
      ↑ kế thừa
FormulaEngineAudit           engine_audit.py   — thêm kiểm toán
      ↑ kế thừa
FormulaEngine                engine_public.py  — API công khai

FlexibleFormulaEngine        flexible_formula_engine.py
      └── ⛔ KHÔNG kế thừa — **chứa** (composition) một `FormulaEngine` bên trong
```

Điểm này quan trọng và hay bị hiểu nhầm: `FlexibleFormulaEngine` **không** phải lớp con.
Nó là lớp bọc, dựng lại engine con mỗi lần `calculate()`. Hệ quả về hiệu năng ở mục 4.

### 1.2 Các module lớn nhất

| Tệp | Dòng | Ghi chú |
|---|---|---|
| `api/data_source_registry.py` | 3 233 | 19 loại nguồn; `_register_all_to_central_registry` **313 dòng** (`:1482`) |
| `flexible_formula_engine.py` | 1 570 | Hàm dài nhất `create_incremental_context` 90 dòng (`:968`) |
| `formula_utils/engine_core.py` | 1 185 | `__init__` **201 dòng** (`:197`) — hàm dài nhất lõi |
| `formula_utils/types.py` | 912 | `ExplainStep`, `TraceNode`… |
| `formula_utils/allocation.py` | 878 | Có `print()` — xem 🟢 #7 |
| `api/source_type_registry.py` | 813 | Chứa cảnh báo 2 đường đăng ký (viết tốt) |

---

## 2. Điểm mạnh (đã kiểm chứng)

**2.1 — Bản vá "lượt hai có mục tiêu" đúng thiết kế.**
`_second_pass_formulas()` (`flexible_formula_engine.py:786`) chỉ chạy khi cấu hình **thật sự**
đọc bảng dòng, và chỉ trên `consumer ∪ node phía sau` — ⛔ không tính lại cả đồ thị. Lượt 1
⛔ không bị đụng. Số lượt theo cấu hình: ⛔ không có `child_tables` → 1 lượt; có bảng nhưng
header dùng biến dòng → 1 lượt; header đọc `output_field` → 2 lượt. ✅ đo được (1/1/2).

**2.2 — Tách đúng tầng escape HTML.** Dữ liệu (`ExplainStep.formula`, `TraceNode.formula`)
giữ **nguyên bản** vì JS tự escape trước khi `innerHTML`; thông điệp (`FormulaError.formula`
→ `msgprint` của Frappe, vốn **không** escape) được escape ở phía Python
(`engine_public.py:116,179` · `engine_core.py:446,910,1009,1084,1136`). Escape **đúng một
lần, ở tầng hiển thị ngoài cùng** — đây là cách làm đúng.

**2.3 — Cổng validate tại lúc khôi phục cache.** `from_cache_bytes` (`engine_core.py:553`)
**⛔ không tin** bytecode trong payload; nó biên dịch lại toàn bộ từ mã nguồn đã qua
`FormulaParser.parse()` — đúng cổng mà `__init__` dùng (`:672-682`, ghi rõ "PIVOT RCE
2026-08-16"). Đây là quyết định bảo mật đúng, và là lý do hàm này chậm (xem mục 4).

**2.4 — Xử lý charref số quá dài rất chặt.** `normalize.py:57,62,112`: chỉ so **độ dài**
chuỗi chữ số (`_MAX_REF_DIGITS = 20`), ⛔ **không** gọi `int()` — vì `int()` chính là thứ
chạm ngưỡng `sys.set_int_max_str_digits` gây `ValueError`. Và **một** charref hỏng ⛔ không
tắt việc gỡ entity cho **cả** công thức (nếu bỏ qua cả chuỗi thì `&gt;` nằm cùng công thức
cũng ⛔ không được gỡ ⇒ công thức sai **im lặng**).

**2.5 — Khối lượng test lớn.** 520 hàm test / 17 tệp; riêng `test_security.py` **78** ca,
`test_fb1_revised.py` 62 ca.

**2.6 — Tài liệu tính năng mới chất lượng cao.** `docs/flexible_formula_engine.md` 493 dòng,
14 bảng, ⛔ không lỗi cú pháp; có bảng phân biệt rõ 3 trường hợp số lượt tính.

**2.7 — Trung thực về giới hạn.** `README.md:1511` tự ghi header đọc `output_field` của
dòng "nay chạy được nhưng vẫn **giòn** — ưu tiên tham chiếu biến dòng". Đây là cách ghi
đúng: nêu rõ giới hạn thay vì để người dùng tự phát hiện.

---

## 3. Phát hiện

### 🟡 #1 — Khoá cache engine thiếu tham số hành vi

`api/_engine_cache.py:28-40`:

```python
def _make_batch_key(formulas: list, allowed_funcs: dict) -> str:
    sorted_f = sorted(formulas, key=lambda f: f["name"])
    formula_json = json.dumps(sorted_f, sort_keys=True, ensure_ascii=False)
    formula_hash = hashlib.sha256(formula_json.encode("utf-8")).hexdigest()
    func_names = ",".join(sorted(allowed_funcs.keys()))
    func_hash = hashlib.sha256(func_names.encode("utf-8")).hexdigest()
    return f"{formula_hash}:{func_hash}"
```

Nhưng `get_or_create_engine()` (`:77-107`) nhận thêm `on_error`, `default_value`,
`deterministic` — và **⛔ không đưa ba tham số này vào khoá**. Khi cache trúng,
`get_cached_engine()` gọi `FormulaEngine.from_cache_bytes(data, safe_funcs=funcs)`
(`:49`) — **⛔ không truyền `**overrides`**, dù `from_cache_bytes` có hỗ trợ sẵn
(`engine_core.py:557`).

**Hệ quả:** người gọi đầu tiên quyết định hành vi cho mọi người gọi sau. Gọi
`get_or_create_engine(f, on_error="raise")` sau khi đã có bản cache `on_error="default"`
sẽ **nhận về engine `default`** — ⛔ không báo lỗi.

**Hiện tại chưa nổ:** cả 2 nơi gọi (`api/formula_builder.py:230,538`) đều dùng mặc định.
Nhưng chữ ký hàm **hứa** đổi được hành vi, nên đây là bẫy đã lên đạn.

**Cách sửa:** đưa `on_error`, `default_value`, `deterministic` vào chuỗi khoá, **hoặc**
truyền `**overrides` xuống `from_cache_bytes` ở `:49`. Sửa cách thứ hai rẻ hơn nhưng vẫn
phải đưa vào khoá — nếu không, engine `on_error="raise"` sẽ bị dùng lại cho người gọi
`on_error="default"`.

---

### 🟡 #2 — Docstring cache hứa nhanh 21×, đo được **chậm 5×**

`api/_engine_cache.py:1-7`:

> *"Cho phép khởi tạo engine từ cache trong ~5ms thay vì ~100ms (**21x speedup**)."*

✅ **Đo trên chính máy này** (bench Python 3.10.12, 10 công thức):

| Đường | Thời gian |
|---|---|
| Dựng mới `FormulaEngine` | **0,814 ms** |
| `from_cache_bytes` | **4,049 ms** |

Tức cache **chậm hơn 5×**, ⛔ không nhanh hơn 21×. Lý do đã biết và **chính đáng**: cổng
validate tại lúc khôi phục (mục 2.3) biên dịch lại từ mã nguồn, nên `from_cache_bytes`
làm **gần đúng** việc mà dựng mới vẫn làm, rồi cộng thêm chi phí `marshal.loads`.

**Hệ quả thật:** `api/formula_builder.py:230,538` đang đi qua đường cache này cho **mọi**
lần tính trên production. Đây là chi phí thuần, ⛔ không đổi lại được gì.

**Cách sửa, chọn một:**
1. **Bỏ `_engine_cache`** ở 2 nơi gọi, dựng trực tiếp — đơn giản nhất, và nhanh hơn.
2. Giữ cache nhưng sửa docstring cho đúng số, kèm ghi chú *"cache là để tiết kiệm **bộ nhớ
   biên dịch**, ⛔ không phải để nhanh hơn"* — chỉ hợp lý nếu có số đo khác chứng minh.
3. Giữ cache **kèm** một đường khôi phục ⛔ không validate lại — ⛔ **không nên**, vì đó
   chính là lỗ RCE đã vá ngày 2026-08-16.

> ⚠️ Đây là điểm tôi **đề nghị Owner xác nhận trước khi sửa**: phương án 1 đổi hành vi
> production, cần người quyết.

---

### 🟡 #3 — Bẫy `loadTestsFromModule`: hàm `test_*` cấp module bị bỏ qua im lặng

`bench run-tests` gom test bằng `unittest.TestLoader().loadTestsFromModule()`
(`frappe/test_runner.py:269`), và bộ gom này **chỉ nhặt lớp `TestCase`**. Hàm `test_*`
khai ở cấp module bị bỏ qua — **⛔ không cảnh báo, ⛔ không lỗi**, bộ test chỉ đơn giản là
thiếu.

✅ Trong chính job này: `formula_builder/tests/test_row_output_dependency.py` ban đầu là
**8 hàm trần** → bộ gom nhặt **0** test. Sau khi bọc vào lớp → nhặt **8**. Đây là **8 ca
regression của bản vá** — tức bằng chứng bảo vệ bản vá từng **vô hình** với CI.

Đã xử lý trong commit `7c689f0`. Ghi lại đây vì:
- Bài học này áp cho **mọi** repo khác trong fleet, ⛔ không riêng app này.
- `formula_builder/` hiện **⛔ không còn** tệp test nào ở trạng thái hàm trần (đã quét).

> 💡 **Phép thử cho người viết test:** chạy
> `python -c "import unittest,<module> as m; print(unittest.TestLoader().loadTestsFromModule(m).countTestCases())"`
> — ra `0` nghĩa là test của bạn ⛔ không bao giờ chạy.

---

### 🟡 #4 — Khai Python 3.14, chạy Python 3.10

| Nơi | Giá trị | Nguồn |
|---|---|---|
| `pyproject.toml:7` | `requires-python = ">=3.14"` | đọc tệp |
| `pyproject.toml:25` | `target-version = "py314"` | đọc tệp |
| `.github/workflows/ci.yml:20,47` | `python-version: '3.14'` | đọc tệp |
| Bench cục bộ | **Python 3.10.12** | ✅ `env/bin/python -V` |

**Hệ quả 1 — "xanh trên máy" ⛔ không suy ra "xanh trên CI".** Mã dùng cú pháp 3.11+ (ví
dụ `except*`, `Self`, `StrEnum`) sẽ chạy ở CI nhưng vỡ ở máy, hoặc ngược lại. ⚠️ Trớ trêu:
`requires-python = ">=3.14"` lẽ ra phải **chặn** cài trên 3.10 — nhưng app được cài bằng
đường `.pth` của bench nên ràng buộc đó ⛔ không có hiệu lực (✅ `pip list` vẫn thấy
`formula_builder 0.0.1`).

**Hệ quả 2 — lint chưa từng chạy ở máy.** `ruff` ⛔ **không có** trong môi trường bench.
CI có bước lint (`ci.yml:21-23`), nên toàn bộ chuẩn `line-length = 110` chưa được kiểm ở
máy dev lần nào. Hiện tôi ⛔ không xác minh được tệp nào vi phạm.

**Cách sửa:** hoặc hạ khai báo xuống phiên bản bench thật đang chạy, hoặc ghi rõ trong
README rằng "CI dùng 3.14, máy dev dùng 3.10 — khác biệt có ý thức". Cài `ruff` vào bench
(`env/bin/pip install ruff`) để lint chạy được trước khi push.

---

### 🟡 #5 — Hai đường đăng ký source type, đường sau đè im lặng

Chính mã nguồn đã ghi rất rõ nguy cơ này — `api/source_type_registry.py:520-534`:

> *"⚠️ If the SAME handler function is registered twice (e.g. once by this decorator and once
> by `_register_all_to_central_registry()`), then `SourceTypeRegistry.register()` writes
> `handler.fingerprint_fn` and `handler.batchable` back onto the function object — and the
> **LATER registration wins, silently**. Both registries share that one function object, so a
> fingerprint fixed in only one place is **silently reverted at runtime**."*

Và `:519-521` cảnh báo thêm: `api/data_source_registry.py` **gán lại tên**
`register_source` giữa tệp, nên handler khai **phía trên** điểm đó **âm thầm** nhận
decorator cũ.

Đây ⛔ không phải suy đoán — **đã xảy ra thật** với `linked_doctype_field` (ghi trong bộ
nhớ đội): sửa `fingerprint_fn` ở decorator mà quên đường đăng ký thứ hai ⇒ bản vá N+1
**mất tác dụng im lặng**.

Đánh 🟡 ⛔ không phải 🔴 vì: cảnh báo đã có trong mã, và `_register_all_to_central_registry`
có chốt chống đăng ký trùng (`data_source_registry.py:1489-1491`).

**Rủi ro còn lại là cấu trúc:** 313 dòng đăng ký lặp lại ở `:1482` là **bản sao thứ hai**
của thông tin đã có ở decorator — hai nguồn sự thật cho cùng một việc.

**Cách sửa (đề xuất, ⛔ chưa làm):** để `_register_all_to_central_registry()` **đọc** từ
registry thay vì **chép lại** danh sách; hoặc sinh nó bằng script từ decorator. ⛔ Không sửa
nhanh trong job này vì chạm 313 dòng đăng ký của 19 loại nguồn.

---

### 🟡 #6 — Nuốt lỗi

| Mẫu | Số lần |
|---|---|
| `except Exception` | **160** |
| `except:` trần | **4** |
| `except … : pass` | **7** |

`except:` trần bắt cả `KeyboardInterrupt` và `SystemExit` — ⛔ không bao giờ nên có trong
thư viện. Vài chỗ `pass` có ghi lý do (ví dụ `normalize.py:115` ghi rõ *"cùng lắm giữ
nguyên — thà ⛔ không gỡ còn hơn vỡ"*), nhưng phần lớn thì không.

**Cách sửa:** thu hẹp về loại lỗi cụ thể; chỗ nào cố ý bỏ qua thì ghi lý do như
`normalize.py:115` đang làm.

---

### 🟢 #7 — `print()` trong thư viện

`formula_utils/allocation.py:339,341,342,346,361,362,365` — 7 lệnh `print()` nằm trong
module **thư viện** (⛔ không phải `example/`). Trên production, mỗi lần gọi sẽ đẩy rác ra
stdout của tiến trình web.

**Cách sửa:** đổi sang `frappe.logger()`, hoặc chuyển thành hàm `debug_dump()` mà nơi gọi
tự nguyện gọi.

---

### 🟢 #8 — Tài liệu cũ còn ghi v30

| Tệp | Ghi |
|---|---|
| `docs/FINAL_AUDIT_v30.md:1` | *"Formula Builder v30.0.0 — Final Audit Report"* |
| `docs/AUDIT_REPORT.md` | còn nhắc v30/v29 |
| `docs/Snapshot_Lifecycle_Full_Example.md` | còn nhắc bản cũ |
| **Lõi thật** | `ENGINE_VERSION = "31.0.0"` (`engine_core.py:195`) |

Người đọc mới ⛔ không biết tệp nào còn đúng. **Cách sửa:** thêm 1 dòng ở đầu mỗi tài liệu
cũ: *"⚠️ Tài liệu này viết cho v30 — xem `flexible_formula_engine.md` cho v31."*

---

### 🟢 #9 — Module 3 233 dòng, một hàm 313 dòng

`data_source_registry.py` (3 233 dòng) chứa 19 loại nguồn; `_register_all_to_central_registry`
chiếm **313 dòng liền** ở `:1482`. Hàm dài nhất lõi khác là `FormulaEngineCore.__init__`
**201 dòng** (`engine_core.py:197`).

⛔ Không phải lỗi, nhưng là lý do khó review và liên quan trực tiếp tới 🟡 #5.

---

## 4. Hiệu năng — số đo

✅ Tất cả số dưới đây đo trên bench cục bộ, Python 3.10.12.

**4.1 — Dựng engine chiếm gần như toàn bộ thời gian tính.**

| Việc | Tỉ lệ thời gian `calculate()` |
|---|---|
| Dựng engine | **98,3 – 98,8 %** |
| Tính toán thật | 1,2 – 1,7 % |

**4.2 — Giữ lại engine đã dựng: nhanh 64–88×.**

| Số công thức | Dựng lại | Dùng lại engine đã dựng |
|---|---|---|
| 14 | 0,206 ms | 0,0032 ms |
| 30 | 0,424 ms | 0,0055 ms |
| 60 | 0,825 ms | 0,0095 ms |
| 200 | 2,660 ms | 0,0304 ms |

**4.3 — Giữ `FlexibleFormulaEngine` chỉ lợi 1,4 %.** Vì nó dựng lại engine con **bên
trong** mỗi lần `calculate()`. Muốn hưởng lợi 4.2 thì phải giữ **`FormulaEngine` đã dựng**,
⛔ không phải lớp bọc.

**4.4 — Khi nào dựng lại là **bắt buộc**?** Chỉ khi công thức phụ thuộc dữ liệu đầu vào —
cụ thể là khi cấu hình có `child_tables`, vì `_build_all_formulas()` đọc `row_id` và
`row[formula_field]` từ `context` (`flexible_formula_engine.py:601,617`). ✅ Đã kiểm: với
cùng một bộ công thức, ⛔ không có `child_tables`, `hash_formulas` **giống hệt nhau** giữa
các `context` khác nhau — nghĩa là **dựng lại là thừa** trong trường hợp đó.

**4.5 — Bản vá ⛔ không làm chậm đường cũ.** Số lượt tính theo cấu hình: ⛔ không bảng → 1;
có bảng nhưng header không đọc `output_field` → 1; header đọc → 2. Tức chi phí tăng chỉ ở
đúng cấu hình trước đây **cho ra số sai**.

**4.6 — `from_cache_bytes` chậm hơn dựng mới 5×** — xem 🟡 #2.

---

## 5. Bảo mật

**5.1 — Cổng validate tại lúc khôi phục cache (điểm mạnh, mục 2.3).** Nguyên tắc:
bytecode **⛔ không bao giờ** được tin từ nguồn tuần tự hoá; luôn biên dịch lại từ mã nguồn
đã qua `SecurityValidator`. Cách này đúng và nên giữ, kể cả khi nó là nguyên nhân của 🟡 #2.

**5.2 — `pyproject.toml` khai `requires-python = ">=3.14"` nhưng ⛔ không có hiệu lực**
(mục 3.4). Nếu mã có phụ thuộc vào hành vi đã thay đổi giữa 3.10 và 3.14 mà ⛔ không có
test phủ, thì lỗi sẽ chỉ lộ trên production.

**5.3 — Bề mặt API.** ✅ Đã đếm (trước đó tôi ghi "chưa xác minh" — nay đã kiểm):

| Chỉ số | Giá trị |
|---|---|
| `@frappe.whitelist()` toàn app | **30** |
| `allow_guest=True` | **✅ 0** — mọi endpoint đều đòi phiên đăng nhập |

**Kiểm quyền theo tài liệu — làm đúng.** App bọc `frappe.has_permission` trong một hàm
dùng chung `assert_read_perm(doctype, docname)` (`api/_helpers.py:84`) và gọi ở **5 chỗ**
(`api/formula_builder.py:62, 96, 186, 284, 533`) — tức **mọi** endpoint nhận
`doctype`/`docname` từ client đều chặn trước khi đọc. Ví dụ `get_child_rows(doctype,
docname, child_field)` gọi chốt này ngay dòng đầu (`:62`).

> ⚠️ **Đính chính một nghi ngờ của chính tôi.** Lần đếm đầu tôi grep `has_permission` và
> chỉ thấy **1** kết quả, suýt kết luận "30 endpoint ⛔ không kiểm quyền". **Sai** — vì
> app gọi qua lớp bọc `assert_read_perm`. Grep theo **tên hàm gốc** ⛔ không thấy được lớp
> bọc. Ghi lại đây vì đây là kiểu sai dễ lặp lại khi rà soát.

**Hai điểm nhỏ ghi nhận, ⛔ không phải lỗi:**

- `assert_read_perm` **thoát sớm** với docname bắt đầu bằng `new-` (`_helpers.py:87`) —
  hợp lý: bản nháp chưa lưu thì chưa có quyền để kiểm.
- `get_doctype_fields(doctype)` (`:74`) **⛔ không** kiểm quyền, trả về *metadata* trường
  (tên nhãn, kiểu) cho bất kỳ doctype nào với người đã đăng nhập. 🟢 nhẹ — chỉ là metadata,
  ⛔ không phải dữ liệu, và vốn dễ tra. Ghi để biết, ⛔ không đề nghị sửa.

**Có giới hạn tần suất cho endpoint AI.** `check_rate_limit` (`_helpers.py`, mặc định 10
lần/60 giây) dùng cho `ai_suggest` — ✅ đúng chỗ, vì đây là endpoint tốn tiền gọi mô hình.

**Ba chỗ `.eval()` đều là `SafeExpression`, ⛔ không phải `eval` Python:**
`data_source_registry.py:656` (`safe_filter.eval`), `:1162` (`cond_expr.eval`),
`batch_binding_resolver.py:224` (`expr.eval`) — cả ba đều là kết quả của
`safe_eval.compile_expression(...)` (`:640`, `:1141`, `:205`). ✅ Không có `eval`/`exec`
trần, ⛔ không có `os.system`, ⛔ không có `subprocess` trong `api/`.

---

## 6. Test & CI

**6.1 — Cơ chế.** CI (`ci.yml`) chạy `ruff` (Python 3.14) rồi `bench --site test_site
run-tests --app formula_builder`. Việc gom test đi qua `unittest.TestLoader`
(`frappe/test_runner.py:269`) — **chỉ nhặt lớp `TestCase`** (mục 3.3).

**6.2 — Khối lượng:** 520 hàm test / 17 tệp.

| Tệp | Số ca |
|---|---|
| `test_security.py` | 78 |
| `test_fb1_revised.py` | 62 |
| `test_phase1.py` | 48 |
| `test_table_formula_builder.py` | 42 |
| `test_platform_source_types.py` | 40 |
| `test_platform_phase1.py` | 32 |
| `test_html_entities.py` | 31 |
| `test_data_source.py` | 30 |
| `test_phase2_composite.py` | 30 |
| `test_engine_core.py` | 28 |
| `test_phase2.py` | 28 |
| `test_flexible_engine_fixes.py` | 25 |
| `test_batch_resolver.py` | 17 |
| `test_config_io.py` | 14 |
| `test_row_output_dependency.py` | 8 |
| `test_registry_consistency.py` | 7 |

**6.3 — ⛔ Không có `pytest` trong đường CI.** `pyproject.toml` ⛔ không khai cấu hình
`[tool.pytest]` nào. Docstring nào hướng dẫn chạy bằng `pytest` thì đó là đường **⛔ không
được CI thực thi**.

**6.4 — Bản vá này được kiểm chứng thế nào (ghi để truy vết):**
- ✅ Lỗi gốc tái hiện được và đã hết: `0 / 350 / 350` → **`350 / 350 / 1 150`**
- ✅ Hồi quy: **85 = 85** ca đỏ giữa cây trước và sau bản vá, **hiệu đối xứng rỗng** trên 15 module dùng chung
- ✅ Đột biến: **4/4** cây đột biến bị giết (M1→5, M2→4, M3→1, M4→1 ca đỏ; cây thật 0/8)
- ✅ `normalize.py`: đúng **4 ca khác hành vi** — và cả 4 đều là ca **có ném lỗi**; 10 ca còn lại giống hệt
- ✅ Đối chứng dương: 3/5 ca test mới **đỏ** trên mã chưa vá

---

## 7. Tài liệu

| Tệp | Trạng thái |
|---|---|
| `docs/flexible_formula_engine.md` | ✅ mới, 493 dòng, 14 bảng, khớp bản vá |
| `docs/fb_source_type_contract.md` | ✅ hợp lệ — hợp đồng cho 🟡 #5 |
| `docs/security_safe_eval.md` | cần đối chiếu với mục 5 |
| `docs/FINAL_AUDIT_v30.md` | 🟢 cũ — ghi v30 |
| `docs/AUDIT_REPORT.md` | 🟢 cũ |
| `docs/Snapshot_Lifecycle_Full_Example.md` | 🟢 còn nhắc bản cũ |
| `README.md` | ✅ có trỏ tới tài liệu mới (`:1511`) |

---

## 8. Đề xuất thứ tự xử lý

| Ưu tiên | Việc | Vì sao trước |
|---|---|---|
| 1 | 🟡 #2 — quyết định số phận `_engine_cache` | Đang chạy trên production, chi phí thuần. **Cần Owner quyết** vì đổi hành vi |
| 2 | 🟡 #1 — đưa tham số hành vi vào khoá cache | Sửa rẻ, chặn bẫy đã lên đạn |
| 3 | 🟡 #4 — cài `ruff` vào bench | Không có nó thì mọi lần push đều mù về lint |
| 4 | 🟡 #6 — thu hẹp `except:` trần (4 chỗ) + `except: pass` (7 chỗ) | Nhỏ, rõ, ít rủi ro |
| 5 | 🟢 #7 — 7 lệnh `print()` | Rẻ |
| 6 | 🟢 #8 — 1 dòng cảnh báo ở đầu mỗi tài liệu cũ | Rẻ, chặn hiểu nhầm |
| 7 | 🟡 #5 — hợp nhất 2 đường đăng ký | Việc lớn, cần job riêng |

---

## 9. Điều ⛔ chưa kiểm trong bản rà này

Ghi rõ để ⛔ không ai đọc thành "đã kiểm hết":

- **Lint `ruff`** chưa chạy được ở máy (mục 3.4) nên chuẩn 110 cột chưa xác minh.
- **Chạy trên Python 3.14** — máy chỉ có 3.10.12; mọi kết luận hiệu năng là số của 3.10.
- **19 loại nguồn dữ liệu**: mới rà cơ chế đăng ký, chưa rà từng handler.
- **`formula_utils/allocation.py`, `time_bucket.py`, `matrix`/`pipeline`**: chưa rà logic.
- **Đo hiệu năng theo lô lớn** (hàng nghìn công thức): chưa đo.
- **`api/_ai_core.py`** (gọi mô hình AI): chưa rà — ⛔ chưa kiểm prompt injection hay
  kiểm soát chi phí ngoài giới hạn tần suất ở mục 5.3.
- **13 module `formula_utils/funcs/`** (hàm dùng trong công thức): chưa rà từng hàm.

*(Mục "bề mặt `whitelist`/`allow_guest`" trước đây nằm trong danh sách này — **đã kiểm
xong**, xem mục 5.3.)*
