// Copyright (c) 2026, Lê Ngọc and contributors
// For license information, please see license.txt

// ═══════════════════════════════════════════════════════════════════════════
// FVB Admin — Phase 1 platform (docs/design/de-xuat-cai-tien-quotation-pricing.md §3A)
//   A1: source_type = Autocomplete, options nạp động từ SourceTypeRegistry
//       (formula_builder.api.source_type_registry.list_source_types) — 17 built-in
//       + mọi custom type đăng ký qua hooks `fb_source_types`.
//   A2: Form động soạn source_config theo config_schema của source_type đang chọn
//       (get_source_type_schema). Source type phức tạp (array/object lồng nhau:
//       pipeline/conditional/fallback_chain, multipliers, args...) → editor JSON trợ
//       giúp (theo ADR D2 — v1).
//   A3: Nút "Test Source (no doc)" (API cũ) + "Test With Doc..." (API mới
//       test_data_source_with_doc) để test config trên doc thật.
//   A4: Nút "Preview Batch Groups" (formula_builder.api.batch_binding_resolver.preview_batch_groups)
//       xem nhóm batch nào resolve_batch / nhóm nào rơi vào execute_individual trước khi deploy.
// Additive: KHÔNG đổi engine/handler; binding cũ (giá trị chuỗi bất kỳ) vẫn đọc được.
// ═══════════════════════════════════════════════════════════════════════════

var FB_ADMIN = (function () {
	"use strict";

	var _source_types_cache = null; // [{source_type,label,app,batchable,...}]
	var _active = null; // {source_type, schema, meta, cfg} cho editor hiện tại

	function logError(tag, e) {
		if (window.console && console.warn) {
			console.warn("[FVB Admin] " + tag + ":", e);
		}
	}

	// ── A1 helpers ──────────────────────────────────────────────────────────

	function fetchSourceTypes() {
		if (_source_types_cache) {
			return Promise.resolve(_source_types_cache);
		}
		return frappe.call({
			method: "formula_builder.api.source_type_registry.list_source_types"
		}).then(function (r) {
			_source_types_cache = (r && r.message) || [];
			return _source_types_cache;
		});
	}

	function loadSourceTypeOptions(frm) {
		var field = frm.fields_dict.source_type;
		if (!field) {
			return;
		}
		fetchSourceTypes().then(function (list) {
			try {
				var current = frm.doc.source_type || "";
				var choices = (list || []).map(function (d) {
					var appLabel = d.app === "formula_builder" ? "platform" : d.app;
					var badge = d.batchable ? " · batchable" : "";
					return {
						value: d.source_type,
						label: (d.label || d.source_type) + " (" + appLabel + ")",
						description: d.description || ""
					};
				});
				var found = false;
				for (var i = 0; i < choices.length; i++) {
					if (choices[i].value === current) {
						found = true;
						break;
					}
				}
				// Giá trị cũ không còn trong registry → giữ hiển thị (không xoá trên form)
				if (current && !found) {
					choices.push({
						value: current,
						label: current + " (không có trong registry)",
						description: "Binding cũ vẫn đọc được — không migrate dữ liệu."
					});
				}
				if (field.set_data) {
					field.set_data(choices);
				} else {
					field.df.options = choices;
				}
			} catch (e) {
				logError("loadSourceTypeOptions", e);
			}
		});
	}

	// ── HTML / render helpers ───────────────────────────────────────────────

	function esc(value) {
		if (value === null || value === undefined) {
			return "";
		}
		return String(value)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;")
			.replace(/>/g, "&gt;").replace(/"/g, "&quot;");
	}

	function attrValue(value) {
		return esc(value === undefined || value === null ? "" : value);
	}

	function setHtmlField(frm, fieldname, html) {
		var f = frm.fields_dict[fieldname];
		if (!f || !f.$wrapper) {
			return false;
		}
		f.$wrapper.html(html);
		return true;
	}

	function parseRawConfig(frm) {
		var raw = frm.doc.source_config;
		if (!raw) {
			return {};
		}
		if (typeof raw === "object") {
			return raw;
		}
		try {
			return JSON.parse(raw) || {};
		} catch (e) {
			return {};
		}
	}

	function writeConfig(frm, cfg) {
		try {
			frm.doc.source_config = JSON.stringify(cfg, null, 2);
			frm.refresh_field("source_config");
		} catch (e) {
			logError("writeConfig", e);
		}
	}

	// ── A2 — render form theo config_schema ────────────────────────────────

	function propType(ps) {
		if (!ps) {
			return "string";
		}
		var t = ps.type;
		if (t === undefined) {
			return "string";
		}
		if (Array.isArray(t)) {
			// ["number","string"] → dùng kiểu đầu làm mặc định
			return t[0] || "string";
		}
		return t;
	}

	function isRequired(schema, key) {
		return (schema.required || []).indexOf(key) !== -1;
	}

	function requiredNote(schema, key) {
		var ru = (schema.required_unless || {})[key];
		if (ru) {
			return " (bắt buộc trừ khi " + esc(ru.if) + " = " + esc(ru.equals) + ")";
		}
		return "";
	}

	// Render 1 field theo prop_schema. Giá trị hiện tại từ cfg[key].
	function renderProp(key, ps, cfg, schema) {
		var label = key.replace(/_/g, " ").replace(/\b\w/g, function (c) {
			return c.toUpperCase();
		});
		var desc = ps.description || "";
		var reqd = isRequired(schema, key);
		var t = propType(ps);
		var val = cfg[key];
		var valText = attrValue(val === undefined || val === null ? "" : val);
		var star = reqd ? ' <span class="text-danger">*</span>' : "";
		var rows = [];
		rows.push('<div class="fb-config-row form-group" data-key="' + esc(key) + '" data-type="' + esc(t) + '">');
		rows.push('	<label class="control-label">' + esc(label) + star + requiredNote(schema, key) + "</label>");

		if (t === "boolean") {
			var checked = val === true ? " checked" : "";
			rows.push('	<div class="checkbox"><label><input type="checkbox" data-fb-input="' + esc(key) + '"' + checked + "> " + esc(desc) + "</label></div>");
		} else if (ps.enum) {
			rows.push('	<select class="form-control" data-fb-input="' + esc(key) + '">');
			rows.push('		<option value=""></option>');
			for (var e = 0; e < ps.enum.length; e++) {
				var sel = String(val) === String(ps.enum[e]) ? " selected" : "";
				rows.push('		<option value="' + esc(ps.enum[e]) + '"' + sel + ">" + esc(ps.enum[e]) + "</option>");
			}
			rows.push("	</select>");
		} else if (t === "integer" || t === "number") {
			var step = t === "integer" ? "1" : "any";
			rows.push('	<input type="number" step="' + step + '" class="form-control" data-fb-input="' + esc(key) + '" value="' + valText + '">');
		} else if (t === "array" || t === "object") {
			// Array/object lồng nhau → JSON editor trợ giúp (ADR D2 — v1)
			var jsonVal = val === undefined ? "" : JSON.stringify(val, null, 2);
			rows.push('	<textarea class="form-control fb-json-input" data-fb-input="' + esc(key) + '" rows="3" spellcheck="false">' + esc(jsonVal) + "</textarea>");
			rows.push('	<div class="text-muted small">JSON ' + (t === "array" ? "array" : "object") + (desc ? " — " + esc(desc) : "") + "</div>");
		} else {
			rows.push('	<input type="text" class="form-control" data-fb-input="' + esc(key) + '" value="' + valText + '">');
		}

		if (desc && t !== "boolean" && t !== "array" && t !== "object") {
			rows.push('	<div class="text-muted small">' + esc(desc) + "</div>");
		}
		rows.push("</div>");
		return rows.join("\n");
	}

	function renderSchemaForm(schema, cfg, meta) {
		var props = (schema && schema.properties) || {};
		var keys = [];
		for (var k in props) {
			if (Object.prototype.hasOwnProperty.call(props, k)) {
				keys.push(k);
			}
		}
		var parts = [];
		if (!keys.length) {
			parts.push('<div class="text-muted">Source type này không có config schema — bỏ trống <code>source_config</code> hoặc soạn JSON trực tiếp bên dưới.</div>');
		} else {
			for (var i = 0; i < keys.length; i++) {
				parts.push(renderProp(keys[i], props[keys[i]], cfg, schema));
			}
		}
		return parts.join("\n");
	}

	function updateStatusLine($wrap, cfg, schema, meta) {
		var $status = $wrap.find(".fb-config-status");
		if (!$status.length) {
			return;
		}
		if (!schema) {
			$status.text("");
			return;
		}
		var props = schema.properties || {};
		var missing = [];
		var reqs = schema.required || [];
		var i;
		for (i = 0; i < reqs.length; i++) {
			var key = reqs[i];
			var val = cfg[key];
			if (val === undefined || val === null || val === "") {
				// tôn trọng required_unless
				var ru = (schema.required_unless || {})[key];
				if (ru && cfg[ru.if] === ru.equals) {
					continue;
				}
				missing.push(key);
			}
		}
		if (missing.length) {
			$status.html('<span class="text-warning small">Thiếu required: <b>' + esc(missing.join(", ")) + "</b></span>");
		} else {
			$status.html('<span class="text-success small">Config đầy đủ required fields.</span>');
		}
	}

	function bindEditorEvents(frm, $wrap, schema, meta) {
		var sourceType = frm.doc.source_type;
		var cfg = _active ? _active.cfg : {};

		function applyFromDom() {
			$wrap.find("[data-fb-input]").each(function () {
				var key = this.getAttribute("data-fb-input");
				var $el = $(this);
				var type = $el.attr("type") || "";
				var tag = this.tagName.toLowerCase();
				if ($el.hasClass("fb-json-input")) {
					var rawTxt = $el.val();
					if (rawTxt && String(rawTxt).trim()) {
						try {
							cfg[key] = JSON.parse(rawTxt);
							$el.removeClass("is-invalid");
						} catch (e) {
							$el.addClass("is-invalid");
							return; // giữ nguyên giá trị cũ tới khi JSON hợp lệ
						}
					} else if (cfg.hasOwnProperty(key)) {
						delete cfg[key];
					}
					return;
				}
				if (type === "checkbox") {
					if ($el.is(":checked")) {
						cfg[key] = true;
					} else {
						delete cfg[key];
					}
					return;
				}
				if (type === "number") {
					var nv = $el.val();
					if (nv === null || nv === undefined || String(nv).trim() === "") {
						delete cfg[key];
					} else {
						var num = parseFloat(nv);
						if (isNaN(num)) {
							delete cfg[key];
						} else {
							cfg[key] = num;
						}
					}
					return;
				}
				// select / text
				var sv = $el.val();
				if (sv === null || sv === undefined || String(sv).trim() === "") {
					delete cfg[key];
				} else {
					cfg[key] = String(sv);
				}
			});
			writeConfig(frm, cfg);
			updateStatusLine($wrap, cfg, schema, meta);
		}

		$wrap.find("[data-fb-input]").on("change input", applyFromDom);
		$wrap.find(".fb-json-input").on("change", applyFromDom);

		var $btnReset = $wrap.find(".fb-config-reset");
		if ($btnReset.length) {
			$btnReset.on("click", function () {
				var fresh = parseRawConfig(frm);
				_active.cfg = fresh;
				cfg = fresh;
				$wrap.find(".fb-config-body").html(renderSchemaForm(schema, fresh, meta));
				bindEditorEvents(frm, $wrap, schema, meta); // re-bind (nội dung mới)
				updateStatusLine($wrap, fresh, schema, meta);
			});
		}

		// Bind JSON textarea pretty button
		var $btnPretty = $wrap.find(".fb-json-pretty");
		if ($btnPretty.length) {
			$btnPretty.on("click", function () {
				var key = $btnPretty.attr("data-target");
				var $ta = $wrap.find('textarea[data-fb-input="' + key + '"]');
				if ($ta.length) {
					try {
						$ta.val(JSON.stringify(JSON.parse($ta.val()), null, 2));
						applyFromDom();
					} catch (e) {
						frappe.msgprint(__("JSON không hợp lệ"));
					}
				}
			});
		}
	}

	function renderConfigEditor(frm) {
		var rendered = setHtmlField(frm, "source_config_editor_html", '<div class="text-muted small">Đang tải schema…</div>');
		if (!rendered) {
			// Chưa migrate/sync doctype → chưa có HTML field trên site; không render.
			return;
		}
		var sourceType = frm.doc.source_type || "";
		if (!sourceType) {
			setHtmlField(frm, "source_config_editor_html",
				'<div class="text-muted small">Chọn <b>Source Type</b> để soạn <code>source_config</code> theo schema.</div>');
			return;
		}
		frappe.call({
			method: "formula_builder.api.source_type_registry.get_source_type_schema",
			args: { source_type: sourceType },
			callback: function (r) {
				var meta = (r && r.message) || {};
				if (meta.error) {
					setHtmlField(frm, "source_config_editor_html",
						'<div class="text-danger small">' + esc(meta.error) + "</div>");
					return;
				}
				var schema = meta.config_schema || {};
				var cfg = parseRawConfig(frm);
				_active = { source_type: sourceType, schema: schema, meta: meta, cfg: cfg };
				var htmlParts = [];
				htmlParts.push('<div class="fb-config-body">' + renderSchemaForm(schema, cfg, meta) + "</div>");
				htmlParts.push('<div class="fb-config-status text-muted small" style="margin-top:8px;"></div>');
				htmlParts.push('<div class="small text-muted" style="margin-top:4px;">' +
					'<button type="button" class="btn btn-xs btn-default fb-config-reset">' + __("Đọc lại từ JSON") + "</button> " +
					"Trường phức tạp (JSON) có thể soạn thẳng trong <code>source_config</code> bên trên." + "</div>");
				var $wrap = $('<div>' + htmlParts.join("\n") + "</div>");
				var htmlField = frm.fields_dict.source_config_editor_html;
				htmlField.$wrapper.empty().append($wrap);
				bindEditorEvents(frm, $wrap, schema, meta);
				updateStatusLine($wrap, cfg, schema, meta);
			}
		});
	}

	// ── A3 — Test / A4 — Preview (buttons) ─────────────────────────────────

	function currentSourceType(frm) {
		var st = frm.doc.source_type;
		if (!st) {
			frappe.msgprint(__("Chọn Source Type trước."));
			return null;
		}
		return st;
	}

	function testSourceNoDoc(frm) {
		var st = currentSourceType(frm);
		if (!st) {
			return;
		}
		frappe.show_alert({ message: __("Đang test source (không doc)…"), indicator: "orange" });
		frappe.call({
			method: "formula_builder.api.source_type_registry.test_data_source",
			args: { source_type: st, source_config: frm.doc.source_config || "{}" },
			callback: function (r) {
				showTestResult(r && r.message, __("Kết quả test source"));
			}
		});
	}

	function testSourceWithDoc(frm) {
		var st = currentSourceType(frm);
		if (!st) {
			return;
		}
		var d = new frappe.ui.Dialog({
			title: __("Test source trên doc thật"),
			fields: [
				{
					fieldname: "doctype", label: __("DocType"), fieldtype: "Link",
					options: "DocType", default: frm.doc.applies_to_doctype || "", reqd: 1
				},
				{ fieldname: "docname", label: __("DocName"), fieldtype: "Dynamic Link",
					options: "doctype", reqd: 1 },
				{
					fieldname: "resolved_context_json", label: __("Resolved context (JSON, tuỳ chọn)"),
					fieldtype: "Code", options: "JSON", default: "{}"
				}
			],
			primary_action_label: __("Test"),
			primary_action: function () {
				var vals = d.get_values();
				if (!vals) {
					return;
				}
				d.hide();
				frappe.show_alert({ message: __("Đang test source trên {0} / {1}…", [vals.doctype, vals.docname]), indicator: "orange" });
				frappe.call({
					method: "formula_builder.api.source_type_registry.test_data_source_with_doc",
					args: {
						source_type: st,
						source_config: frm.doc.source_config || "{}",
						doctype: vals.doctype,
						docname: vals.docname,
						resolved_context_json: vals.resolved_context_json || "{}"
					},
					callback: function (r) {
						showTestResult(r && r.message, __("Kết quả test trên doc"));
					}
				});
			}
		});
		d.show();
	}

	function showTestResult(msg, title) {
		if (!msg) {
			frappe.msgprint(__("Không nhận được phản hồi từ server."));
			return;
		}
		if (msg.success) {
			var valueHtml = typeof msg.value === "string"
				? esc(msg.value)
				: '<pre class="pre-wrap">' + esc(JSON.stringify(msg.value, null, 2)) + "</pre>";
			frappe.msgprint({
				title: title,
				indicator: "green",
				message: __("Resolved OK") + ' — type: <code>' + esc(msg.type) + "</code><br>" + valueHtml
			});
		} else {
			var errs = msg.validation_errors
				? "<ul><li>" + (msg.validation_errors || []).map(esc).join("</li><li>") + "</li></ul>"
				: "";
			frappe.msgprint({
				title: title,
				indicator: "red",
				message: esc(msg.error || "Lỗi") + errs
			});
		}
	}

	function validateConfig(frm) {
		var st = currentSourceType(frm);
		if (!st) {
			return;
		}
		frappe.call({
			method: "formula_builder.api.source_type_registry.validate_binding_source_config",
			args: { source_type: st, source_config: frm.doc.source_config || "{}" },
			callback: function (r) {
				var m = (r && r.message) || {};
				if (m.valid) {
					frappe.msgprint({ title: __("Config hợp lệ"), indicator: "green", message: __("source_config khớp schema.") });
				} else {
					var errHtml = (m.errors || []).map(function (e) {
						return "<li>" + esc(e) + "</li>";
					}).join("");
					frappe.msgprint({ title: __("Config có lỗi"), indicator: "red", message: "<ul>" + errHtml + "</ul>" });
				}
			}
		});
	}

	function renderGroupRows(groups) {
		if (!groups || !groups.length) {
			return '<div class="text-muted">Không có binding batchable trong scope.</div>';
		}
		var rows = [];
		for (var i = 0; i < groups.length; i++) {
			var g = groups[i];
			var strategyBadge = "";
			if (g.strategy === "resolve_batch") {
				strategyBadge = '<span class="label label-success">resolve_batch</span>';
			} else if (g.strategy === "resolve_batch_query") {
				strategyBadge = '<span class="label label-warning">resolve_batch_query</span>';
			} else {
				strategyBadge = '<span class="label label-danger">execute_individual</span>';
			}
			rows.push("<tr><td><code>" + esc(g.source_type) + "</code></td><td><code>" + esc(g.fingerprint) + "</code></td>" +
				"<td>" + strategyBadge + "</td><td>" + esc(g.binding_count) + "</td><td class='small'>" +
				esc((g.variables || []).join(", ")) + "</td></tr>");
		}
		return '<table class="table table-bordered table-hover">' +
			"<thead><tr><th>Source type</th><th>Fingerprint</th><th>Strategy</th><th>#binding</th><th>Biến</th></tr></thead><tbody>" +
			rows.join("\n") + "</tbody></table>";
	}

	function renderIndividualList(list) {
		if (!list || !list.length) {
			return "";
		}
		var rows = (list || []).map(function (b) {
			return "<tr><td><code>" + esc(b.variable_name) + "</code></td><td><code>" + esc(b.source_type) + "</code></td>" +
				"<td class='small'>" + esc(b.reason) + "</td></tr>";
		}).join("\n");
		return '<h5>' + __("Binding không batch (N+1)") + " — " + esc(list.length) + "</h5>" +
			'<table class="table table-bordered"><tbody>' + rows + "</tbody></table>";
	}

	function previewBatchGroups(frm) {
		var d = new frappe.ui.Dialog({
			title: __("Preview Batch Groups"),
			fields: [
				{
					fieldname: "doctype", label: __("Scope DocType (trống = global)"), fieldtype: "Link",
					options: "DocType", default: frm.doc.applies_to_doctype || ""
				},
				{
					fieldname: "applies_to_field", label: __("Scope Field"), fieldtype: "Data",
					default: frm.doc.applies_to_field || ""
				},
				{ fieldname: "include_inactive", label: __("Bao gồm binding is_active = 0"), fieldtype: "Check" }
			],
			primary_action_label: __("Preview"),
			primary_action: function () {
				var vals = d.get_values();
				if (!vals) {
					return;
				}
				d.hide();
				frappe.call({
					method: "formula_builder.api.batch_binding_resolver.preview_batch_groups",
					args: {
						doctype: vals.doctype || "",
						applies_to_field: vals.applies_to_field || "",
						include_inactive: vals.include_inactive ? 1 : 0
					},
					callback: function (r) {
						var m = (r && r.message) || {};
						if (m.error) {
							frappe.msgprint({ title: __("Preview thất bại"), indicator: "red", message: esc(m.error) });
							return;
						}
						var msg = '<div class="row">' +
							'<div class="col-sm-3"><b>' + esc(m.summary.total_bindings) + "</b><br><span class='text-muted'>" + __("binding khớp scope") + "</span></div>" +
							'<div class="col-sm-3"><b>' + esc(m.summary.total_groups) + "</b><br><span class='text-muted'>" + __("nhóm batch") + "</span></div>" +
							'<div class="col-sm-3"><b>' + esc(m.summary.individual_bindings) + "</b><br><span class='text-muted'>" + __("chạy cá nhân") + "</span></div>" +
							'<div class="col-sm-3"><b>' + esc(m.summary.estimated_queries) + "</b><br><span class='text-muted'>" + __("query ước tính") + "</span></div>" +
							"</div><hr>" + renderGroupRows(m.groups) + renderIndividualList(m.individual_bindings);
						frappe.msgprint({
							title: __("Preview batch groups"),
							message: msg,
							wide: true
						});
					}
				});
			}
		});
		d.show();
	}

	function addUtilityButtons(frm) {
		if (frm.fb_admin_buttons_added) {
			return;
		}
		frm.fb_admin_buttons_added = true;
		var group = __("Data Source");
		frm.add_custom_button(__("Validate Config"), function () { validateConfig(frm); }, group);
		frm.add_custom_button(__("Test Source (no doc)"), function () { testSourceNoDoc(frm); }, group);
		frm.add_custom_button(__("Test With Doc…"), function () { testSourceWithDoc(frm); }, group);
		frm.add_custom_button(__("Preview Batch Groups"), function () { previewBatchGroups(frm); }, group);
	}

	return {
		refresh: function (frm) {
			try {
				loadSourceTypeOptions(frm);
			} catch (e) {
				logError("refresh/loadSourceTypeOptions", e);
			}
			try {
				renderConfigEditor(frm);
			} catch (e) {
				logError("refresh/renderConfigEditor", e);
			}
			try {
				addUtilityButtons(frm);
			} catch (e) {
				logError("refresh/addUtilityButtons", e);
			}
		},
		source_type_changed: function (frm) {
			try {
				renderConfigEditor(frm);
			} catch (e) {
				logError("source_type_changed", e);
			}
		}
	};
})();

frappe.ui.form.on("Formula Variable Binding", {
	refresh: function (frm) {
		FB_ADMIN.refresh(frm);
	},
	source_type: function (frm) {
		FB_ADMIN.source_type_changed(frm);
	}
});
