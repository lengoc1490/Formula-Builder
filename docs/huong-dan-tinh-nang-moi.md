# Hướng dẫn tính năng mới v28_14 — Formula Builder

> **Phạm vi tài liệu**
>
> | | |
> |---|---|
> | App | `formula_builder` — nhánh `develop`, HEAD `51cb497` (2026-11-12) |
> | Phạm vi | 6 thay đổi của bản vá v28_14: `$NAME`, lọc binding theo field, biến trả kèm phạm vi, gộp biến trùng tên, biến toàn cục đã tắt, widget gửi `fieldname` |
> | Đối tượng | DEV tích hợp FB vào app khác; admin cấu hình `Formula Variable Binding`; người viết công thức |
> | ⛔ Ngoài phạm vi | Kiến trúc engine ([flexible_formula_engine.md](flexible_formula_engine.md)) · hợp đồng source type ([fb_source_type_contract.md](fb_source_type_contract.md)) · hướng dẫn dùng phía AlumGlass ([link](../../alumglass/docs/variable-catalog/huong-dan-su-dung-tinh-nang.md)) |
> | Ngày soạn | 2026-11-13 |
>
> **Mức kiểm chứng:** ⛔ **chưa chạy trên site, chưa quan sát autocomplete trên trình duyệt.**
> Đã chạy test thuần (không cần Frappe/DB) tại HEAD `51cb497`:
> `tests/test_dollar_normalize.py` — **15 ca PASS**; `tests/test_live_context_dedupe.py` —
> **11 ca PASS**. Mọi mô tả UI/DB đọc từ mã.

> 🔴 **Hai câu phải nhớ:**
> 1. `$NAME` **nay chạy được** — nhưng `$snap.*` và chuỗi trong nháy ⛔ không bị đổi.
> 2. Lọc binding theo `applies_to_field` chỉ xảy ra khi scope có `fieldname`, và so khớp là
>    **đúng nguyên một fieldname** — ⛔ không phải danh sách ngăn `|`.

---

## 1. Tóm tắt 6 thay đổi

| # | Thay đổi | File | Ai chạm tới |
|---|---|---|---|
| 1 | `$NAME` được chấp nhận (`$NAME` → `NAME`) | `formula_utils/normalize.py` | Người viết công thức; app chèn biến dạng `$` |
| 2 | `get_live_context` lọc binding theo `applies_to_field` khi scope có `fieldname` | `api/formula_builder.py`, `api/binding_scope.py` | Người cấu hình binding |
| 3 | Mỗi biến trả kèm `applies_to_field` (chuỗi) và `only_fields` (list) | `api/formula_builder.py` | App ngoài (AlumGlass) lọc gợi ý tại client |
| 4 | Gộp biến trùng tên, hợp phạm vi field, ghi nguồn bị bỏ vào `duplicate_sources` | `api/formula_builder.py` | Người cấu hình binding; DEV đọc context |
| 5 | `Formula Global Variable` đã tắt (`is_active=0`) không còn được nạp | `api/global_variable_cache.py` | Admin; AlumGlass B1 |
| 6 | Widget gửi `fieldname` trong `_scope()` và `_buildCtx()` | `public/js/formula_builder.js` | Người dùng dialog công thức |

Tương thích ngược: ⛔ **không đổi schema DB** ⇒ **không cần migrate cho FB**. Công thức cũ dùng
tên trần vẫn chạy y như trước.

---

## 2. `$NAME` được chấp nhận

### 2.1 Vì sao có thay đổi này

Autocomplete của Formula Builder chèn biến toàn cục dưới dạng `$TEN` (xem
`public/js/formula_builder_field.js`, `insert: "$" + v.name`). Nhưng engine chỉ hiểu **tên trần**.
Trước bản vá, `$VAT_RATE` bị coi là lỗi cú pháp dù nghĩa y hệt `VAT_RATE`.

### 2.2 Luật chuyển đổi

| Chuỗi nhập | Kết quả | Vì sao |
|---|---|---|
| `$VAT_RATE * 2` | `VAT_RATE * 2` | Bỏ `$` của tên biến |
| `$A + $B_1` | `A + B_1` | Mọi tên khớp `[A-Za-z_]\w*` |
| `$snap.total + $RATE` | `$snap.total + RATE` | `$snap.*` là cú pháp snapshot — giữ nguyên |
| `$snapshot` | `snapshot` | Chỉ **đúng** `snap` được giữ; tên khác cùng tiền tố chữ vẫn bỏ `$` |
| `'$NAME' + "$OTHER" + $REAL` | `'$NAME' + "$OTHER" + REAL` | Chuỗi trong nháy là **dữ liệu**, ⛔ không phải biến (kể cả nháy escape `\'`) |
| `&dollar;RATE + 1` | `RATE + 1` | Gỡ HTML entity **trước** bước bỏ `$` |
| `$ 5`, `1$ + a` | giữ nguyên | `$` không đi kèm tên biến (tiền tệ, ký tự lạ) |
| `$$X` | `$X` | Chỉ bỏ `$` gắn với tên hợp lệ |

Áp dụng trong `normalize_formula()` — cùng pipeline mà validator và engine dùng trước khi parse,
nên **validate và tính toán nhìn thấy cùng một kết quả**. Hàm thuần tương ứng:
`formula_utils.normalize.strip_dollar_prefix(expr)`.

### 2.3 Cách kiểm tra

1. Mở dialog công thức, gõ một công thức có `$`:

   ```
   $VAT_RATE * 100
   ```

2. Bấm nút **▶** (tooltip “Chạy thử”, hoặc **Ctrl+Enter**). Kết quả mong đợi: tính ra số,
   ⛔ không còn báo lỗi cú pháp.
3. Gõ thử `IF($A = 1, '$B', $C)` — mong đợi: chỉ `$A`/`$C` thành biến, `'$B'` vẫn là chuỗi.
4. Gõ thử `$snap.total` — mong đợi: giữ nguyên, vẫn hiểu là snapshot.

Chạy test thuần (không cần site):

```bash
cd ~/myfrappe/apps/formula_builder
python3 -I -c "import sys, unittest; sys.path.insert(0, '.'); \
  unittest.main(module='formula_builder.tests.test_dollar_normalize', exit=False, verbosity=2)"
```

### 2.4 Giới hạn

- Chỉ bỏ `$` khi theo sau là tên hợp lệ `[A-Za-z_]\w*`. `$1`, `$ 5`, `$%` giữ nguyên.
- `snap` được giữ **theo đúng chữ thường**. `$SNAP.x` bị đổi thành `SNAP.x`.
- ⛔ Không thêm cú pháp `$` mới nào khác (không có `$[field]`, không có `$(...)`).

---

## 3. Lọc binding theo field đang sửa

### 3.1 Widget gửi gì

| Nơi gửi | Key trong scope JSON | Lấy từ |
|---|---|---|
| `AluglassFormulaEditor._scope()` | `fieldname` | `opts.current_field` |
| `AluglassFormulaEditor._buildCtx()` | `fieldname` (truyền cho `_ContextBuilder.build`) | `opts.current_field` |

`current_field` được `formula_builder_field.js` gán khi mở editor cho một field cụ thể. Nếu không
có field đang sửa, giá trị là `""` — khi đó ⛔ không lọc (xem 3.2).

> Lõi Formula Builder **không dùng** key `fieldname` trong `_buildCtx()` — nó chỉ chuyển tiếp để
> app ngoài (AlumGlass) đọc và lọc `only_fields` tại client. Key này có tác dụng **server-side**
> trong `_scope()` (các lượt gọi `get_live_context`, validate, evaluate, explain).

### 3.2 Server lọc thế nào

`get_live_context(scope_context_json)` đọc `fieldname` (chấp nhận cả key cũ `current_field`), rồi
gọi `get_scope_bindings(doctype, field=...)` — luật tập trung ở `api/binding_scope.py`:

| `applies_to_doctype` của binding | `applies_to_field` của binding | Scope **có** `fieldname = F` | Scope **không** có fieldname |
|---|---|---|---|
| rỗng | rỗng | Hiện (global) | Hiện |
| = doctype | rỗng | Hiện (mọi field của doctype) | Hiện |
| = doctype | = F | Hiện | Hiện |
| = doctype | ≠ F | **Không hiện** | Hiện |
| doctype khác | bất kỳ | Không hiện | Không hiện |
| rỗng | có giá trị | Không hiện (không thuộc doctype nào) | Không hiện |

> ⚠️ **So khớp là ĐÚNG NGUYÊN một chuỗi.** `applies_to_field = "width"` khớp `fieldname=width`;
> `applies_to_field = "width|height"` **không** khớp `fieldname=width` (và binding bị loại).
> Muốn một binding áp cho nhiều field: để `applies_to_field` **trống** (áp mọi field của doctype)
> rồi để client lọc bằng `only_fields`, hoặc tạo **mỗi field một binding**.

> ℹ️ **Vì sao vẫn "hiện" khi scope không có fieldname:** đây là chủ ý bảo toàn hành vi cũ — app
> nạp context **một lần** cho cả form (bulk) không được mất binding. Trường hợp này server vẫn trả
> `applies_to_field` / `only_fields` để client tự lọc (mục 3.3).

### 3.3 Biến trả kèm phạm vi field

Mỗi biến (entry có `name`) trong `variables` có thêm:

| Key | Kiểu | Ý nghĩa |
|---|---|---|
| `applies_to_field` | chuỗi | Phạm vi gốc của binding; sau bước gộp là các field ngăn `\|` |
| `only_fields` | list | Cùng thông tin dạng list — client lọc trực tiếp (`[]` = không giới hạn) |

Bước cuối của `get_live_context` chuẩn hoá **mọi** biến (kể cả biến không trùng tên, field của
chứng từ, biến toàn cục) về cùng dạng này.

### 3.4 Gộp biến trùng tên

Nhiều binding có thể cùng `variable_name` (khác scope, hoặc admin tạo trùng). Trước bản vá, entry
**đầu tiên** thắng tuyệt đối — kể cả khi nó resolve ra `None`, nó vẫn che entry phía sau có giá trị
thật.

| Luật | Hành vi |
|---|---|
| Ưu tiên giá trị | Entry có `value is not None` được giữ; nếu entry sau có giá trị còn entry đầu rỗng ⇒ **thay tại chỗ** (giữ nguyên vị trí trong danh sách) |
| Hoà | Giữ entry **đầu tiên** (thứ tự gợi ý không đổi) |
| Phạm vi field | **Hợp** phạm vi của mọi entry cùng tên; nếu **một** entry không giới hạn ⇒ không giới hạn |
| Nguồn bị bỏ | Ghi vào `duplicate_sources` của entry được giữ (`source`, `source_type`, `value`) — ⛔ không bỏ im lặng |
| Binding bị bỏ | **Vẫn resolve đầy đủ** ở bước 3; chỉ không lặp lại trong danh sách gợi ý |

### 3.5 Cách dùng: cấu hình binding theo field

1. Desk → `Formula Variable Binding` → **New** (hoặc mở record có sẵn).
2. Điền:
   - `variable_name` (bắt buộc), `variable_label`.
   - `source_type` + `source_config`.
   - `applies_to_doctype`: doctype sở hữu field.
   - `applies_to_field`: **một** fieldname, ví dụ `calc_formula`. Để trống = áp mọi field của
     doctype.
   - `is_active = 1`.
3. Lưu.
4. Kiểm autocomplete: mở field đúng tên trong `applies_to_field` → biến phải có; mở field khác
   (cùng doctype) → biến phải **không** có (khi scope có `fieldname`).
5. Kiểm `$`: gõ `$<tên biến>` → phải tính được (mục 2).
6. Kiểm biến tắt: xem mục 4.

**Dấu hiệu sai thường gặp:**

| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| Biến hiện ở **mọi** field dù đã khai `applies_to_field` | Scope gọi `get_live_context` không có `fieldname` (đường bulk) — đúng theo thiết kế; client phải lọc bằng `only_fields` |
| Biến **không** hiện ở field đúng | `applies_to_field` là danh sách ngăn `\|`, hoặc sai doctype, hoặc binding `is_active=0` |
| Biến hiện nhưng giá trị `None` | Binding resolve lỗi/không có dữ liệu — kiểm `source_config`, không phải lỗi lọc scope |
| Sửa binding mà kết quả không đổi | Context cache ở client (dialog 30 giây; AlumGlass 5 phút) — đóng/mở lại form hoặc chờ TTL |

---

## 4. `Formula Global Variable` đã tắt không còn được nạp

`api/global_variable_cache.py::get_all_global_variables()` nay lọc `is_active = 1` trước khi trả.

- **Trước:** record đã tắt vẫn được trả về. Với AlumGlass B1, **mọi record trả về đều được ghi
  vào `inputs`** ⇒ record tắt có thể **che** giá trị của system variable cùng tên bằng chuỗi rỗng.
- **Sau:** biến đã tắt không vào autocomplete/context và không vào `inputs`.
- Record `value_source` là `FORMULA` / `DB_QUERY` (không có `constant_value`) **vẫn được trả về**
  khi đang bật — hành vi cũ giữ nguyên.
- Cache Redis TTL **60 giây**. `on_update` / `on_trash` của DocType xoá cache ngay; nhưng
  `frappe.db.set_value()` **không chạy document event** ⇒ đường ghi đó phải chờ tối đa 60 giây.

**Cách kiểm tra:**

1. Mở `Formula Global Variable`, tắt `is_active` của một biến đang dùng.
2. Chờ ≤ 60 giây (hoặc xoá cache), mở lại form → biến phải biến mất khỏi gợi ý.
3. ⚠️ Công thức đang dùng biến đó sẽ **không còn nguồn giá trị** từ nguồn này (trừ khi có nguồn
   khác cung cấp cùng tên) — kiểm tra trước khi tắt trên production.

---

## 5. Tương thích ngược và triển khai

| Tình huống | Hành vi |
|---|---|
| Công thức cũ dùng tên trần `VAT_RATE` | Chạy y như trước |
| Công thức cũ dùng `$VAT_RATE` | **Nay chạy được** (trước là lỗi cú pháp) |
| Công thức có `'$NAME'` trong nháy | Giữ nguyên chuỗi — ⛔ **không** đổi hành vi |
| Công thức có `$snap.*` | Giữ nguyên cú pháp snapshot |
| Binding cũ **không** khai `applies_to_field` | Áp mọi field như trước |
| Binding cũ khai `applies_to_field`, scope **không** gửi fieldname | Vẫn hiện như trước (kèm `only_fields`) |
| Schema DB | ⛔ **Không đổi** — không cần migrate cho FB |

**Cần làm khi triển khai:**

```bash
bench build --app formula_builder
bench restart                     # nạp lại mã Python
bench --site <site> clear-cache   # xoá cache context/settings
```

> ⚠️ **Asset version chưa bump:** `hooks.py` vẫn khai `formula_builder.js?v=30.0.1` (HEAD
> `51cb497`). Sau `bench build`, trình duyệt có thể vẫn dùng JS cũ trong cache — phải cứng-refresh
> (Ctrl+Shift+R) hoặc bump version trong `hooks.py`. Đây là việc của DEV, tài liệu chỉ ghi nhận.

---

## 6. AlumGlass dùng Formula Builder thế nào (ngắn)

Đây là phần **bắt buộc biết** nếu bạn sửa FB mà app AlumGlass đang chạy:

| Đường | FB cung cấp | AlumGlass dùng cho |
|---|---|---|
| `get_live_context` | Resolve `Formula Variable Binding` + phạm vi field | Nguồn biến chính của autocomplete (`_get_live_context_vars`) |
| `FormulaEngine` | DAG, parse, tính toán | B4 (tính dòng BOM) và B6 (bảng giá thành) |
| `get_all_global_variables` | Hằng số toàn cục đã lọc `is_active` | B1 — ghi vào `inputs` |

- AlumGlass gọi `get_formula_context` với `include_all_sources=True` khi **validate** ⇒ universe
  đi đường legacy đầy đủ, ⛔ không bị profile lọc. Lưu ý: nếu nơi gọi **có** truyền `fieldname`
  (controller `AL Cost Template` truyền `calc_formula`), binding khai `applies_to_field` khác field
  đó **vẫn** bị loại khỏi universe validate; `AL Bom Set` không truyền nên thấy mọi binding.
- AlumGlass **bulk prefetch** không gửi `fieldname` ⇒ binding có `applies_to_field` vẫn được trả
  về; việc lọc theo field do client AlumGlass làm bằng `only_fields` / `hide_all`.
- Đường đi đầy đủ của một biến (gợi ý → runtime):
  [tu-goi-y-den-runtime.md](../../alumglass/docs/variable-catalog/tu-goi-y-den-runtime.md).

---

## 7. Kiểm chứng đã làm

| Hạng mục | Trạng thái |
|---|---|
| `tests/test_dollar_normalize.py` (thuần, không cần Frappe) | ✅ **15 ca PASS** |
| `tests/test_live_context_dedupe.py` (thuần, đọc chính file nguồn bằng AST) | ✅ **11 ca PASS** |
| `bench migrate` / chạy trên site | ⛔ **chưa chạy** — FB không đổi schema nên không bắt buộc |
| Quan sát autocomplete trên trình duyệt | ⛔ **chưa làm** |
| Đo trên dữ liệu thật | ⛔ **chưa làm** |

Chạy lại cả hai bộ test:

```bash
cd ~/myfrappe/apps/formula_builder
python3 -I -c "import sys, unittest; sys.path.insert(0, '.'); \
  unittest.main(module='formula_builder.tests.test_live_context_dedupe', exit=False, verbosity=2)"
```

---

## 8. Giới hạn và đọc tiếp

| ⛔ Không có | Thực tế |
|---|---|
| `applies_to_field` là danh sách nhiều field **cho việc lọc server** | So khớp đúng nguyên chuỗi; muốn nhiều field ⇒ nhiều binding, hoặc để trống + client lọc |
| Tự lọc theo field khi scope không gửi `fieldname` | Không lọc — đúng chủ ý bảo toàn hành vi bulk |
| Đổi `$` bên trong chuỗi/literal | Không đổi (dữ liệu) |
| `$SNAP.*` / biến thể hoa-thường của `snap` | Chỉ đúng chữ `snap` được giữ |
| Migrate cho FB | Không cần — không đổi schema |

| Tài liệu | Dành cho |
|---|---|
| [README.md](../README.md) | Toàn bộ tính năng, data model, API |
| [flexible_formula_engine.md](flexible_formula_engine.md) | Engine đa bảng, số lượt tính |
| [fb_source_type_contract.md](fb_source_type_contract.md) | Hợp đồng source type (gồm scope `applies_to_field`, §9) |
| [design/fvb-single-resolution-layer.md](design/fvb-single-resolution-layer.md) | Thiết kế một lớp resolve duy nhất cho FVB |
| [AlumGlass — hướng dẫn dùng tính năng](../../alumglass/docs/variable-catalog/huong-dan-su-dung-tinh-nang.md) | Phía app: profile, Settings, Formula Field |
| [AlumGlass — từ gợi ý đến runtime](../../alumglass/docs/variable-catalog/tu-goi-y-den-runtime.md) | Đường đi của biến trong luồng tính giá |
| [AlumGlass — nguồn biến theo DocType](../../alumglass/docs/variable-catalog/nguon-bien-theo-doctype.md) | Từng DocType: biến setting ở đâu, lấy từ đâu, điều kiện gì, runtime dùng thế nào |
