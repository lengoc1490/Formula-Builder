Cơ chế tính giá Quotation trong AlumGlass — Tài liệu kỹ thuật đầy đủ
> Viết từ việc đọc trực tiếp code thật: `engine/bom_orchestrator.py`, `api/__init__.py`,
> `alumglass/doctype/overrides/quotation.js`, `al_bom_version.py`, `fb_handlers.py`,
> `api/quotation_events.py` — không suy đoán. Mọi số dòng/tên hàm trong tài liệu này
> khớp với code tại thời điểm viết.
---
Mục lục
## Bức tranh tổng quan — 3 tầng kiến trúc
## Sơ đồ luồng tổng thể
## Giai đoạn Setup — Master Data (config trước khi tính được giá)
## Dialog Quotation — luồng nhập liệu người dùng
## API entry point — `calculate_bom` (sync/async)
## BomOrchestrator — 8 phase B0→B7 (trái tim của engine)
## Cơ chế biến — toàn bộ nguồn resolve giá trị
## Tra giá composite key — mã đại diện + Pricing Dimension
## Formula Builder tính toán thế nào — liên hệ chi tiết
## Validate công thức — 2 lớp
## Snapshot — 2 cơ chế khác nhau, đừng nhầm lẫn
## Kết quả trả về & nơi lưu trữ
## Sơ đồ tổng kết toàn bộ luồng
## Phụ lục — bảng tra nhanh file/hàm theo chủ đề
---
1. Bức tranh tổng quan — 3 tầng kiến trúc
```
┌───────────────────────────────────────────────────────────────────┐
│ TẦNG 1 — DỮ LIỆU (Frappe DocTypes, 100% data-driven)              │
│   AL Bom Set, AL Bom Item, AL Cost Template, AL Cost Bucket,      │
│   AL Variable Set/Library, AL Pricing Dimension, AL Variable      │
│   Dimension Mapping, AL Glass Master, AL Material Category,       │
│   AL Profile System, AL Product Type, AL Accessory Set...         │
└──────────────────────────┬────────────────────────────────────────┘
                           │ đọc config (không hardcode nghiệp vụ)
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│ TẦNG 2 — ORCHESTRATION (alumglass, module `engine`)                 │
│   BomOrchestrator — 8 phase B0→B7: gom input, tra cứu master data,  │
│   build công thức, GỌI formula_builder để tính, gom bucket, lưu.    │
│   KHÔNG tự eval công thức — luôn ủy quyền cho tầng 3.               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ formulas + context → gọi
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ TẦNG 3 — ENGINE TÍNH TOÁN (app `formula_builder`, độc lập nghiệp vụ) │
│   FormulaEngine (DAG + sandbox AST) — tính Bom Items (B4)            │
│   FlexibleFormulaEngine (multi-table) — tính Cost Template (B6)      │
│   BatchBindingResolver — batch-resolve Formula Variable Binding      │
│   SourceTypeRegistry — điểm mở rộng cho custom source (fb_handlers)  │
└──────────────────────────────────────────────────────────────────────┘
```
Nguyên tắc cốt lõi (ghi ngay đầu `bom_orchestrator.py`):
> \*"AlumGlass chỉ config, không hardcode nghiệp vụ. Mọi logic đến từ DB... Tính toán ủy thác cho Formula Builder... Engine này chỉ làm: đọc config → resolve biến → build formulas → gọi FB → lưu kết quả."\*
AlumGlass không tự viết 1 dòng `eval()` nào cho công thức người dùng nhập — mọi phép tính thật sự chạy trong sandbox AST của `formula_builder`.
---
2. Sơ đồ luồng tổng thể
```
[User mở Quotation, thêm dòng sản phẩm]
        │
        ▼
[Dialog "Nhập thông số"] ── quotation.js
   • Chọn AL BOM (sản phẩm)
   • Nhập biến (W_mm, H_mm, màu nhôm, xuất xứ, độ dày, bề mặt...)
   • Chọn kính theo từng vị trí (nếu multi-glass)
        │  Lưu vào Quotation Item.al_bom_vars (JSON)
        ▼
[Bấm "Tính giá"] ── gọi API alumglass.api.calculate_bom
        │
        ├─ BOM nhỏ/vừa (≤ ASYNC_BOM_THRESHOLD dòng) → chạy ĐỒNG BỘ
        └─ BOM lớn → enqueue background job (queue "long") → trả kết quả
                      qua realtime event khi xong
        │
        ▼
[BomOrchestrator(quotation_item_name).run()] ── engine/bom_orchestrator.py
   B0 Version Pinning     — chốt đúng 1 AL BOM Version (snapshot bất biến)
   B1 Gather Inputs       — gom biến từ nhiều nguồn (xem mục 7)
   B2 Prefetch Master Data— batch query (Item, Item Price, Glass Master...)
   B3 Build Formulas      — build list {name, formula} cho từng Bom Item
   B4 Calculate Bom Items — GỌI formula_builder.FormulaEngine (DAG + sandbox)
   B5 Aggregate Buckets   — gom line_total theo Cost Bucket
   B6 Calculate Cost Tpl  — GỌI formula_builder.FlexibleFormulaEngine
   B7 Save Results        — ghi vào Quotation Item (1 commit)
        │
        ▼
[Trả kết quả về dialog] {buckets, cost_template, lines}
        │
        ▼
[User Submit Quotation] ── doc_events on_submit
        │
        ▼
[Tạo ConfigSnapshot cho mỗi Quotation Item đã tính] — audit trail bất biến
```
---
3. Giai đoạn Setup — Master Data
Đây là bước con người cấu hình trước, không phải code chạy — nhưng bắt buộc phải hiểu đúng thứ tự phụ thuộc thì mới hiểu được engine đọc gì ở đâu.
3.1 Cấu trúc sản phẩm (AL Bom Set → AL Bom Item)
`AL Bom Set`: 1 "khuôn" sản phẩm (vd "Cửa đi 2 cánh"). Có `product_type`, `profile_system`, `variable_set`, `default_accessory_set`, và field cấu hình `formula_fieldnames` (danh sách field nào trên `AL Bom Item` chứa công thức — data-driven, không hardcode).
`AL Bom Item` (child table của Bom Set): mỗi dòng = 1 loại vật tư (thanh nhôm, tấm kính, phụ kiện, nẹp...). Field quan trọng:
`slug` — định danh dòng, dùng cho cross-reference (`items.slug.field`).
`width`/`height`/`qty`/`show_condition`/`item_condition_formula`/`rule_input_expr` — công thức, viết bằng cú pháp formula_builder.
`item_selection_mode` (`Fixed`/`Formula`/`Rule`) — chọn `item_code` tĩnh, theo điều kiện, hay tra `AL Dynamic Item Rule`.
`price_type` (`Item Price`/khác), `price_base_item` — mã đại diện để tra giá (xem mục 8).
`default_glass_master` — với dòng kính, mã kính mặc định (có thể bị dialog override theo từng vị trí).
`cost_bucket` — dòng này được gom vào bucket giá nào (VL_NHOM, VL_KINH...).
`calc_pattern` (Link → `AL Quantity Calc Method`) — công thức tính số lượng phức tạp (m², cái, bộ...) được đóng gói sẵn.
3.2 Cấu trúc chi phí (AL Cost Bucket → AL Cost Template)
`AL Cost Bucket`: 1 "ngăn" chi phí (VL_NHOM, VL_KINH, NC_SX, OH_VC...). Có `source_type`/`source_config` — data-driven, cho phép cấu hình cách gom (`aggregate_from_items`) thay vì hardcode.
`AL Cost Template` (+ `AL Cost Template Item`): công thức tính giá cuối (GIA_THANH, GIA_BAN, VAT, GIA_VAT...) — mỗi dòng có `line_code` + `calc_formula`, tham chiếu tới Cost Bucket hoặc dòng khác.
3.3 Biến (Variable) — 2 loại
`AL Variable Library` (`is_system=1`): biến engine tự resolve từ 1 doctype khác (vd `OFFSET_DO_NGANG` từ `AL Profile System.offset_crossbar`) — có `source_doctype`/`source_field`.
`AL Variable Library` (`is_system=0`) + `AL Variable Set`: biến người dùng nhập tay (W_mm, H_mm, màu nhôm...) — mô tả kiểu UI control (`var_type`, `link_doctype`, `select_options`) để dialog Quotation dựng form nhập liệu.
3.4 Pricing Dimension — cấu hình composite key
`AL Pricing Dimension`: định nghĩa 1 "chiều" giá (Màu sắc, Xuất xứ, Độ dày, Bề mặt...) — tự sinh `Custom Field` (`custom_pd_\*`) trên Item Price (ERPNext gốc).
`AL Variable Dimension Mapping`: nối 1 biến (`variable_name`) với 1 Pricing Dimension + lọc theo `material_category` (NHOM/KINH/...).
3.5 Vật tư & kính
`AL Glass Master`: catalog mã kính, có `total_thick_mm`/`glass_type`/`item_code`.
`AL Accessory Set` (+ `AL Accessory Item`): tập hợp phụ kiện, mỗi dòng có `qty_formula`.
`AL Material Category`: NHOM/KINH/PHU_KIEN..., có `requires_price_base_item`, `default_scrap_pct`, `has_weight`.
3.6 Bất biến hóa (Immutable) — AL BOM
`AL BOM`: liên kết `bom_set` + `default_cost_template`, có `current_version` trỏ tới `AL BOM Version` đang Published.
`AL BOM Version`: snapshot bất biến toàn bộ cấu hình ở thời điểm publish (xem mục 11) — đây là thứ engine THẬT SỰ đọc khi tính giá, không đọc trực tiếp `AL Bom Set`/`AL Cost Template` live.
---
4. Dialog Quotation — luồng nhập liệu người dùng
File: `alumglass/alumglass/doctype/overrides/quotation.js` (1634 dòng).
User chọn `AL BOM` cho 1 dòng Quotation Item → dialog gọi `alumglass.api.get_variable_set_for_bom(bom_code)` để lấy:
Danh sách biến cần nhập (từ `AL Variable Set` gắn với Bom Set), kèm `var_type`/`link_doctype`/`select_options` để dựng đúng loại control (Select/Link/Data/Float).
`glass_groups` — danh sách vị trí kính (nếu sản phẩm có ≥1 dòng kính), mỗi group có mã kính đại diện (`rep`) + mặc định (`default`).
Dialog render form (`_render_vars_container`/`_make_var_control`) — biến pricing dimension (màu/xuất xứ/độ dày/bề mặt nhôm) đánh dấu không bắt buộc (`OPTIONAL_DIMENSIONS`) — để trống thì engine bỏ qua dimension đó khi tra giá (matching kiểu best-partial-match, xem mục 8).
Nếu có `glass_groups` → dialog render thêm N selector Link → `AL Glass Master`, cho phép đổi mã kính riêng theo từng vị trí.
User bấm Lưu → `_save()` gom toàn bộ giá trị thành object, JSON hoá, ghi vào `Quotation Item.al_bom_vars`:
```json
   {
     "aluminum_color": "DARK", "aluminum_origin": "IMPORT",
     "W_mm": 2400, "H_mm": 2600, "n_panel": 2,
     "glass_master_map": {"KINH-LOWE-24": "KINH-DON-8"},
     "_profile_system": "PS-XINGFA-55", "_cost_template": null,
     "_accessory_set": "ACC-SET-01",
     "extra_vars": {}
   }
   ```
User bấm "Tính giá" → gọi `alumglass.api.calculate\_bom` (mục 5).
---
5. API entry point — `calculate\_bom`
File: `alumglass/api/__init__.py`, hàm `calculate_bom(quotation_item_name)`.
```python
@frappe.whitelist()
def calculate\_bom(quotation_item_name):
    qi = frappe.get\_doc("Quotation Item", quotation_item_name)
    line\_count = _estimate_bom_line_count(qi)          # đếm nhanh từ snapshot, không load engine
    threshold = \_get_async_threshold()                  # Formula Global Variable ASYNC\_BOM\_THRESHOLD, default 150

    if line\_count <= threshold:
        result = BomOrchestrator(quotation\_item_name).run()   # ĐỒNG BỘ
        return \_normalize\_bom_response(result)

    return \_enqueue\_bom_calculation(qi)                 # BẤT ĐỒNG BỘ (frappe.enqueue, queue="long")
```
Đồng bộ (đa số trường hợp): chạy ngay trong request, trả kết quả trực tiếp cho dialog.
Bất đồng bộ (BOM rất lớn, > ngưỡng): `frappe.enqueue` chạy `_run_bom_calculation_job` trong RQ worker riêng — set `al_calc_status = Queued → Running → Success/Failed`, publish kết quả qua `frappe.publish_realtime("alumglass_bom_calc_done", ...)`, dialog lắng nghe event này để tự cập nhật UI.
Cả 2 nhánh đều gọi cùng 1 `BomOrchestrator(...).run()` — chỉ khác đồng bộ hay không.
---
6. BomOrchestrator — 8 phase B0→B7
File: `alumglass/engine/bom\_orchestrator.py` (~1470 dòng). Đây là class trung tâm, method `run()`:
```python
def run(self):
    self.b0\_version_pinning()
    self.b1\_gather_inputs()
    self.b2\_prefetch_master_data()
    self.b3\_build_formulas()
    self.b4\_calculate_bom_items()
    self.b5\_aggregate_cost_buckets()
    self.b6\_calculate_cost_template()
    self.b7\_save_results()
    return self.\_build_response()
```
B0 — Version Pinning
Chốt đúng 1 `AL BOM Version` (bất biến) để tính:
Nếu `Quotation Item.al_bom_version` đã có → dùng đúng version đó (đã pin từ lần tính trước, đảm bảo tái lập được).
Nếu chưa có nhưng `AL BOM.current_version` đã tồn tại → dùng version đó, ghi vào `al_bom_version`.
Nếu `AL BOM` chưa từng có version nào → tự động tạo 1 `AL BOM Version` mới, `workflow_state="Published"` ngay lập tức (`_auto_create_bom_version`), snapshot toàn bộ cấu hình hiện tại, set làm `current_version`.
→ Hệ quả quan trọng: sau B0, toàn bộ các bước sau KHÔNG đọc `AL Bom Set`/`AL Cost Template` sống nữa — chỉ đọc từ snapshot JSON đã đóng băng trong `self.bom_version`.
B1 — Gather Inputs
Gom biến từ nhiều nguồn theo thứ tự ưu tiên (nguồn sau đè nguồn trước) — xem chi tiết đầy đủ ở mục 7.
B2 — Prefetch Master Data
Batch-query TOÀN BỘ dữ liệu cần cho B3/B4 trong ít lượt truy vấn nhất (chống N+1):
Trọng lượng (`Item.weight_per_unit`) cho mọi `item_code` xuất hiện trong BOM.
Giá (`Item Price`) — qua composite pricing (mục 8).
`AL Glass Master` cho mọi mã kính (mặc định + override theo từng vị trí).
`AL Material Category` (scrap_pct, has_weight).
Resolve Dynamic Item Rule (nẹp kính, keo... chọn theo độ dày kính) — theo từng dòng (mỗi vị trí kính có thể ra kết quả khác nhau).
Build `row_literals[slug]` — dict literal cho từng dòng BOM (weight_per_unit, unit_price, glass_thick, glass_type, item_code, scrap_pct, has_weight...).
B3 — Build Formulas
Chuyển từng `AL Bom Item` thành list `{name, formula}` cho `FormulaEngine`:
Field công thức (`width`, `height`, `qty`...) → đổi tên thành `{slug}__{field}` (namespace phẳng).
Cross-reference `items.slug.field` → chuẩn hóa thành `slug__field` (dùng `formula_builder.table_formula_builder.normalize_global` — hàm chuẩn của chính formula_builder, không tự viết regex).
Sinh thêm 3 công thức "synthetic" cho mỗi dòng: `{slug}__unit_qty` (gọi `lookup_calc_pattern`), `{slug}__total_qty` (= unit_qty × qty), `{slug}__line_total` (= total_qty × unit_price).
Inject `self.inputs["items"]` — dict lồng nhau `{slug: {field: value}}` để hỗ trợ cú pháp cross-table khác.
B4 — Calculate Bom Items (GỌI formula_builder thật sự)
```python
from formula_builder.formula_utils.engine_public import FormulaEngine

engine = FormulaEngine(
    formulas=self.bom\_formulas,
    safe_funcs={"lookup_calc_pattern": ..., "lookup_rule": ..., "roundup": ...},
    on_error="default", default_value=0, deterministic=True,
)
result = engine.calculate(dict(self.inputs))
```
→ Đây là lần đầu tiên trong toàn bộ flow, code thật sự thực thi công thức. `FormulaEngine` tự:
Parse AST từng công thức, build dependency graph, topological sort (dòng nào cần dòng nào tính trước).
Chạy trong sandbox AST (chặn import/eval/lambda/dunder).
`on_error="default"` — 1 dòng lỗi không làm chết cả BOM, trả `0` + ghi vào `engine.last_errors`.
Kết quả merge ngược vào `self.inputs`, build `self.bom_result` (list dòng BOM với width/height/qty/unit_price/line_total/trace...).
B5 — Aggregate Cost Buckets
Gom `line_total` theo `cost_bucket` của từng dòng. Có 2 nhánh:
FB-max: nếu `AL Cost Bucket.source_type = "aggregate_from_items"` đã cấu hình `source_config` → gọi `formula_builder.api.batch_binding_resolver.resolve_all_bindings_batch` (native aggregate, giống SUMIF).
Fallback: bucket chưa cấu hình → cộng dồn bằng vòng lặp Python thường (`buckets[bk] += line_total`).
B6 — Calculate Cost Template (GỌI formula_builder lần 2, engine khác)
```python
from formula_builder.flexible_formula_engine import FlexibleFormulaEngine, EngineConfig

config = EngineConfig(
    global_formulas=[{"name": "TONG_VL", "formula": "VL_NHOM + VL_KINH + ..."}, ...],
    extra_context={**self.inputs, **self.buckets},
    custom_functions={"lookup_calc_pattern": ..., "lookup_rule": ..., "roundup": ...},
    on_error="default", default_value=0, deterministic=True,
)
engine = FlexibleFormulaEngine(config)
result = engine.calculate(dict(self.inputs))
```
→ Engine thứ 2 của formula_builder — `FlexibleFormulaEngine` (multi-table, dùng cho tổng hợp cấp cao: GIA_THANH, PROFIT, VAT, GIA_VAT...) khác với `FormulaEngine` (dùng ở B4 cho từng dòng vật tư). Cả 2 đều nằm trong `formula_builder`, alumglass chỉ truyền cấu hình.
B7 — Save Results
Gộp toàn bộ kết quả (`buckets`, `cost_template`, `lines`, `trace`, `errors`) thành 1 JSON duy nhất, ghi vào `Quotation Item` bằng 1 lệnh `set_value` + 1 lần `commit()` (tối ưu, không ghi rải rác nhiều lần).
---
7. Cơ chế biến — toàn bộ nguồn resolve giá trị
Đây là phần dễ gây nhầm lẫn nhất — biến đến từ 7 nguồn, resolve tuần tự trong `b1\_gather\_inputs()`, nguồn sau ghi đè nguồn trước:
#	Bước	Nguồn	Ghi chú
1.1	`extra_vars` trong `al_bom_vars`	User (dialog)	Biến tự do, không qua Variable Set
1.2	`Formula Global Variable`	DB, toàn cục	Hằng số (VAT_RATE, PROFIT_MARGIN mặc định...)
1.3	`AL Variable Library` (`is_system=1`)	DB, qua `system_variable_resolver.py`	OFFSET_DO_NGANG, NC_SX_PCT... resolve từ Profile System/Product Type — fallback, xem mục 9.4
1.4	`get_live_context()` (Formula Variable Binding)	formula_builder, native	Nguồn chính khi đã seed — override 1.3 nếu có binding tương ứng
1.4b	`AL Profile System.system_variables` (child table)	DB	Override tường minh theo từng Profile System cụ thể
1.5	`al_bom_vars` (user input)	Dialog	User luôn thắng cuối cùng — trừ 3 key đặc biệt (`extra_vars`, `accessory_set`, `glass_master`)
1.5b	Override config (`_accessory_set`, `_profile_system`, `_cost_template`, `glass_master`, `glass_master_map`)	Dialog	Không vào `self.inputs` trực tiếp — điều khiển hành vi B2/B6
1.6	Fallback default cho user var (`is_system=0`) chưa nhập	`AL Variable Library.default_value`	Tránh NameError khi công thức tham chiếu biến chưa nhập
Điểm mấu chốt cần nhớ: thứ tự ưu tiên là để user luôn override được mọi thứ, nhưng hệ thống luôn có giá trị mặc định hợp lý nếu user không nhập — không bao giờ NameError giữa chừng tính toán.
---
8. Tra giá composite key — mã đại diện + Pricing Dimension
8.1 Vì sao cần "mã đại diện" (`price_base_item`)
1 dòng BOM (`AL Bom Item`) có `item_code` riêng = hình dạng vật lý (quyết định trọng lượng/mét). Nhưng giá/kg lại phụ thuộc màu + xuất xứ + độ dày + bề mặt — không thể gắn N × M × K... dòng Item Price cho từng `item_code` riêng lẻ. Giải pháp: `price_base_item` = 1 mã chung đại diện (vd `NHOM-XINGFA`), Item Price của mã NÀY mới mang các field `custom_pd_*` (composite dimension).
```python
lit["unit_price"] = prices.get(pbi) if pbi else prices.get(ic)   # pbi ưu tiên
lit["weight_per_unit"] = weights.get(ic)                          # LUÔN theo item\_code riêng
```
→ Trọng lượng theo hình dạng thật, giá theo mã đại diện + dimension.
8.2 Matching — best-partial-match, không phải AND cứng
Với 1 mã đại diện, có thể có nhiều dòng Item Price (mỗi dòng set 1 tổ hợp dimension khác nhau, có thể không set đủ cả 4 field). Thuật toán (`engine/composite_pricing.py::best_partial_match`, dùng chung cho mọi nhánh):
Dòng nào không set 1 field composite → bỏ qua field đó (không loại dòng).
Dòng nào khớp nhiều field nhất với input hiện tại → thắng.
Không dòng nào khớp → rơi về dòng "trần" (không set field composite nào).
8.3 Lọc theo `material_category`
`AL Variable Dimension Mapping.material_category` đảm bảo dòng nhôm không bị áp nhầm dimension của kính và ngược lại — filter này áp dụng thống nhất ở cả 2 nhánh (FB-max và Python fallback, xem mục 9.5).
8.4 Kính — mã đại diện + đổi theo từng vị trí
Tương tự nhôm nhưng thêm 1 tầng: dialog cho phép chọn kính khác nhau cho từng vị trí (`glass_master_map: {rep: actual}`). Engine B2 resolve theo từng dòng (không dùng chung 1 giá trị cho cả BOM):
```python
gm_code = self.glass_master_map.get(default_gm) or self.glass_master_override or default_gm
```
→ `glass_data[slug]` (glass_thick/glass_type) build riêng theo dòng → Dynamic Item Rule (chọn nẹp kính theo độ dày) cũng resolve riêng theo dòng, không dùng chung 1 kết quả cho mọi vị trí nẹp.
---
9. Formula Builder tính toán thế nào — liên hệ chi tiết
`formula_builder` là 1 Frappe app riêng, độc lập nghiệp vụ (README tự mô tả: "Industry-agnostic — nền tảng chung cho mọi ngành"). AlumGlass cắm vào app này ở đúng 4 điểm, không sửa 1 dòng code nào của formula_builder.
9.1 Điểm nối #1 — `FormulaEngine` (dùng ở B4)
Engine lõi: parse công thức → AST → dependency graph → Kahn's topological sort → biên dịch bytecode → chạy trong sandbox AST (`SecurityValidator` chặn import/eval/lambda/`__dunder__`).
`safe_funcs` — dict hàm được phép gọi trong công thức. AlumGlass truyền vào 3 hàm nghiệp vụ riêng (`lookup_calc_pattern`, `lookup_rule`, `roundup`) — formula_builder không biết những hàm này là gì, chỉ chạy chúng như bất kỳ hàm Python nào trong whitelist.
`on_error="default"` — lỗi 1 công thức không làm sập cả DAG, engine tự thu thập lỗi vào `engine.last_errors`.
9.2 Điểm nối #2 — `FlexibleFormulaEngine` (dùng ở B6)
Engine multi-table (cấp cao hơn `FormulaEngine`), xử lý các công thức tổng hợp toàn cục (không gắn với 1 dòng cụ thể) — dùng cho Cost Template (GIA_THANH, PROFIT, VAT...).
`EngineConfig.extra_context` — nơi alumglass "bơm" toàn bộ `self.inputs` + `self.buckets` vào làm biến sẵn có cho công thức Cost Template dùng.
`EngineConfig.custom_functions` — giống hệt cơ chế `safe_funcs` ở B4, chỉ khác tên tham số vì đây là API riêng của `FlexibleFormulaEngine`.
9.3 Điểm nối #3 — `SourceTypeRegistry` + `fb_handlers.py` (đăng ký nguồn dữ liệu custom)
File `alumglass/fb_handlers.py` đăng ký 2-3 "source type" custom vào formula_builder qua decorator:
```python
from formula_builder.api.source_type_registry import register_source

@register_source("aluminum_price_composite", app="alumglass", ...)
def aluminum_price_composite(binding, doc, resolved_so_far):
    ...  # logic tra giá composite key — 100% code alumglass
```
Đăng ký qua `hooks.py::fb_source_types = ["alumglass.fb_handlers.aluminum_price_composite", ...]`. formula_builder tự động phát hiện (`SourceTypeRegistry._discover_from_hooks()`) và cho phép các Formula Variable Binding dùng `source_type="aluminum_price_composite"` — engine gọi lại đúng hàm alumglass đã đăng ký, không cần biết bên trong làm gì.
→ Đây là ranh giới đúng: formula_builder cho "chỗ cắm", alumglass cắm domain logic vào.
9.4 Điểm nối #4 — `BatchBindingResolver` / `resolve_all_bindings_batch` / `get_live_context`
`_resolve_fb_context()` (B1.4) gọi `formula\_builder.api.formula_builder.get_live_context(scope_json)` — trả context đầy đủ (biến global + system var) đã resolve qua Formula Variable Binding (doctype của formula_builder, KHÔNG phải `AL Variable Library` của alumglass).
`_fetch_composite_prices_via_fb()` (B2) và `_resolve_cost_buckets_via_fb()` (B5) gọi `formula_builder.api.batch_binding_resolver.resolve_all_bindings_batch(bindings, pre_resolved=row_ctx)` — batch-resolve nhiều binding cùng lúc, giảm N+1 query.
Quan trọng — 2 con đường song song đang tồn tại (có chủ đích, đang trong quá trình di trú):
	Đường CŨ (alumglass tự viết)	Đường MỚI (formula_builder native)
System variable (OFFSET_*, NC_SX_PCT...)	`AL Variable Library` + `system_variable_resolver.py`	`Formula Variable Binding` (`source_type=linked_doctype_field`)
Composite pricing (nhôm/kính)	`bom_orchestrator._fetch_composite_prices()` (Python fallback)	`_fetch_composite_prices_via_fb()` + FVB `aluminum_price_composite`
Cost Bucket aggregate	`b5_aggregate_cost_buckets()` vòng lặp Python	FVB `aggregate_from_items`
Ở mỗi cặp trên, đường MỚI ưu tiên hơn nếu có binding cấu hình sẵn (`is_active=1`), đường CŨ chỉ chạy khi KHÔNG có binding — đây là lưới an toàn khi di trú, không phải 2 kiến trúc cạnh tranh nhau mãi mãi. Nguyên tắc chung: càng dùng được cơ chế có sẵn của formula_builder càng tốt — chỉ viết code alumglass riêng khi 13 source type có sẵn không diễn đạt được (hoặc cần thuật toán nghiệp vụ riêng như best-partial-match).
9.5 Điều đảm bảo 2 đường luôn cho cùng kết quả
Vì 2 đường trên có thể "đổi ca" cho nhau (tùy binding có active hay không), toàn bộ thuật toán thật (best-partial-match, lọc material_category) được tách vào 1 module dùng chung (`engine/composite_pricing.py`) — cả `fb_handlers.py::aluminum_price_composite` (đường mới) lẫn `bom_orchestrator._fetch_composite_prices()` (đường cũ) đều gọi lại cùng 1 hàm — không viết 2 lần, không lệch kết quả tùy đường nào đang chạy.
---
10. Validate công thức — 2 lớp
Lớp	Ở đâu	Chặn cứng hay cảnh báo	Nguồn `known_names`
Client (JS, lúc gõ)	`public/js/cost_template.js` (Cost Template), `formula_setup.js` (autocomplete mọi doctype)	Chặn cứng (`frappe.validated=false`) chỉ với Cost Template	Regex tokenizer riêng, mirror tay whitelist hàm server
Server (Python, lúc save)	`alumglass/al_bom_engine/formula_validate.py` — dùng chung cho Cost Template, Bom Item, Accessory Item	Cost Template: chỉ cảnh báo. Bom Item/Accessory Item: chặn cứng (chưa có lớp client)	`get_formula_context()` — merge CẢ `Formula Variable Binding` (formula_builder) LẪN `AL Variable Library` (alumglass), dedup theo tên
`FormulaValidator` (AST-based, từ `formula_builder.formula_utils`) là engine validate thật — alumglass chỉ truyền `known_names` (universe biến hợp lệ) + whitelist hàm (`BASE_FUNCS` của formula_builder ∪ hàm custom alumglass).
---
11. Snapshot — 2 cơ chế khác nhau, đừng nhầm lẫn
11.1 `AL BOM Version` snapshot — snapshot CẤU HÌNH (công thức/rule)
Tạo khi 1 version được insert (`before_insert`) — chụp:
`bom_set_snapshot` — toàn bộ `AL Bom Set` + `AL Bom Item` tại thời điểm đó.
`cost_template_snapshot` — toàn bộ `AL Cost Template` + `AL Cost Template Item`.
`pricing_dimension_snapshot` — toàn bộ `AL Pricing Dimension` + `AL Variable Dimension Mapping` (P1 — đảm bảo composite pricing tái lập được dù cấu hình dimension đổi sau này).
Bất biến hóa: `validate()::_guard_published_immutability()` chặn sửa 3 field trên sau khi `workflow\_state = "Published"` — muốn đổi công thức phải tạo version MỚI (qua `AL Design Revision`), không sửa version cũ.
→ Đây là snapshot engine B0-B6 THẬT SỰ ĐỌC khi tính giá — không đọc `AL Bom Set` sống.
11.2 `ConfigSnapshot` — snapshot KẾT QUẢ (audit trail báo giá)
Tạo khi Submit Quotation (`doc_events on_submit` → `quotation_events.py::on_submit`), không phải mỗi lần bấm "Tính giá" (quyết định của Owner — tránh tạo rác mỗi lần user thử số liệu):
`inputs_json` = `al_bom_vars` (những gì user đã nhập).
`result_json` = `al_bom_result` (kết quả engine trả về).
`bom_version` = version đã dùng để tính.
→ Đây là bằng chứng "báo giá này được tính từ input gì, ra kết quả gì, dùng version cấu hình nào" — phục vụ tra soát về sau, độc lập với việc cấu hình có bị sửa tiếp hay không.
Tóm gọn khác biệt: BOM Version snapshot = "công thức lúc đó là gì", ConfigSnapshot = "lần tính đó ra số bao nhiêu, từ input gì".
---
12. Kết quả trả về & nơi lưu trữ
`b7_save_results()` ghi 1 JSON duy nhất vào `Quotation Item.al_bom_result`:
```json
{
  "buckets": {"VL_NHOM": 5000000, "VL_KINH": 3000000, ...},
  "cost_template": {"TONG_VL": 8000000, "GIA_THANH": 9500000, "GIA_BAN": 10500000, "GIA_VAT": 11550000, ...},
  "cost_template_trace": {"NC_SX": "8%=0.08 × TONG_VL=8000000 = 640000", ...},
  "lines": [{"slug": "khung_bao", "item_code": "...", "width": 2400, "line_total": 120000, "trace": "...", ...}],
  "gia_vat": 11550000,
  "errors": {"bom_items": {}, "cost_template": {}}
}
```
Đồng thời ghi tắt `al_gia_vat`/`al_gia_ban` (2 field số riêng, tiện query/report không cần parse JSON). Dialog đọc lại JSON này để render bảng chi tiết + trace giải thích từng dòng.
---
13. Sơ đồ tổng kết toàn bộ luồng
```
┌───────────────┐     al_bom_vars (JSON)      ┌────────────────────────┐
│  Dialog UI    │ ──────────────────────────► │  Quotation Item        │
│ (quotation.js)│                             │  (Frappe doctype)      │
└──────┬────────┘                             └───────────┬────────────┘
       │ click "Tính giá"                                 │
       ▼                                                  │
┌────────────────────────┐   sync/async theo số dòng      │
│ api.calculate\_bom()   │◄───────────────────────────────┘
└──────────┬─────────────┘
           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    BomOrchestrator.run()                                │
│                                                                         │
│  B0 Version Pinning ──► AL BOM Version (snapshot bất biến)              │
│         │                                                               │
│  B1 Gather Inputs ──► 7 nguồn biến (mục 7), FVB override                │
│         │                                                               │
│  B2 Prefetch ──► Item/ItemPrice/GlassMaster (composite key)             │
│         │              │                                                │
│         │              └──► fb\_handlers.py (nếu FVB active)            │
│         │                        │                                      │
│  B3 Build Formulas               │  formula_builder.SourceTypeRegistry  │
│         │                        ▼                                      │
│  B4 Calculate Bom Items ──► [FORMULA_BUILDER: FormulaEngine]            │
│         │                    DAG + sandbox AST + safe_funcs             │
│  B5 Aggregate Buckets ──► (FVB aggregate_from_items | Python loop)      │
│         │                                                               │
│  B6 Calculate Cost Tpl ──► [FORMULA_BUILDER: FlexibleFormulaEngine]     │
│         │                                                               │
│  B7 Save Results ──► Quotation Item.al_bom_result (1 commit)            │
└─────────────────────────────────────────────────────────────────────────┘
           │
           ▼ trả {buckets, cost\_template, lines}
┌───────────────┐
│  Dialog hiện  │
│  kết quả      │
└──────┬────────┘
       │ Submit Quotation
       ▼
┌───────────────────────────────┐
│ quotation\_events.on\_submit  │──► tạo ConfigSnapshot (audit trail bất biến)
└───────────────────────────────┘
```
---
14. Phụ lục — bảng tra nhanh file/hàm theo chủ đề
Chủ đề	File	Hàm/class chính
Entry point API	`alumglass/api/__init__.py`	`calculate_bom`, `_enqueue_bom_calculation`, `_run_bom_calculation_job`
Engine chính	`alumglass/engine/bom_orchestrator.py`	`BomOrchestrator.run()`, `b0`...`b7`
Dialog nhập liệu	`alumglass/alumglass/doctype/overrides/quotation.js`	`_render_vars_container`, `_make_var_control`, `_save`
Biến (Variable)	`alumglass/al_bom_engine/system_variable_resolver.py`	`resolve_source_record_names`, `resolve_system_variable_values`
Composite pricing	`alumglass/engine/composite_pricing.py`	`best_partial_match`
Custom source type (formula_builder plug-in)	`alumglass/fb_handlers.py`	`aluminum_price_composite`, `glass_master_data`, `cost_bucket_aggregate`
Validate công thức	`alumglass/al_bom_engine/formula_validate.py`	`build_known_names`, `check_formula`, `check_formula_fields`
Snapshot cấu hình	`alumglass/al_bom_engine/doctype/al_bom_version/al_bom_version.py`	`before_insert`, `_take_snapshots`, `_snapshot_pricing_dimensions`
Snapshot kết quả	`alumglass/api/quotation_events.py`	`on_submit`
Engine tính toán (bên formula_builder)	`formula_builder/formula_utils/engine_public.py`	`FormulaEngine`
Engine multi-table (bên formula_builder)	`formula_builder/flexible_formula_engine.py`	`FlexibleFormulaEngine`, `EngineConfig`
Batch resolver (bên formula_builder)	`formula_builder/api/batch_binding_resolver.py`	`resolve_all_bindings_batch`
Source type registry (bên formula_builder)	`formula_builder/api/source_type_registry.py`	`register_source`, `SourceTypeRegistry`
