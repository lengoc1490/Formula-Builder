frappe.provide("formula_builder.formula");

// ── Hằng số mặc định (fallback khi không có setting) ─────────────────────────
const _DEFAULT_FIELD_LANGUAGE_MAP = {
  "JSON"        : "json",
  "Code"        : "python",
  "Small Text"  : "plaintext",
  "HTML"        : "html",
  "HTML Editor" : "html",
  "Text"        : "plaintext",
  "Long Text"   : "plaintext",
  "Data"        : "plaintext",
  "Text Editor" : "html",
};

const _DEFAULT_SKIP_FIELDTYPES = [
  "Section Break","Column Break","Tab Break","Heading","Button",
  "Image","Attach","Attach Image","Barcode","Signature","Table",
  "Table MultiSelect","Check","Select","Link","Dynamic Link",
  "Date","Time","Datetime","Duration","Color","Icon","Rating",
  "Geolocation","Password","Int","Float","Currency","Percent",
  "Read Only","HTML","HTML Editor",
];

const _DEFAULT_HEIGHTS = {
  "JSON"       : "160px",
  "Code"       : "180px",
  "HTML"       : "160px",
  "HTML Editor": "160px",
  "Long Text"  : "140px",
  "Text"       : "100px",
  "Small Text" : "72px",
  "Data"       : "80px",
};

/**
 * Lấy config từ window._afbFieldConfig nếu có, fallback về giá trị mặc định.
 * window._afbFieldConfig có thể được set từ bên ngoài (settings, boot, server config):
 *   window._afbFieldConfig = {
 *     language_map : { "Code": "python", ... },   // override/extend
 *     skip_fieldtypes: [...],                      // override toàn bộ
 *     heights      : { "Code": "200px", ... },     // override/extend
 *     global_vars  : [{ name, label, value }, ...] // thay _inlineGlobalVars
 *   };
 */
function _getFieldConfig() {
  const ext = window._afbFieldConfig || {};
  return {
    language_map    : Object.assign({}, _DEFAULT_FIELD_LANGUAGE_MAP, ext.language_map || {}),
    skip_fieldtypes : new Set(ext.skip_fieldtypes || _DEFAULT_SKIP_FIELDTYPES),
    heights         : Object.assign({}, _DEFAULT_HEIGHTS, ext.heights || {}),
    global_vars     : ext.global_vars || window._inlineGlobalVars || [],
  };
}

// Cached getters – invalidate nếu _afbFieldConfig thay đổi
let _cfgCache = null;
let _cfgCacheRef = null;
function _cfg() {
  const ref = window._afbFieldConfig;
  if (_cfgCache && _cfgCacheRef === ref) return _cfgCache;
  _cfgCache    = _getFieldConfig();
  _cfgCacheRef = ref;
  return _cfgCache;
}

// Compat aliases cho code bên dưới
const FIELD_LANGUAGE_MAP  = new Proxy({}, { get: (_, k) => _cfg().language_map[k] });
const SKIP_FIELDTYPES     = new Proxy(new Set(), {
  get: (_, k) => typeof Set.prototype[k] === "function"
    ? (...args) => _cfg().skip_fieldtypes[k](...args)
    : _cfg().skip_fieldtypes[k],
});
const DEFAULT_HEIGHTS     = new Proxy({}, { get: (_, k) => _cfg().heights[k] });

window._afbPatchedEditors = window._afbPatchedEditors || {};
const _patchedEditors = window._afbPatchedEditors;

// ── Helpers chung ─────────────────────────────────────────────────────────────
function _getFrmDocJsonForScope(scope) {
  // Delegate to shared serializer in formula_builder.js (§9)
  if (typeof formula_builder?.formula?._serializeDoc === "function") {
    return formula_builder.formula._serializeDoc(scope?.current_doctype, scope?.current_docname);
  }
  // Fallback if formula_builder.js not yet loaded
  try {
    const doctype = scope?.current_doctype;
    if (!doctype) return null;
    let frm = null;
    try { frm = cur_frm && cur_frm.doctype === doctype ? cur_frm : null; } catch {}
    if (!frm?.doc) return null;
    const doc  = frm.doc;
    const meta = frappe.get_meta?.(doctype);
    if (!meta) return null;
    const SKIP = new Set(["Section Break","Column Break","Tab Break","Heading","Button",
                          "HTML","Image","Attach","Attach Image","Barcode","Signature",
                          "Table","Table MultiSelect"]);
    const result = {};
    meta.fields.forEach(f => {
      if (SKIP.has(f.fieldtype)) return;
      const v = doc[f.fieldname];
      if (v !== undefined && v !== null) result[f.fieldname] = v;
    });
    meta.fields
      .filter(f => f.fieldtype === "Table" || f.fieldtype === "Table MultiSelect")
      .forEach(tableMf => {
        const rows      = doc[tableMf.fieldname] || [];
        const childMeta = frappe.get_meta?.(tableMf.options);
        result[tableMf.fieldname] = rows.map(row => {
          const rowData = {};
          if (childMeta) {
            childMeta.fields.forEach(cf => {
              if (SKIP.has(cf.fieldtype)) return;
              const v = row[cf.fieldname];
              if (v !== undefined && v !== null) rowData[cf.fieldname] = v;
            });
          } else {
            Object.keys(row).forEach(k => { if (!k.startsWith("__")) rowData[k] = row[k]; });
          }
          if (row.idx !== undefined) rowData.idx = row.idx;
          if (row.name) rowData.name = row.name;
          return rowData;
        });
      });
    return JSON.stringify(result);
  } catch (e) {
    console.warn("[FormulaBuilder FieldPatch] _getFrmDocJsonForScope error:", e);
    return null;
  }
}

function _editorKey(frm, fieldname) {
  return `${frm.doctype}::${frm.docname || "__new__"}::${fieldname}`;
}

function _getFieldValue(frm, fieldname) {
  return frm.doc[fieldname] || "";
}

function _resolveLanguage(field_meta, override) {
  if (override) return override;
  const ft = field_meta?.fieldtype || "Data";
  return _cfg().language_map[ft] || "plaintext";
}

function _defaultHeight(fieldtype) {
  return _cfg().heights[fieldtype] || "80px";
}

function _esc(str) {
  // Reuse from formula_builder.js when available; otherwise define locally
  if (typeof formula_builder?.formula?._esc === "function") return formula_builder.formula._esc(str);
  return String(str || "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ── CSS — CRITICAL runtime injection (must match OLD code exactly) ─────────
// OLD code inject CSS at runtime AFTER Frappe desk CSS → always wins cascade.
// NEW code's external CSS (app_include_css) loads BEFORE Frappe → overridden.
// This function replicates the OLD behavior: inject all field-patch CSS at
// runtime when first patchField/patchChildField/initGridField is called.
function _ensureFieldPatchCSS() {
  if (document.getElementById("afb-field-patch-css-v3")) return;
  const s = document.createElement("style");
  s.id = "afb-field-patch-css-v3";
  s.textContent = `
    /* ── Field patch wrap ──────────────────────────────────────────────── */
    .afb-fp-wrap {
      border: 1px solid var(--afb-border, #cbd5e1);
      border-radius: var(--afb-radius, 6px);
      overflow: hidden;
      background: var(--afb-bg0, #fff);
      transition: border-color var(--afb-tr, 150ms), box-shadow var(--afb-tr, 150ms);
      position: relative;
    }
    .afb-fp-wrap:focus-within {
      border-color: var(--afb-amber, #f59e0b);
      box-shadow: 0 0 0 3px rgba(245,158,11,.12);
    }
    .afb-fp-toolbar {
      display: flex; align-items: center; gap: 6px;
      padding: 4px 8px;
      background: var(--afb-bg1, #f8fafc);
      border-bottom: 1px solid var(--afb-border, #cbd5e1);
      font-size: 11px;
    }
    .afb-fp-lang-badge {
      font-family: var(--afb-mono, monospace);
      font-size: 10px;
      background: var(--afb-bg3, #e2e8f0);
      color: var(--afb-text2, #334155);
      padding: 2px 7px; border-radius: 3px;
      font-weight: 600; letter-spacing: .3px;
    }
    .afb-fp-monaco {
      border-radius: 0;
      overflow: hidden;
      position: relative;
    }
    .afb-fp-monaco .monaco-editor .overflow-guard {
      overflow: hidden !important;
    }
    .afb-fp-monaco .monaco-editor .view-lines {
      padding-bottom: 4px !important;
    }
    .overflowingContentWidgets .suggest-widget {
      z-index: 100000 !important;
    }
    .afb-fp-preview {
      display: flex; align-items: center; gap: 5px;
      padding: 3px 6px 3px 8px;
      background: var(--afb-bg1, #f8fafc);
      border-top: 1px solid var(--afb-border, #cbd5e1);
      font-size: 11px; font-family: var(--afb-mono, monospace);
      min-height: 24px; user-select: none;
    }
    .afb-fp-preview-icon {
      color: var(--afb-text3, #64748b);
      flex-shrink: 0; font-size: 10px;
    }
    .afb-fp-preview-val {
      flex: 1;
      color: var(--afb-text3, #64748b);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      transition: color 150ms;
    }
    .afb-fp-preview-val.ok    { color: var(--afb-green, #10b981); font-weight: 600; }
    .afb-fp-preview-val.error { color: var(--afb-red, #ef4444); }
    .afb-fp-preview-val.running { color: var(--afb-amber, #f59e0b); }
    .afb-fp-btn {
      cursor: pointer;
      font-size: 10px; flex-shrink: 0;
      padding: 2px 7px; border-radius: 3px;
      border: 1px solid var(--afb-border, #cbd5e1);
      background: var(--afb-bg3, #e2e8f0);
      color: var(--afb-text2, #334155);
      transition: background var(--afb-tr, 150ms), border-color var(--afb-tr, 150ms);
      font-family: var(--afb-ui, sans-serif);
      line-height: 1.4;
    }
    .afb-fp-btn:hover { background: var(--afb-bg4, #cbd5e1); }
    .afb-fp-btn.dialog-btn {
      border-color: var(--afb-amber, #f59e0b);
      color: var(--afb-amber, #f59e0b);
    }
    .afb-fp-btn.dialog-btn:hover {
      background: rgba(245,158,11,.1);
    }
    .afb-fp-val-tooltip {
      position: fixed;
      z-index: 99999;
      background: #1e293b;
      color: #f1f5f9;
      border-radius: 5px;
      padding: 5px 10px;
      font-size: 11px;
      font-family: var(--afb-mono, monospace);
      pointer-events: none;
      opacity: 0;
      transition: opacity 120ms;
      max-width: 320px;
      word-break: break-all;
      box-shadow: 0 4px 12px rgba(0,0,0,.25);
      line-height: 1.5;
    }
    .afb-fp-val-tooltip.visible { opacity: 1; }
    .afb-fp-val-tooltip-name {
      color: #93c5fd; font-weight: 700; font-size: 11px; display: block;
    }
    .afb-fp-val-tooltip-val {
      color: #86efac; font-size: 12px; display: block; margin-top: 2px;
    }
    .afb-fp-val-tooltip-meta {
      color: #94a3b8; font-size: 10px; display: block; margin-top: 2px;
    }

    /* ── Backward compat aliases ───────────────────────────────────────── */
    .aluglass-field-patch-wrap { border:1px solid var(--afb-border,#cbd5e1);border-radius:var(--afb-radius,6px);overflow:hidden;background:#fff;transition:border-color 150ms,box-shadow 150ms; }
    .aluglass-field-patch-wrap:focus-within { border-color:var(--afb-amber,#f59e0b);box-shadow:0 0 0 3px rgba(245,158,11,.12); }
    .aluglass-fp-toolbar  { display:flex;align-items:center;gap:6px;padding:4px 8px;background:var(--afb-bg1,#f8fafc);border-bottom:1px solid var(--afb-border,#cbd5e1);font-size:11px; }
    .aluglass-fp-lang-badge { font-family:monospace;font-size:10px;background:var(--afb-bg3,#e2e8f0);color:var(--afb-text2,#334155);padding:2px 7px;border-radius:3px;font-weight:600; }
    .aluglass-fp-monaco   { overflow:visible;position:relative; }
    .aluglass-fp-monaco .monaco-editor .overflow-guard { overflow:visible !important; }
    .aluglass-btn { display:inline-flex;align-items:center;gap:5px;padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid var(--afb-border,#cbd5e1);background:var(--afb-bg3,#e2e8f0);color:var(--afb-text,#1e293b);outline:none;white-space:nowrap;transition:background 150ms,border-color 150ms; }
    .aluglass-btn:hover { background:var(--afb-bg4,#cbd5e1); }

    /* ── Inline grid cell ──────────────────────────────────────────────── */
    .afb-grid-cell-wrap {
      position: relative;
      width: 100%;
    }
    .afb-grid-cell-editor {
      position: absolute;
      inset: 0;
      z-index: 10;
      background: #fff;
      border: 1.5px solid var(--afb-amber, #f59e0b);
      border-radius: 4px;
      box-shadow: 0 2px 8px rgba(245,158,11,.15);
      overflow: visible;
    }
    .afb-grid-cell-static {
      padding: 3px 6px;
      font-size: 12px;
      font-family: var(--afb-mono, monospace);
      color: var(--afb-text, #1e293b);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-height: 24px;
      line-height: 24px;
      cursor: text;
    }
    .afb-grid-cell-static:empty::before {
      content: "—";
      color: var(--afb-text3, #94a3b8);
    }

    /* Float popup mode */
    .afb-grid-float-popup {
      position: absolute;
      z-index: 9999;
      background: #fff;
      border: 2px solid var(--afb-amber, #f59e0b);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(0,0,0,.18), 0 2px 8px rgba(245,158,11,.12);
      overflow: visible;
    }
    .afb-grid-float-popup .afb-fp-wrap,
    .afb-grid-float-popup .afb-grid-cell-editor {
      height: 100% !important;
      border: none !important;
      border-radius: 6px !important;
      box-shadow: none !important;
    }
    .afb-grid-float-popup::before {
      content: "";
      position: absolute;
      bottom: -8px; left: 20px;
      border: 8px solid transparent;
      border-bottom: none;
      border-top-color: var(--afb-amber, #f59e0b);
    }

    /* ── Frappe grid overrides (injected at runtime → beats Frappe CSS) ── */
    /* overflow:visible cho grid container đã chuyển sang xử lý động bởi
       _fixGridContainBlock (chỉ bật khi editor focus, restore khi blur).     */
    /* Prevent Frappe contain:paint/content from trapping position:fixed */
    .grid-row-open .form-in-grid,
    .grid-row-open .grid-form-body,
    .grid-row-open .grid-form-row {
      contain: none !important;
      container-type: normal !important;
    }
    .afb-grid-cell-editor .monaco-editor,
    .afb-grid-cell-editor .monaco-editor .overflow-guard {
      overflow: visible !important;
    }
    .afb-grid-cell-editor .monaco-editor .view-lines {
      padding-bottom: 4px !important;
    }
    .afbd-dialog .overflowingContentWidgets .suggest-widget {
      z-index: 110000 !important;
    }
  `;
  document.head.appendChild(s);
}

let _valTooltipEl = null;
function _getValTooltip() {
  if (_valTooltipEl && document.body.contains(_valTooltipEl)) return _valTooltipEl;
  _valTooltipEl = document.createElement("div");
  _valTooltipEl.className = "afb-fp-val-tooltip";
  document.body.appendChild(_valTooltipEl);
  return _valTooltipEl;
}

// ── Grid body contain fix ──────────────────────────────────────────────────────
// Frappe v15/v16 dùng `contain: content/paint` trên .grid-body để tối ưu
// performance. Contain tạo containing block cho `position: fixed`, khiến
// ── Fix Frappe grid containing-block ─────────────────────────────────────────
// Frappe v15/v16 uses CSS properties on grid containers that create a
// containing block for `position: fixed`. Monaco's fixedOverflowWidgets
// uses `position: fixed` to position suggest widgets. When trapped inside
// a containing block, the suggest widget:
//   1. Gets positioned relative to the grid instead of the viewport (văng xa)
//   2. Gets clipped by overflow:hidden on the grid container (che công thức)
//
// Properties that create containing blocks for position:fixed:
//   transform, filter, backdrop-filter, perspective, will-change,
//   contain:paint, contain:layout, contain:strict, contain:content,
//   container-type (any non-normal value)
//
// This helper walks up the DOM from the editor to the body and temporarily
// neutralizes these properties. All values are restored when the editor is
// disposed, so Frappe layout is only affected while the user is typing.
function _fixGridContainBlock(editorContainer) {
  // Chỉ chạy khi editor nằm trong grid context
  if (!editorContainer.closest('.grid-body, .form-in-grid')) return function(){};

  // Với fixedOverflowWidgets:false, suggest dùng position:absolute nằm trong
  // editor. Chỉ cần set overflow:visible trên editor containers và .control-input
  // (wrapper trực tiếp của field) để suggest thoát ra khỏi editor.
  // KHÔNG leo lên .grid-form-body / .grid-form-row / .form-in-grid / .grid-body
  // vì đó là các container có scrollbar của bảng con.
  var restores = [];
  var el = editorContainer;
  while (el && el !== document.body) {
    // Dừng ngay khi gặp bất kỳ grid container nào — giữ nguyên scrollbar hệ thống
    if (el.classList.contains('grid-form-body') ||
        el.classList.contains('grid-form-row') ||
        el.classList.contains('form-in-grid') ||
        el.classList.contains('grid-body')) break;

    var ovX = getComputedStyle(el).getPropertyValue('overflow-x');
    var ovY = getComputedStyle(el).getPropertyValue('overflow-y');
    if ((ovX && ovX !== 'visible') || (ovY && ovY !== 'visible')) {
      restores.push({
        el: el,
        origOvX: el.style.getPropertyValue('overflow-x'),
        origOvY: el.style.getPropertyValue('overflow-y'),
      });
      el.style.setProperty('overflow-x', 'visible', 'important');
      el.style.setProperty('overflow-y', 'visible', 'important');
    }
    el = el.parentElement;
  }
  return function() {
    restores.forEach(function(r) {
      if (r.origOvX) r.el.style.setProperty('overflow-x', r.origOvX, 'important');
      else           r.el.style.removeProperty('overflow-x');
      if (r.origOvY) r.el.style.setProperty('overflow-y', r.origOvY, 'important');
      else           r.el.style.removeProperty('overflow-y');
    });
  };
}

// ── ContextBuilder helper ─────────────────────────────────────────────────────
function _buildContext({ frm, childTableField, cdn }) {
  if (formula_builder.formula._ContextBuilder?.build) {
    return formula_builder.formula._ContextBuilder.build({ frm, childTableField, cdn, liveCtx: null });
  }
  const SKIP = new Set(["Section Break","Column Break","Tab Break","Heading","Button",
                        "Image","Attach","Attach Image","Barcode","Signature","Table","Table MultiSelect"]);
  const parentMeta = frappe.get_meta?.(frm?.doctype);
  const parentFields = (parentMeta?.fields || [])
    .filter(mf => !SKIP.has(mf.fieldtype) && mf.fieldtype !== "Table" && mf.fieldtype !== "Table MultiSelect")
    .map(mf => ({
      name: mf.fieldname, label: mf.label || mf.fieldname,
      fieldtype: mf.fieldtype, doctype: frm.doctype,
      source: "parent", value: frm.doc?.[mf.fieldname], insert: mf.fieldname,
    }));
  let currentRowFields = [], childDoctype = null;
  if (childTableField && cdn) {
    childDoctype = parentMeta?.fields?.find(f => f.fieldname === childTableField)?.options;
    if (childDoctype) {
      const childMeta = frappe.get_meta?.(childDoctype);
      const row = (frm.doc?.[childTableField] || []).find(r => r.name === cdn) || {};
      currentRowFields = (childMeta?.fields || [])
        .filter(mf => !SKIP.has(mf.fieldtype))
        .map(mf => ({
          name: mf.fieldname, label: mf.label || mf.fieldname,
          fieldtype: mf.fieldtype, doctype: childDoctype,
          source: "current_row", value: row[mf.fieldname], insert: mf.fieldname, rowName: cdn,
        }));
    }
  }
  const siblingItems = [];
  (parentMeta?.fields || [])
    .filter(mf => mf.fieldtype === "Table" || mf.fieldtype === "Table MultiSelect")
    .forEach(tableMf => {
      const tblField   = tableMf.fieldname;
      const tblDoctype = tableMf.options;
      const tblMeta    = frappe.get_meta?.(tblDoctype);
      const rows       = frm.doc?.[tblField] || [];
      const cfNames    = (tblMeta?.fields || []).filter(f => !SKIP.has(f.fieldtype));
      const rowCount   = rows.length || 1;
      for (let idx = 0; idx < Math.min(rowCount, 30); idx++) {
        const row = rows[idx] || {};
        cfNames.forEach(cf => {
          siblingItems.push({
            name    : `${tblField}[${idx}].${cf.fieldname}`,
            label   : `${cf.label || cf.fieldname} — hàng ${idx + 1}`,
            fieldtype: cf.fieldtype,
            doctype : tblDoctype,
            source  : tblField === childTableField ? "current_table" : "sibling_table",
            value   : row[cf.fieldname],
            insert  : `${tblField}[${idx}].${cf.fieldname}`,
            tableName: tblField,
            rowIdx  : idx,
            rowName : row.name,
          });
        });
      }
    });
  const globalVars = _cfg().global_vars.map(v => ({
    name: "$" + v.name, label: v.label || v.name,
    fieldtype: "Currency / Data", doctype: "Global Variable",
    source: "global", value: v.value, insert: "$" + v.name,
  }));
  return {
    parentFields, currentRowFields, siblingItems,
    globalVars, refs: [], localVars: [],
    allItems: [...currentRowFields, ...parentFields, ...siblingItems, ...globalVars],
  };
}

// ── Completion handler ────────────────────────────────────────────────────────
function _buildCompletionHandler(editorRef, contextFn) {
  if (typeof _buildCompletionHandlerV3 === "function") {
    return _buildCompletionHandlerV3(editorRef, contextFn);
  }
  const fnReg = formula_builder.formula.FunctionRegistry;
  return function(model, pos) {
    if (model !== editorRef.getModel?.()) return { suggestions: [] };
    const MK   = monaco.languages.CompletionItemKind;
    const word = model.getWordUntilPosition(pos);
    const lineBefore = model.getLineContent(pos.lineNumber).substring(0, pos.column);
    const range = {
      startLineNumber: pos.lineNumber, endLineNumber: pos.lineNumber,
      startColumn: word.startColumn,   endColumn: pos.column,
    };
    const ctx  = contextFn ? contextFn() : { allItems:[], currentRowFields:[], siblingItems:[], globalVars:[], parentFields:[], refs:[], localVars:[] };
    const seen = new Set();
    const items = [];
    const add = item => { if (!seen.has(item.label)) { seen.add(item.label); items.push({ range, ...item }); } };
    const tblDotMatch = lineBefore.match(/(\w+)\[\d+\]\.$/);
    if (tblDotMatch) {
      const tblName = tblDotMatch[1];
      ctx.siblingItems.filter(s => s.tableName === tblName).forEach(s => add({
        label: s.name.split(".").pop(), kind: MK.Field,
        insertText: s.name.split(".").pop(),
        detail: `${s.fieldtype} · hàng ${(s.rowIdx||0)+1}${s.value != null ? " · " + String(s.value) : ""}`,
        documentation: `**${s.name}**\n\nGiá trị: \`${s.value ?? "null"}\`\nDoctype: ${s.doctype}`,
        sortText: "0_" + s.name,
      }));
      return { suggestions: items };
    }
    const tblIdxMatch = lineBefore.match(/(\w+)\[$/);
    if (tblIdxMatch) {
      const tblName = tblIdxMatch[1];
      const indices = [...new Set(ctx.siblingItems.filter(s => s.tableName === tblName).map(s => s.rowIdx))];
      if (!indices.length) indices.push(0);
      indices.forEach(idx => add({ label: String(idx), kind: MK.Value, insertText: String(idx), detail: `Hàng ${idx+1}`, sortText: "0i_" + idx }));
      return { suggestions: items };
    }
    if (lineBefore.match(/\b\w+\.$/)) {
      ctx.allItems.forEach(s => add({
        label: s.name, kind: MK.Field, insertText: s.insert,
        detail: `${s.fieldtype||""} · ${s.doctype||""}`,
        sortText: "0_" + s.name,
      }));
      return { suggestions: items };
    }
    ctx.currentRowFields.forEach(f => add({
      label: f.name, kind: MK.Field, insertText: f.insert,
      detail: `${f.fieldtype} · hàng hiện tại${f.value != null ? " = " + String(f.value) : ""}`,
      documentation: `**${f.name}**\n\nGiá trị: \`${f.value ?? "null"}\`\nDoctype: ${f.doctype}`,
      sortText: "1_" + f.name,
    }));
    ["IF","IFS","IIF","SWITCH","and_","or_","not_","True","False","None","in"].forEach(kw =>
      add({ label: kw, kind: MK.Keyword, insertText: kw, sortText: "2k_" + kw })
    );
    fnReg.getAll().forEach(f => add({
      label: f.name, kind: MK.Function,
      insertText: f.name + "($1)",
      insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
      documentation: `**${f.sig}**\n\n${f.desc}\n\n_${f.example}_`,
      detail: `ƒ ${f.cat}`, sortText: "3_" + f.name,
    }));
    const isGlobalCtx = lineBefore.endsWith("$") || word.word.startsWith("$");
    ctx.globalVars.forEach(v => add({
      label: v.name, kind: MK.Variable, insertText: v.insert,
      detail: `🌍 ${v.value != null ? v.value : "—"}`,
      sortText: (isGlobalCtx ? "1g_" : "4g_") + v.name,
    }));
    ctx.localVars.forEach(v => add({
      label: v.name, kind: MK.Field, insertText: v.insert,
      detail: `${v.fieldtype} · ${v.doctype}${v.value != null ? " = " + v.value : ""}`,
      sortText: "4l_" + v.name,
    }));
    ctx.parentFields.forEach(f => add({
      label: f.name, kind: MK.Field, insertText: f.insert,
      detail: `${f.fieldtype} · ${f.doctype}${f.value != null ? " = " + String(f.value) : ""}`,
      documentation: `**${f.name}**\n\nGiá trị: \`${f.value ?? "null"}\`\nDoctype: ${f.doctype}`,
      sortText: "5_" + f.name,
    }));
	
    {
      const tblMap = new Map();
      ctx.siblingItems.forEach(s => {
        if (!tblMap.has(s.tableName)) tblMap.set(s.tableName, []);
        tblMap.get(s.tableName).push(s);
      });
      const perTable = Math.max(3, Math.floor(30 / Math.max(tblMap.size, 1)));
      tblMap.forEach(group => {
        group.slice(0, perTable).forEach(s => add({
          label: s.name, kind: MK.Field, insertText: s.insert,
          detail: `${s.fieldtype} · hàng ${(s.rowIdx||0)+1}${s.value != null ? " = " + String(s.value) : ""}`,
          documentation: `**${s.name}**\n\nGiá trị: \`${s.value ?? "null"}\`\nDoctype: ${s.doctype}`,
          sortText: "6_" + s.name,
        }));
      });
    };
	
    ctx.refs.forEach(r => add({
      label: r.name, kind: MK.Reference, insertText: r.insert,
      detail: `🔗 ${r.doctype}`, sortText: "7_" + r.name,
    }));
    fnReg.getSnippets().forEach(s => add({
      label: s.title, kind: MK.Snippet, insertText: s.code,
      insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
      detail: s.desc || "Snippet", sortText: "8_" + s.title,
    }));
    [
      { label: "frappe.session.user",          detail: "User hiện tại" },
      { label: "frappe.session.user_fullname",  detail: "Tên đầy đủ user" },
      { label: "frappe.now_datetime",           detail: "Datetime hiện tại" },
      { label: "frappe.today",                  detail: "Ngày hôm nay" },
    ].forEach(v => add({ label: v.label, kind: MK.Variable, insertText: v.label, detail: v.detail, sortText: "9_" + v.label }));
    if (Array.isArray(ctx._extra)) {
      ctx._extra.forEach(c => add({ kind: MK.Value, sortText: "z_", ...c }));
    }
    return { suggestions: items };
  };
}

// ── Hover provider ──────────────────────────────────────────────────────────
function _registerHoverProvider(monacoEditor, contextFn) {
  if (typeof monaco === "undefined") return { dispose: () => {} };
  const langId = monacoEditor.getModel()?.getLanguageId?.() || "formula-builder";
  const model  = monacoEditor.getModel();
  const disposable = monaco.languages.registerHoverProvider(langId, {
    provideHover(hoverModel, pos) {
      if (hoverModel !== model) return null;
      const word = hoverModel.getWordAtPosition(pos);
      if (!word) return null;
      const fn = formula_builder.formula.FunctionRegistry?.find?.(word.word);
      if (fn) {
        return {
          range: new monaco.Range(pos.lineNumber, word.startColumn, pos.lineNumber, word.endColumn),
          contents: [
            { value: `**${fn.sig}**` },
            { value: `${fn.desc}\n\n_Ví dụ: ${fn.example}_` },
          ],
        };
      }
      const ctx = contextFn ? contextFn() : null;
      if (!ctx) return null;
      const lineText  = hoverModel.getLineContent(pos.lineNumber);
      const colOffset = pos.column - 1;
      const fullTokenMatch = lineText.match(/(\w+\[\d+\]\.\w+)/g);
      let matchedItem = null;
      if (fullTokenMatch) {
        for (const tok of fullTokenMatch) {
          const start = lineText.indexOf(tok);
          const end   = start + tok.length;
          if (colOffset >= start && colOffset <= end) {
            matchedItem = ctx.allItems.find(i => i.insert === tok || i.name === tok);
            break;
          }
        }
      }
      if (!matchedItem) {
        const w = word.word;
        matchedItem = ctx.allItems.find(i => i.name === w || i.insert === w || i.name === "$" + w);
      }
      if (!matchedItem) return null;
      const valStr    = matchedItem.value != null ? String(matchedItem.value) : "null";
      const sourceMap = {
        parent       : "📄 Doctype mẹ",
        current_row  : "📍 Hàng hiện tại",
        current_table: "↔ Bảng hiện tại",
        sibling_table: "↔ Sibling table",
        global       : "🌍 Biến toàn cục",
        local        : "📄 Cục bộ",
        ref          : "🔗 Tham chiếu",
      };
      const sourceLabel = sourceMap[matchedItem.source] || matchedItem.source || "—";
      return {
        range: new monaco.Range(pos.lineNumber, word.startColumn, pos.lineNumber, word.endColumn),
        contents: [
          { value: `**${matchedItem.name}**  _${sourceLabel}_` },
          { value: `| | |\n|---|---|\n| **Giá trị** | \`${valStr}\` |\n| **Kiểu** | \`${matchedItem.fieldtype || "—"}\` |\n| **Doctype** | \`${matchedItem.doctype || "—"}\` |` },
        ],
      };
    },
  });
  return disposable;
}

// ── Preview ─────────────────────────────────────────────────────────────────
async function _runPreview(formula, scopeFn, previewEl, valBar) {
  if (!previewEl) return;
  const valEl = previewEl.querySelector(".afb-fp-preview-val");
  if (!valEl) return;
  if (!formula || !formula.trim()) {
    valEl.textContent = "—";
    valEl.className   = "afb-fp-preview-val";
    if (valBar) valBar.innerHTML = "";
    return;
  }
  valEl.textContent = "⏳ Đang chạy...";
  valEl.className   = "afb-fp-preview-val running";
  try {
    const scope = typeof scopeFn === "function" ? scopeFn() : {};
    const res = await frappe.call({
      method: "formula_builder.api.formula_builder.evaluate_formula",
      args  : { 
        formula, 
        scope_context_json: JSON.stringify(scope),
        frm_doc_json: _getFrmDocJsonForScope(scope),
      },
    });
    const r = res.message;
    if (r?.success) {
      const fmt = typeof r.result === "number"
        ? r.result.toLocaleString("vi-VN")
        : String(r.result ?? "null");
      valEl.textContent = `= ${fmt}`;
      valEl.className   = "afb-fp-preview-val ok";
      if (valBar) valBar.innerHTML = `<span style="color:#10b981">✓ Hợp lệ</span>`;
    } else {
      valEl.textContent = `✗ ${r?.error || "Lỗi"}`;
      valEl.className   = "afb-fp-preview-val error";
      if (valBar) valBar.innerHTML = `<span style="color:#ef4444">✗ ${_esc(r?.error || "Lỗi")}</span>`;
    }
  } catch {
    valEl.textContent = "—";
    valEl.className   = "afb-fp-preview-val";
    if (valBar) valBar.innerHTML = `<span style="color:#ef4444">✗ Lỗi kết nối</span>`;
  }
}

// ── HTML builder ──────────────────────────────────────────────────────────────
function _buildWrapHTML({ fieldname, cdnAttr, language, height, showToolbar, showPreview }) {
  const uid = "fp_" + Math.random().toString(36).substr(2, 8);
  const toolbarHtml = showToolbar ? `
    <div class="afb-fp-toolbar">
      <span class="afb-fp-lang-badge">${language}</span>
      <div style="flex:1"></div>
      <button class="afb-btn  fp-copy" title="Copy">📋</button>
    </div>` : "";
  const previewHtml = showPreview ? `
    <div class="afb-fp-preview">
      <span class="afb-fp-preview-icon">▶</span>
      <span class="afb-fp-preview-val">—</span>
      <button class="afb-fp-btn run-btn"    title="Chạy thử công thức">Chạy</button>
      <button class="afb-fp-btn dialog-btn" title="Mở Formula Builder đầy đủ">⬡ Editor</button>
    </div>` : "";
  return {
    uid,
    html: `<div class="afb-fp-wrap" data-field="${fieldname}"${cdnAttr}>
      ${toolbarHtml}
      <div class="afb-fp-monaco" id="fpm-${uid}" style="height:${height};"></div>
      ${previewHtml}
    </div>`,
  };
}

// ── Factory: tạo Monaco editor inline ─────────────────────────────────────────
function _createInlineMonaco({ container, initialValue, cfg, contextFn, onChangeFn, scopeFn, previewEl, openDialogFn }) {
  let monacoEditor  = null;
  let _resizeObs    = null;
  let _previewTimer = null;
  const disposables = [];
  if (!monaco.languages.getLanguages().some(l => l.id === cfg.language)) {
    monaco.languages.register({ id: cfg.language });
  }
  let valBar = null;
  if (previewEl) {
    valBar = document.createElement("div");
    valBar.className = "afb-fp-valbar";
    valBar.style.cssText = "font-size:10px;padding:2px 6px;color:#64748b;background:#f8fafc;border-top:1px solid #e2e8f0;border-bottom-left-radius:4px;border-bottom-right-radius:4px;";
    previewEl.parentNode.insertBefore(valBar, previewEl.nextSibling);
  }

  // Grid context: .form-in-grid has transform which traps position:fixed.
  // Solution: use fixedOverflowWidgets:false so suggest stays inside editor
  // using position:absolute (not affected by transform).
  // Everything else identical to parent field.
  var inGrid = !!(container.closest('.grid-body') || container.closest('.form-in-grid'));

  monacoEditor = monaco.editor.create(container, {
    value               : initialValue || "",
    language            : cfg.language,
    theme               : window._afbLightTheme ? "formula-builder-light" : "vs",
    automaticLayout     : false,
    fontSize            : 13,
    fontFamily          : "'JetBrains Mono','Fira Code','Cascadia Code',monospace",
    minimap             : { enabled: false },
    scrollBeyondLastLine: false,
    lineNumbers         : cfg.line_numbers ? "on" : "off",
    glyphMargin         : false,
    folding             : !!cfg.line_numbers,
    wordWrap            : cfg.word_wrap ? "on" : "off",
    suggestOnTriggerCharacters: true,
    quickSuggestions    : { other: true, strings: true, comments: false },
    parameterHints      : { enabled: true },
    suggest             : { preview: true, showStatusBar: false, insertMode: "replace", showIcons: true, showFields: true, showVariables: true, showSnippets: true },
    suggestFontSize     : 13,
    suggestLineHeight   : 24,
    fixedOverflowWidgets: inGrid ? false : true,
    padding             : { top: 6, bottom: 16 },
    scrollbar           : { vertical: "auto", horizontal: "hidden", useShadows: false },
    overviewRulerLanes  : 0,
    renderLineHighlight : "none",
  });

  // BUG FIX: đảm bảo view-lines không bị padding-bottom 52px từ .afb-monaco rule
  requestAnimationFrame(() => {
    const vl = container.querySelector(".monaco-editor .view-lines");
    if (vl) vl.style.setProperty("padding-bottom", "4px", "important");
  });

  const model = monacoEditor.getModel();
  formula_builder.formula.CompletionRegistry.ensureLanguage(cfg.language);
  formula_builder.formula.CompletionRegistry.register(model, _buildCompletionHandler(monacoEditor, contextFn), cfg.language);
  const hoverDisposable = _registerHoverProvider(monacoEditor, contextFn);
  disposables.push(hoverDisposable);
  if (typeof ResizeObserver !== "undefined") {
    _resizeObs = new ResizeObserver(() => monacoEditor?.layout());
    _resizeObs.observe(container);
  }
  disposables.push(monacoEditor.onDidChangeModelContent(() => {
    const val = monacoEditor.getValue();
    if (typeof onChangeFn === "function") onChangeFn(val);
    if (previewEl && scopeFn) {
      clearTimeout(_previewTimer);
      _previewTimer = setTimeout(() => _runPreview(val, scopeFn, previewEl, valBar), 400);
    }
  }));
  if (previewEl) {
    previewEl.querySelector(".run-btn")?.addEventListener("click", () => {
      _runPreview(monacoEditor.getValue(), scopeFn, previewEl, valBar);
    });
    previewEl.querySelector(".dialog-btn")?.addEventListener("click", () => {
      if (typeof openDialogFn === "function") openDialogFn(monacoEditor.getValue());
    });
  }
  return {
    getEditor : () => monacoEditor,
    getValue  : () => monacoEditor?.getValue() || "",
    setValue  : (v) => {
      if (!monacoEditor) return;
      const state = monacoEditor.saveViewState();
      monacoEditor.setValue(v || "");
      if (state) monacoEditor.restoreViewState(state);
      if (previewEl && scopeFn) {
        clearTimeout(_previewTimer);
        _previewTimer = setTimeout(() => _runPreview(v || "", scopeFn, previewEl, valBar), 200);
      }
    },
    dispose: () => {
      clearTimeout(_previewTimer);
      _resizeObs?.disconnect();
      disposables.forEach(d => d.dispose?.());
      if (model) formula_builder.formula.CompletionRegistry.unregister(model);
      monacoEditor?.dispose();
    },
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// _buildPatchConfig  –  helper dùng chung cho patchField & patchChildField
// Ưu tiên: opts > setting (window._afbFieldConfig) > hằng số mặc định
// ═══════════════════════════════════════════════════════════════════════════════
function _buildPatchConfig(fieldMeta, opts) {
  return Object.assign({
    language         : _resolveLanguage(fieldMeta, null),
    height           : fieldMeta ? _defaultHeight(fieldMeta.fieldtype) : "100px",
    show_toolbar     : false,
    show_preview     : true,
    word_wrap        : true,
    line_numbers     : false,
    extra_completions: [],
    on_change        : null,
  }, opts);
}

// ─── Shared Monaco-init helper used by patchField & patchChildField ──────────
// Handles: loadMonaco → _createInlineMonaco, copy toolbar, fallback textarea
// Returns nothing; mutates the passed `api` object in-place.
function _patchFieldCommon({ uid, cfg, initialValueFn, $wrap, $inputArea, previewEl, contextFn, scopeFn, onChangeFn, openDialogFn, api }) {
  loadMonaco().then(() => {
    if (typeof monaco === "undefined") throw new Error("Monaco not loaded");
    const container = document.getElementById(`fpm-${uid}`);
    if (!container) return;

    // ── Fix Frappe grid containing-block (contain: paint/content) ─────────
    const restoreGridContain = _fixGridContainBlock(container);

    const inst = _createInlineMonaco({
      container,
      initialValue: initialValueFn(),
      cfg,
      contextFn,
      onChangeFn,
      scopeFn,
      previewEl,
      openDialogFn,
    });
    if (cfg.show_toolbar) {
      $wrap.find(".fp-copy").on("click", () => {
        navigator.clipboard?.writeText(inst.getValue()).catch(() => {});
        frappe.show_alert({ message: "📋 Đã copy", indicator: "green" }, 1);
      });
    }
    api.getEditor = inst.getEditor;
    api.getValue  = inst.getValue;
    api.setValue  = inst.setValue;
    const origDispose = inst.dispose;
    api._dispose = () => { restoreGridContain(); origDispose(); };
  }).catch(err => {
    console.error("[FormulaBuilder] Monaco load failed, using fallback textarea:", err);
    const container = document.getElementById(`fpm-${uid}`);
    if (!container) return;
    const textarea = document.createElement("textarea");
    textarea.style.cssText = `width:100%;height:${cfg.height};font-family:monospace;padding:8px;border:1px solid #cbd5e1;border-radius:4px;background:#fff;`;
    textarea.value = initialValueFn();
    container.appendChild(textarea);
    textarea.addEventListener("input", () => onChangeFn(textarea.value));
    api.getEditor = () => null;
    api.getValue  = () => textarea.value;
    api.setValue  = (v) => { textarea.value = v || ""; };
    api._dispose  = () => { textarea.remove(); };
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// patchField  –  inject Monaco vào field của doctype mẹ (giữ nguyên)
// ═══════════════════════════════════════════════════════════════════════════════
formula_builder.formula.patchField = function(frm, fieldname, opts = {}) {
  const key = _editorKey(frm, fieldname);
  if (_patchedEditors[key]) return _patchedEditors[key];
  const field = frm.fields_dict[fieldname];
  if (!field) {
    console.warn(`[FormulaBuilder] patchField: field "${fieldname}" không tồn tại trong ${frm.doctype}`);
    return null;
  }
  const $fw = $(field.$wrapper || field.wrapper);
  if (!$fw.length) return null;
  $fw.find(".afb-fp-wrap, .afb-field-patch-wrap").remove();
  const cfg = _buildPatchConfig(field.df, opts);
  _ensureFieldPatchCSS();
  const { uid, html } = _buildWrapHTML({
    fieldname,
    cdnAttr    : "",
    language   : cfg.language,
    height     : cfg.height,
    showToolbar: cfg.show_toolbar,
    showPreview: cfg.show_preview,
  });
  const $wrap      = $(html);
  const $inputArea = $fw.find("input, textarea").first();
  if ($inputArea.length) { $inputArea.hide(); $inputArea.after($wrap); }
  else { $fw.append($wrap); }
  const previewEl  = cfg.show_preview ? $wrap.find(".afb-fp-preview")[0] || null : null;
  const scopeFn    = () => ({
    current_doctype  : frm.doctype,
    current_docname  : frm.docname || null,
    current_field    : fieldname,
    child_table_field: null,
    row_index        : null,
  });
  const contextFn  = () => {
    const ctx = _buildContext({ frm, childTableField: null, cdn: null });
    if (cfg.extra_completions?.length) ctx._extra = cfg.extra_completions;
    return ctx;
  };
  const openDialogFn = (currentVal) => {
    formula_builder.formula.openDialog({
      value            : currentVal,
      current_doctype  : frm.doctype,
      current_docname  : frm.docname,
      current_field    : fieldname,
      field_label      : field.df?.label || fieldname,
      onSave: (val) => {
        api.setValue(val || "");
        frm.set_value(fieldname, val);
      },
    });
  };
  const api = {
    getEditor  : () => null,
    getValue   : () => "",
    setValue   : () => {},
    openDialog : () => openDialogFn(""),
    dispose    : () => {
      if (api._dispose) api._dispose();
      $wrap.remove();
      $inputArea.show();
      delete _patchedEditors[key];
    },
  };
  _patchedEditors[key] = api;
  _patchFieldCommon({
    uid, cfg,
    initialValueFn : () => _getFieldValue(frm, fieldname),
    $wrap, $inputArea, previewEl, contextFn, scopeFn,
    onChangeFn: (val) => {
      frm.set_value(fieldname, val);
      if (typeof cfg.on_change === "function") cfg.on_change(val);
    },
    openDialogFn,
    api,
  });
  return api;
};

// ═══════════════════════════════════════════════════════════════════════════════
// patchChildField  –  inject Monaco vào field của child table row (FIXED)
// ═══════════════════════════════════════════════════════════════════════════════
formula_builder.formula.patchChildField = function(frm, childTableField, cdn, fieldname, opts = {}) {
  const key = opts._keyOverride || `${frm.doctype}::${childTableField}::${cdn}::${fieldname}`;

  if (_patchedEditors[key] && !opts.forceNew) return _patchedEditors[key];
  if (_patchedEditors[key] && opts.forceNew) {
    try { _patchedEditors[key].dispose(); } catch {}
    delete _patchedEditors[key];
  }

  let $fw;
  if (opts.wrapper) {
    $fw = $(opts.wrapper);
    if (!$fw.length) { console.warn(`[FormulaBuilder] patchChildField: provided wrapper not found`); return null; }
  } else {
    const grid = frm.fields_dict[childTableField]?.grid;
    if (!grid) { console.warn(`[FormulaBuilder] patchChildField: grid "${childTableField}" không tìm thấy`); return null; }
    const gridRow = grid.get_row?.(cdn);
    if (!gridRow) { console.warn(`[FormulaBuilder] patchChildField: row "${cdn}" không tìm thấy`); return null; }
    const field = opts.expanded ? gridRow.get_field?.(fieldname, true) : gridRow.get_field?.(fieldname);
    if (!field) { console.warn(`[FormulaBuilder] patchChildField: field "${fieldname}" không tìm thấy`); return null; }
    $fw = $(field.wrapper || field.$wrapper);
  }
  if (!$fw.length) return null;

  $fw.find(".afb-fp-wrap, .afb-field-patch-wrap").remove();

  const parentMeta   = frappe.get_meta?.(frm.doctype);
  const childMeta_   = parentMeta?.fields?.find(f => f.fieldname === childTableField);
  const childDoctype = childMeta_?.options;
  const fieldMeta    = childDoctype ? frappe.get_meta?.(childDoctype)?.fields?.find(f => f.fieldname === fieldname) : null;
  const cfgDefaults  = fieldMeta ? {} : { language: opts.language || "formula-builder" };
  const cfg          = _buildPatchConfig(fieldMeta, Object.assign(cfgDefaults, opts));

  _ensureFieldPatchCSS();

  const { uid, html } = _buildWrapHTML({
    fieldname,
    cdnAttr    : ` data-cdn="${cdn}"`,
    language   : cfg.language,
    height     : cfg.height,
    showToolbar: cfg.show_toolbar,
    showPreview: cfg.show_preview,
  });

  const $wrap      = $(html);
  const $inputArea = $fw.find("input, textarea").first();
  if ($inputArea.length) { $inputArea.hide(); $inputArea.after($wrap); }
  else { $fw.append($wrap); }

  const previewEl    = cfg.show_preview ? $wrap.find(".afb-fp-preview")[0] || null : null;
  const currentValue = () => {
    const row = (frm.doc?.[childTableField] || []).find(r => r.name === cdn);
    return row ? (row[fieldname] || "") : "";
  };
  const scopeFn = () => {
    const rows   = frm.doc?.[childTableField] || [];
    const rowIdx = rows.findIndex(r => r.name === cdn);
    return {
      current_doctype  : frm.doctype,
      current_docname  : frm.docname || null,
      current_field    : fieldname,
      child_table_field: childTableField,
      row_index        : rowIdx >= 0 ? rowIdx : 0,
    };
  };
  const contextFn = () => {
    const ctx = _buildContext({ frm, childTableField, cdn });
    if (cfg.extra_completions?.length) ctx._extra = cfg.extra_completions;
    return ctx;
  };
  const openDialogFn = (currentVal) => {
    const rows   = frm.doc?.[childTableField] || [];
    const rowIdx = rows.findIndex(r => r.name === cdn);
    formula_builder.formula.openDialog({
      value            : currentVal,
      current_doctype  : frm.doctype,
      current_docname  : frm.docname,
      child_table_field: childTableField,
      row_index        : rowIdx >= 0 ? rowIdx : 0,
      current_field    : fieldname,
      field_label      : fieldMeta?.label || fieldname,
      onSave: (val) => {
        api.setValue(val || "");
        frappe.model.set_value(childDoctype, cdn, fieldname, val);
      },
    });
  };
  const api = {
    getEditor  : () => null,
    getValue   : () => "",
    setValue   : () => {},
    openDialog : () => openDialogFn(""),
    dispose    : () => {
      if (api._dispose) api._dispose();
      $wrap.remove();
      $inputArea.show();
      delete _patchedEditors[key];
    },
  };
  _patchedEditors[key] = api;
  _patchFieldCommon({
    uid, cfg,
    initialValueFn : currentValue,
    $wrap, $inputArea, previewEl, contextFn, scopeFn,
    onChangeFn: (val) => {
      frappe.model.set_value(childDoctype, cdn, fieldname, val);
      if (typeof cfg.on_change === "function") cfg.on_change(val);
    },
    openDialogFn,
    api,
  });
  return api;
};

// ═══════════════════════════════════════════════════════════════════════════════
// Các hàm khác (patchFormFields, enableGlobalPatch, dispose helpers, sync) giữ nguyên
// ═══════════════════════════════════════════════════════════════════════════════
formula_builder.formula.patchFormFields = function(frm, globalOpts = {}, fieldOpts = {}) {
  if (!frm?.fields_dict) return;
  const { skip_fieldtypes, language_map } = _cfg();
  Object.entries(frm.fields_dict).forEach(([fieldname, field]) => {
    const ft = field.df?.fieldtype;
    if (!ft || skip_fieldtypes.has(ft)) return;
    if (!(ft in language_map) && !fieldOpts[fieldname]) return;
    formula_builder.formula.patchField(frm, fieldname, Object.assign({}, globalOpts, fieldOpts[fieldname] || {}));
  });
};

let _globalPatchEnabled  = false;
let _originalFormRefresh = null;
formula_builder.formula.enableGlobalPatch = function(defaultOpts = {}, filterFn = null) {
  if (_globalPatchEnabled) return;
  _globalPatchEnabled = true;
  const proto = frappe.ui?.form?.Form?.prototype;
  if (!proto) { console.warn("[FormulaBuilder] enableGlobalPatch: frappe.ui.form.Form chưa sẵn sàng."); return; }
  _originalFormRefresh = proto.refresh;
  proto.refresh = function(...args) {
    const result = _originalFormRefresh.apply(this, args);
    setTimeout(() => {
      if (!this?.fields_dict) return;
      const { skip_fieldtypes, language_map } = _cfg();
      Object.entries(this.fields_dict).forEach(([fieldname, field]) => {
        const ft = field.df?.fieldtype;
        if (!ft || skip_fieldtypes.has(ft) || !(ft in language_map)) return;
        if (typeof filterFn === "function" && !filterFn(this, fieldname, ft)) return;
        const key = _editorKey(this, fieldname);
        if (_patchedEditors[key]) return;
        formula_builder.formula.patchField(this, fieldname, defaultOpts);
      });
    }, 0);
    return result;
  };
  console.info("[FormulaBuilder] Global field patch đã được kích hoạt.");
};
formula_builder.formula.disableGlobalPatch = function() {
  if (!_globalPatchEnabled || !_originalFormRefresh) return;
  const proto = frappe.ui?.form?.Form?.prototype;
  if (proto) proto.refresh = _originalFormRefresh;
  _globalPatchEnabled  = false;
  _originalFormRefresh = null;
  console.info("[FormulaBuilder] Global field patch đã tắt.");
};
formula_builder.formula.disposePatchedField = function(frm, fieldname) {
  _patchedEditors[_editorKey(frm, fieldname)]?.dispose();
};
formula_builder.formula.disposeFormPatches = function(frm) {
  const prefix = `${frm.doctype}::`;
  Object.keys(_patchedEditors).forEach(key => {
    if (key.startsWith(prefix)) _patchedEditors[key].dispose();
  });
};
formula_builder.formula.disposeChildPatch = function(frm, childTableField, cdn, fieldname) {
  _patchedEditors[`${frm.doctype}::${childTableField}::${cdn}::${fieldname}`]?.dispose();
};
formula_builder.formula.syncChildFieldValue = function(frm, childTableField, cdn, fieldname) {
  const key = `${frm.doctype}::${childTableField}::${cdn}::${fieldname}`;
  const api = _patchedEditors[key];
  if (!api) return;
  const row = (frm.doc?.[childTableField] || []).find(r => r.name === cdn);
  if (row) api.setValue(row[fieldname] || "");
};


// ═══════════════════════════════════════════════════════════════════════════════
// initGridField  –  tích hợp Monaco inline + dblclick dialog cho cột child table
//
// Sử dụng:
//   formula_builder.formula.initGridField(frm, "items", "custom_item_formula", {
//       language    : "formula-builder",
//       height      : "80px",
//       show_toolbar: false,
//   });
//
// Tự động xử lý:
//   • 1 click  → mở Monaco inline trong cell, focus ngay lập tức
//   • dblclick → mở full dialog (giống trường bảng mẹ)
//   • Đóng cell (click ngoài / Esc) → lưu + restore static text
//   • form_render (expanded row) → Monaco đầy đủ trong form con
//   • Sau khi đóng expanded row → inline cell hoạt động lại bình thường
// ═══════════════════════════════════════════════════════════════════════════════
formula_builder.formula.initGridField = function(frm, gridField, fieldname, opts = {}) {
    const cfg = Object.assign({
        language    : "formula-builder",
        height      : "80px",
        show_toolbar: false,
        show_preview: false,
        float_popup : false,   // ← mới: bật để cell nổi lên to hơn khi click
        float_width : "480px", // ← chiều rộng popup nổi
        float_height: "160px", // ← chiều cao popup nổi
    }, opts);

    const childDoctype = (() => {
        const meta = frappe.get_meta(frm.doctype);
        return meta?.fields?.find(f => f.fieldname === gridField)?.options || null;
    })();

    // ── Helpers ──────────────────────────────────────────────────────────────

    function _key(cdn) {
        return `${frm.doctype}::${gridField}::${cdn}::${fieldname}`;
    }

    function _currentVal(cdn) {
        const row = (frm.doc?.[gridField] || []).find(r => r.name === cdn);
        return row?.[fieldname] || "";
    }

    function _saveVal(cdn, val) {
        if (childDoctype) frappe.model.set_value(childDoctype, cdn, fieldname, val);
    }

    function _openFullDialog(cdn) {
        const rows   = frm.doc?.[gridField] || [];
        const rowIdx = rows.findIndex(r => r.name === cdn);
        const fieldMeta = childDoctype
            ? frappe.get_meta(childDoctype)?.fields?.find(f => f.fieldname === fieldname)
            : null;
        formula_builder.formula.openDialog({
            value            : _currentVal(cdn),
            current_doctype  : frm.doctype,
            current_docname  : frm.docname,
            child_table_field: gridField,
            row_index        : rowIdx >= 0 ? rowIdx : 0,
            current_field    : fieldname,
            field_label      : fieldMeta?.label || fieldname,
            onSave(val) {
                _saveVal(cdn, val);
                // Cập nhật static text nếu cell đang hiển thị
                const grid  = frm.fields_dict?.[gridField]?.grid;
                const gw    = grid?.wrapper?.[0] || grid?.$wrapper?.[0];
                const rowEl = gw?.querySelector?.(`.grid-row[data-name="${cdn}"]`);
                if (rowEl) {
                    const st = rowEl.querySelector(`.grid-static-col[data-fieldname="${fieldname}"] .afb-grid-cell-static`);
                    if (st) st.textContent = val || "";
                }
            },
        });
    }

    // ── Mở Monaco inline trong cell (1 click) ─────────────────────────────────
    // Trả về Promise, resolve khi Monaco đã focus (dùng cho onReady)
    function _openInlineEditor(cell, cdn) {
      const key = _key(cdn);

      // Nếu editor đang sống trong cell này → chỉ focus
      const existing = window._afbPatchedEditors?.[key];
      if (existing && cell.querySelector(".monaco-editor")) {
          try { existing.getEditor?.()?.focus(); } catch {}
          return;
      }

      // Dispose editor cũ (ví dụ orphan sau expanded row)
      if (existing) {
          try { existing.dispose(); } catch {}
          delete window._afbPatchedEditors[key];
      }

      // Lấy hoặc tạo container trong cell
      let editorContainer = cell.querySelector(".afb-grid-cell-editor");
      const staticEl      = cell.querySelector(".afb-grid-cell-static");

      if (!editorContainer) {
          editorContainer = document.createElement("div");
          editorContainer.className = "afb-grid-cell-editor";
          editorContainer.style.height = cfg.height;
          cell.appendChild(editorContainer);
      }
      editorContainer.style.display = "";
      if (staticEl) staticEl.style.display = "none";

      // Context / scope
      const contextFn = () => {
          const ctx = _buildContext({ frm, childTableField: gridField, cdn });
          return ctx;
      };
      const scopeFn = () => {
          const rows   = frm.doc?.[gridField] || [];
          const rowIdx = rows.findIndex(r => r.name === cdn);
          return {
              current_doctype  : frm.doctype,
              current_docname  : frm.docname || null,
              current_field    : fieldname,
              child_table_field: gridField,
              row_index        : rowIdx >= 0 ? rowIdx : 0,
          };
      };

      // Đăng ký Monaco
      const editorCfg = Object.assign({}, cfg, { show_preview: false });

      loadMonaco().then(() => {
          if (typeof monaco === "undefined") return;
          // Kiểm tra lại — có thể cell đã đóng trước khi Monaco load
          if (!document.body.contains(editorContainer)) return;

          const restoreGridContain = _fixGridContainBlock(editorContainer);

          const inst = _createInlineMonaco({
              container   : editorContainer,
              initialValue: _currentVal(cdn),
              cfg         : editorCfg,
              contextFn,
              scopeFn,
              previewEl   : null,
              onChangeFn  : (val) => _saveVal(cdn, val),
              openDialogFn: () => _openFullDialog(cdn),
          });

          // Lưu vào registry với API đầy đủ
          const api = window._afbPatchedEditors?.[key] || {};
          api.getEditor = inst.getEditor;
          api.getValue  = inst.getValue;
          api.setValue  = inst.setValue;
          api._dispose  = inst.dispose;
          api.dispose   = () => {
              restoreGridContain();
              inst.dispose();
              editorContainer.style.display = "none";
              if (staticEl) {
                  staticEl.textContent  = _currentVal(cdn);
                  staticEl.style.display = "";
              }
              delete window._afbPatchedEditors[key];
          };
          window._afbPatchedEditors[key] = api;

          // [FIX 1-CLICK] Focus ngay sau khi Monaco mount xong
          requestAnimationFrame(() => {
              try {
                  const ed = inst.getEditor();
                  if (!ed) return;
                  ed.focus();
                  // Đặt con trỏ về cuối văn bản
                  const model = ed.getModel();
                  if (model) {
                      const lastLine = model.getLineCount();
                      const lastCol  = model.getLineMaxColumn(lastLine);
                      ed.setPosition({ lineNumber: lastLine, column: lastCol });
                      ed.revealPosition({ lineNumber: lastLine, column: lastCol });
                  }
              } catch {}
          });
      });

      // Ghi placeholder vào registry ngay lập tức (trước khi Monaco load xong)
      // để click handler không gọi lại lần 2 trong khi đang load
      if (!window._afbPatchedEditors[key]) {
          window._afbPatchedEditors[key] = {
              getEditor: () => null, getValue: () => _currentVal(cdn),
              setValue: () => {}, openDialog: () => _openFullDialog(cdn),
              _loading: true,
              dispose: () => {
                  editorContainer.style.display = "none";
                  if (staticEl) { staticEl.textContent = _currentVal(cdn); staticEl.style.display = ""; }
                  delete window._afbPatchedEditors[key];
              },
          };
      }

      // Click ngoài / Esc → đóng editor
      const _close = (ev) => {
          if (ev && ev.type === "mousedown") {
              if (ev.target.closest(".suggest-widget, .overflowingContentWidgets, .monaco-list, .afb-fp-wrap")) return;
              if (cell.contains(ev.target)) return;
          }
          document.removeEventListener("mousedown", _close, true);
          document.removeEventListener("keydown",   _escHandler, true);

          const curApi = window._afbPatchedEditors?.[key];
          const val    = curApi?.getValue?.() ?? _currentVal(cdn);
          _saveVal(cdn, val);
          curApi?.dispose?.();
      };
      const _escHandler = (ev) => { if (ev.key === "Escape") _close(); };
      setTimeout(() => {
          document.addEventListener("mousedown", _close, true);
          document.addEventListener("keydown",   _escHandler, true);
      }, 200);
    }


    // ── Float popup (tùy chọn float_popup: true) ──────────────────────────────
    function _openFloatPopup(cell, cdn) {
      const key = _key(cdn);

      // Đóng popup cũ nếu có
      document.querySelectorAll(".afb-grid-float-popup").forEach(el => el.remove());
      const existing = window._afbPatchedEditors?.[key];
      if (existing) { try { existing.dispose(); } catch {} delete window._afbPatchedEditors[key]; }

      // Tính vị trí: hiển thị phía trên cell, căn trái theo cell
      const cellRect = cell.getBoundingClientRect();
      const popupW   = parseInt(cfg.float_width)  || 480;
      const popupH   = parseInt(cfg.float_height) || 160;
      let   left     = cellRect.left + window.scrollX;
      let   top      = cellRect.top  + window.scrollY - popupH - 10;

      // Nếu bị cắt trên → hiển thị phía dưới
      if (top < window.scrollY + 8) top = cellRect.bottom + window.scrollY + 6;
      // Nếu bị cắt phải → dịch trái
      if (left + popupW > window.innerWidth - 8) left = window.innerWidth - popupW - 8 + window.scrollX;

      const popup = document.createElement("div");
      popup.className = "afb-grid-float-popup";
      popup.style.cssText = `left:${left}px;top:${top}px;width:${popupW}px;height:${popupH}px;`;

      const editorDiv = document.createElement("div");
      editorDiv.style.cssText = "width:100%;height:100%;";
      popup.appendChild(editorDiv);
      document.body.appendChild(popup);

      // Context / scope (giống inline)
      const contextFn = () => _buildContext({ frm, childTableField: gridField, cdn });
      const scopeFn   = () => {
          const rows   = frm.doc?.[gridField] || [];
          const rowIdx = rows.findIndex(r => r.name === cdn);
          return {
              current_doctype  : frm.doctype,
              current_docname  : frm.docname || null,
              current_field    : fieldname,
              child_table_field: gridField,
              row_index        : rowIdx >= 0 ? rowIdx : 0,
          };
      };
      const editorCfg = Object.assign({}, cfg, { show_preview: false, height: "100%" });

      loadMonaco().then(() => {
          if (typeof monaco === "undefined" || !document.body.contains(popup)) return;
          const inst = _createInlineMonaco({
              container   : editorDiv,
              initialValue: _currentVal(cdn),
              cfg         : editorCfg,
              contextFn,
              onChangeFn  : (val) => _saveVal(cdn, val),
              openDialogFn: () => { _closePopup(); _openFullDialog(cdn); },
              scopeFn,
              previewEl   : null,
          });

          // Đăng ký vào registry
          const api = {
              getEditor: inst.getEditor, getValue: inst.getValue,
              setValue : inst.setValue,  _dispose : inst.dispose,
              dispose  : () => { inst.dispose(); popup.remove(); delete window._afbPatchedEditors[key]; },
          };
          window._afbPatchedEditors[key] = api;

          // Con trỏ về cuối
          requestAnimationFrame(() => {
              try {
                  const ed    = inst.getEditor();
                  if (!ed) return;
                  ed.focus();
                  const model = ed.getModel();
                  if (model) {
                      const lastLine = model.getLineCount();
                      const lastCol  = model.getLineMaxColumn(lastLine);
                      ed.setPosition({ lineNumber: lastLine, column: lastCol });
                  }
              } catch {}
          });
      });

      // Đóng khi click ngoài / Esc
      const _closePopup = () => {
          document.removeEventListener("mousedown", _outsideHandler, true);
          document.removeEventListener("keydown",   _escHandler,     true);
          const curApi = window._afbPatchedEditors?.[key];
          const val    = curApi?.getValue?.() ?? _currentVal(cdn);
          _saveVal(cdn, val);
          // Cập nhật static text
          const st = cell.querySelector(".afb-grid-cell-static");
          if (st) st.textContent = val || "";
          curApi?.dispose?.();
      };
      const _outsideHandler = (ev) => {
          if (popup.contains(ev.target)) return;
          if (ev.target.closest(".suggest-widget, .overflowingContentWidgets, .monaco-list")) return;
          _closePopup();
      };
      const _escHandler = (ev) => { if (ev.key === "Escape") _closePopup(); };

      setTimeout(() => {
          document.addEventListener("mousedown", _outsideHandler, true);
          document.addEventListener("keydown",   _escHandler,     true);
      }, 200);
    }

    // ── Khởi tạo static cell DOM ──────────────────────────────────────────────
    // Đảm bảo mỗi cell có .afb-grid-cell-static để hiển thị giá trị
    function _ensureCellDOM(cell, cdn) {
        if (cell.querySelector(".afb-grid-cell-static")) return;
        // Ẩn nội dung gốc của Frappe trong static col
        const existingContent = cell.querySelector(".field-area, .static-area");
        if (existingContent) existingContent.style.display = "none";

        const staticEl = document.createElement("div");
        staticEl.className   = "afb-grid-cell-static";
        staticEl.textContent = _currentVal(cdn);
        cell.appendChild(staticEl);
    }

    // ── Bind event cho expanded row (form_render) ─────────────────────────────
    function _bindExpandedRow(cdn, rowEl) {
        // Dispose inline editor nếu đang mở
        const key = _key(cdn);
        if (window._afbPatchedEditors?.[key]) {
            try { window._afbPatchedEditors[key].dispose(); } catch {}
            delete window._afbPatchedEditors[key];
        }

        const expandedWrapper = rowEl.querySelector(
            `.form-layout [data-fieldname="${fieldname}"] .control-input`
        ) || rowEl.querySelector(
            `[data-fieldname="${fieldname}"] .control-input`
        );
        if (!expandedWrapper) return;

        formula_builder.formula.patchChildField(frm, gridField, cdn, fieldname, {
            language    : cfg.language,
            height      : cfg.height,
            show_toolbar: cfg.show_toolbar,
            show_preview: true,   // expanded row dùng preview như field bảng mẹ
            forceNew    : true,
            expanded    : true,
            wrapper     : expandedWrapper,
        });

        // overflow:visible cho grid container được xử lý động bởi
        // _fixGridContainBlock (focus → visible, blur → restore scrollbar)

        // MutationObserver: khi row đóng → dispose editor + xóa key
        // QUAN TRỌNG: phải gọi api.dispose() để _fixGridContainBlock restore
        // overflow về giá trị gốc → giữ scrollbar dọc của bảng con.
        if (!rowEl._afbCloseObserver) {
            rowEl._afbCloseObserver = new MutationObserver(() => {
                if (!rowEl.classList.contains("grid-row-open")) {
                    rowEl._afbCloseObserver.disconnect();
                    rowEl._afbCloseObserver = null;
                    // Gọi dispose để restoreGridContain() chạy, trả lại
                    // overflow:auto cho .form-in-grid và các ancestors.
                    const api = window._afbPatchedEditors?.[key];
                    if (api) {
                        try { api.dispose(); } catch (e) { console.warn("[FormulaBuilder] dispose failed:", e); }
                    }
                    delete window._afbPatchedEditors?.[key];
                }
            });
            rowEl._afbCloseObserver.observe(rowEl, { attributes: true, attributeFilter: ["class"] });
        }
    }

    // ── Gắn click handler lên grid wrapper ───────────────────────────────────
    const grid = frm.fields_dict?.[gridField]?.grid;
    if (!grid) return;
    const gw = grid.wrapper?.[0] || grid.$wrapper?.[0];
    if (!gw) return;

    // Ensure CSS
    _ensureFieldPatchCSS();

    // Rebind (xóa handler cũ nếu có)
    // [FIX] Dùng key riêng theo fieldname để mỗi cột có handler độc lập.
    // Trước đây dùng gw._afbGridFieldHandler (chung), nên lần gọi initGridField
    // thứ 2 xóa luôn handler của lần 1 → cột đầu tiên mất click.
    const _hKey    = `_afbGridFieldHandler_${fieldname}`;
    const _hDblKey = `_afbGridFieldDblHandler_${fieldname}`;

    if (gw[_hKey]) {
        gw.removeEventListener("click",    gw[_hKey], true);
        gw.removeEventListener("dblclick", gw[_hDblKey], true);
    }

    // Dùng capture=true để chạy trước Frappe xử lý click
    gw[_hKey] = function(e) {
        const cell = e.target.closest(`.grid-static-col[data-fieldname="${fieldname}"]`);
        if (!cell) return;
        const rowEl = cell.closest(".grid-row");
        if (!rowEl) return;
        const cdn = rowEl.getAttribute("data-name");
        if (!cdn) return;
        if (rowEl.classList.contains("grid-row-open")) return;

        // Khởi tạo DOM tĩnh nếu chưa có
        _ensureCellDOM(cell, cdn);

        // Mở editor inline (1 click)
        if (cfg.float_popup) _openFloatPopup(cell, cdn);
        else                 _openInlineEditor(cell, cdn);
    };

    gw[_hDblKey] = function(e) {
        const cell = e.target.closest(`.grid-static-col[data-fieldname="${fieldname}"]`);
        if (!cell) return;
        const rowEl = cell.closest(".grid-row");
        if (!rowEl) return;
        const cdn = rowEl.getAttribute("data-name");
        if (!cdn) return;
        if (rowEl.classList.contains("grid-row-open")) return;

        // Đóng inline editor nếu đang mở trước khi mở dialog
        const key = _key(cdn);
        const api = window._afbPatchedEditors?.[key];
        if (api && !api._loading) {
            try { api.dispose(); } catch {}
        }

        // Mở full dialog
        e.stopImmediatePropagation();
        _openFullDialog(cdn);
    };

    gw.addEventListener("click",    gw[_hKey],    true);
    gw.addEventListener("dblclick", gw[_hDblKey], true);

    // ── Đăng ký form_render tự động ──────────────────────────────────────────
    // Đảm bảo không đăng ký trùng (dùng flag trên frm)
    const _renderKey = `_afbGridRender_${gridField}_${fieldname}`;
    if (!frm[_renderKey]) {
        frm[_renderKey] = true;
        frappe.ui.form.on(frm.doctype.replace(/ /g, "_") || frm.doctype, {});  // ensure event bus
        // Dùng hook trực tiếp vào Frappe event system của child doctype
        const frappeChildDt = childDoctype || (gridField + " Item");
        frappe.ui.form.on(frappeChildDt, {
            form_render(innerFrm, cdt, cdn) {
                if (innerFrm.docname !== frm.docname) return;
                setTimeout(() => {
                    const innerGrid  = innerFrm.fields_dict?.[gridField]?.grid;
                    const frappeRow  = innerGrid?.get_row?.(cdn);
                    if (!frappeRow) return;
                    const rowEl = frappeRow.wrapper?.[0] || frappeRow.$wrapper?.[0];
                    if (!rowEl?.classList.contains("grid-row-open")) return;
                    _bindExpandedRow(cdn, rowEl);
                }, 300);
            },
        });
    }
};


console.info("[Formula Builder Field Patch v2.4] Loaded — _patchFieldCommon dedup, _serializeDoc shared, _buildCompletionHandlerV3 delegate, scrollable tabs");