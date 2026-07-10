app_name = "formula_builder"
app_title = "Formula Builder"
app_publisher = "Lê Ngọc"
app_description = "Generic Excel-like formula engine and builder for Frappe"
app_email = "lengoc1490@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "formula_builder",
# 		"logo": "/assets/formula_builder/logo.png",
# 		"title": "Formula Builder",
# 		"route": "/formula_builder",
# 		"has_permission": "formula_builder.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/formula_builder/css/formula_builder.css"
# app_include_js = "/assets/formula_builder/js/formula_builder.js"

app_include_css = [
    "/assets/formula_builder/css/formula_builder_vars.css?v=30.0.0",
    "/assets/formula_builder/css/formula_builder_monaco.css?v=30.0.0",
    "/assets/formula_builder/css/formula_builder.css?v=30.0.0",
    "/assets/formula_builder/css/formula_builder_field.css?v=30.0.0",
    "/assets/formula_builder/css/formula_builder_dialog.css?v=30.0.0",
]

app_include_js = [
    "/assets/formula_builder/js/formula_builder.js?v=30.0.0",
    "/assets/formula_builder/js/formula_builder_field.js?v=30.0.0",
    "/assets/formula_builder/js/formula_builder_dialog.js?v=30.0.0",
]

# include js, css files in header of web template
# web_include_css = "/assets/formula_builder/css/formula_builder.css"
# web_include_js = "/assets/formula_builder/js/formula_builder.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "formula_builder/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "formula_builder/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "formula_builder.utils.jinja_methods",
# 	"filters": "formula_builder.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "formula_builder.install.before_install"
# after_install = "formula_builder.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "formula_builder.uninstall.before_uninstall"
# after_uninstall = "formula_builder.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "formula_builder.utils.before_app_install"
# after_app_install = "formula_builder.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "formula_builder.utils.before_app_uninstall"
# after_app_uninstall = "formula_builder.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "formula_builder.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"formula_builder.tasks.all"
# 	],
# 	"daily": [
# 		"formula_builder.tasks.daily"
# 	],
# 	"hourly": [
# 		"formula_builder.tasks.hourly"
# 	],
# 	"weekly": [
# 		"formula_builder.tasks.weekly"
# 	],
# 	"monthly": [
# 		"formula_builder.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "formula_builder.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "formula_builder.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "formula_builder.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["formula_builder.utils.before_request"]
# after_request = ["formula_builder.utils.after_request"]

# Job Events
# ----------
# before_job = ["formula_builder.utils.before_job"]
# after_job = ["formula_builder.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"formula_builder.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

doc_events = {
    "Formula Global Variable":    {"on_update": "formula_builder.api.formula_builder.invalidate_suggestions_cache"},
    "Formula Set":                {"on_update": "formula_builder.api.formula_builder.invalidate_suggestions_cache"},
    "Formula Builder Settings":   {"on_update": "formula_builder.api.formula_builder.invalidate_suggestions_cache"},
}

fixtures = [
    {"doctype": "Formula Builder Settings", "filters": [["name", "=", "Formula Builder Settings"]]}
]

after_migrate = "formula_builder.install.after_migrate"