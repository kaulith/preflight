from pathlib import Path

import pytest

from preflight.js_scanner import JSScanner
from preflight.models import Match, Rule
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"

scanner = JSScanner(load_rules("v16"))


def lines_by_rule(source, file="fixture.js"):
	lines = {}
	for finding in scanner.scan(source, file):
		lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(rule_lines) for rule_id, rule_lines in lines.items()}


def lines_matched(match, source):
	rule = Rule(
		id="digest-rule",
		title="Digest rule",
		severity="error",
		match=match,
		message="Digest rule.",
		replacement="None.",
		references=(),
	)
	return sorted(finding.line for finding in JSScanner([rule]).scan(source, "fixture.js"))


DUE_DATE = Match(type="doctype_field", fields=("Sales Invoice.due_date",))
POST_ONLY = Match(type="http_method", paths=("digest.api.send_digest",), rejected_methods=("GET",))
ITEM_RATE = Match(
	type="doctype_field",
	fields=("Sales Invoice Item.rate",),
	child_tables=(("Sales Invoice.items", "Sales Invoice Item"),),
)


def test_violations_are_reported_on_their_lines():
	assert lines_by_rule((FIXTURES / "violations.js").read_text()) == {
		"v16-deprecated-client-get-js": [7],
		"v16-removed-blog-doctypes": [29, 30],
		"v16-removed-changelog-feed-js": [14],
		"v16-filter-hidden-argument": [37],
		"v16-removed-energy-points-js": [4, 5],
		"v16-removed-filter-methods": [34],
		"v16-removed-grid-setup-download": [36],
		"v16-removed-list-sidebar": [3],
		"v16-removed-newsletter": [23],
		"v16-removed-newsletter-doctypes": [20],
		"v16-removed-octicons": [16],
		"v16-removed-query-report-print-methods": [35],
		"v16-removed-workspace-sidebar-items": [15],
		"v16-web-form-progress-dots": [38],
	}


def test_removed_doctype_is_reported_where_a_client_api_reads_it():
	source = 'frappe.db.get_list("Blog Post", { filters: { published: 1 } });\nfrappe.set_route("List", "Newsletter");\n'
	assert lines_by_rule(source) == {
		"v16-removed-blog-doctypes": [1],
		"v16-removed-newsletter-doctypes": [2],
	}


def test_removed_doctype_named_outside_a_client_api_is_not_reported():
	assert lines_by_rule('frm.set_value("subject", __("Newsletter"));\n') == {}


@pytest.mark.parametrize(
	"call", ['frappe.db\n\t.get_list("Blog Post");', 'frappe.new_doc(\n\t"Blog Post",\n);']
)
def test_removed_doctype_in_a_multiline_call_is_reported_on_its_own_line(call):
	assert lines_by_rule(call + "\n") == {"v16-removed-blog-doctypes": [2]}


def test_record_name_after_the_doctype_on_another_line_is_not_reported():
	assert lines_by_rule('frappe.set_route(\n\t"Form",\n\t"Web Page",\n\t"Blog Post",\n);\n') == {}


@pytest.mark.parametrize("fixture", ["clean.js", "clean_erpnext.js", "clean.scss"])
def test_clean_file_has_no_findings(fixture):
	assert scanner.scan((FIXTURES / fixture).read_text(), fixture) == []


def test_longer_name_with_the_same_prefix_is_not_reported():
	assert lines_by_rule("frappe.views.ListSidebarGroupBy.refresh();\n") == {}


def test_endpoint_string_is_matched_in_any_quote_style():
	source = "frappe.call({ method: 'frappe.client.get_js' });\nfrappe.xcall(`frappe.client.get_js`);\n"
	assert lines_by_rule(source) == {"v16-deprecated-client-get-js": [1, 2]}


def test_endpoint_outside_a_string_is_not_reported():
	assert lines_by_rule("frappe.client.get_js(items);\n") == {}


def test_endpoint_between_two_strings_is_not_reported():
	assert lines_by_rule('const url = "/api/method/" + frappe.client.get_js + "?v=1";\n') == {}


def test_path_in_a_multiline_template_is_reported_on_its_own_line():
	source = "const help = `Call\n\tfrappe.client.get_js\nfrom a button`;\n"
	assert lines_by_rule(source) == {"v16-deprecated-client-get-js": [2]}


def test_path_named_inside_a_longer_string_is_not_reported():
	assert lines_by_rule('frappe.msgprint(__("Moved out of frappe.email.doctype.newsletter"));\n') == {}


def test_path_that_only_shares_a_prefix_is_not_reported():
	assert lines_by_rule('frappe.xcall("frappe.utils.gzip_compression");\n') == {}


def test_string_a_string_rule_reports_is_not_reported_again_as_an_import():
	source = 'frappe.call({ method: "frappe.utils.weasyprint.download_pdf" });\n'
	findings = JSScanner(load_rules("v17")).scan(source, "fixture.js")
	assert [finding.rule.id for finding in findings] == ["v17-weasyprint-download-pdf"]


def test_commented_out_code_is_not_reported():
	source = (
		"\t// new frappe.views.ListSidebar({ doctype: doctype });\n"
		"\t/*\n\tfrappe.energy_points.get_points(5);\n\t*/\n"
		"\tfrm.refresh(); // frappe.views.ListSidebar went away in v16\n"
	)
	assert lines_by_rule(source) == {}


def test_comment_marker_inside_a_string_is_not_a_comment():
	source = 'const url = "https://example.com"; new frappe.views.ListSidebar();\n'
	assert lines_by_rule(source) == {"v16-removed-list-sidebar": [1]}


def test_comment_marker_inside_a_template_literal_is_not_a_comment():
	source = "$(wrapper).append(`<a href=//example.com>${frappe.boot.changelog_feed.length}</a>`);\n"
	assert lines_by_rule(source) == {"v16-removed-changelog-feed-js": [1]}


def test_slash_does_not_hide_the_comment_after_it():
	source = (
		"const tick = /`/;\n"
		"const half = width / 2; // frappe.views.ListSidebar went away in v16\n"
		"// frappe.energy_points too\n"
	)
	assert lines_by_rule(source) == {}


def test_finding_carries_file_and_snippet():
	(finding,) = scanner.scan("\n\tfrappe.energy_points.get_points(5);\n", "digest/public/js/digest.js")
	assert (finding.file, finding.line) == ("digest/public/js/digest.js", 2)
	assert finding.snippet == "frappe.energy_points.get_points(5);"


def test_snippet_is_cut_at_200_characters():
	(finding,) = scanner.scan(f"frappe.energy_points.get_points({'1, ' * 100});\n", "digest.js")
	assert len(finding.snippet) == 200


@pytest.mark.parametrize(
	("call", "line"),
	[
		('frappe.db.get_list("Bin", {\n\tfields: ["item_code", "sum(actual_qty) as qty"],\n});', 2),
		('frappe.db.get_value("Bin", { item_code },\n\t["warehouse", "sum(actual_qty) as qty"]);', 2),
		(
			(
				'frappe.call({\n\tmethod: "frappe.client.get_list",\n'
				'\targs: { doctype: "Bin", fields: ["sum(actual_qty) as qty"] },\n'
				"\tcallback: (r) => r.message.filter((row) => /[(]/.test(row.qty)),\n});"
			),
			3,
		),
		(
			'frappe.xcall("frappe.client.get_value", {\n\tdoctype: "Bin",\n\tfieldname: "sum(actual_qty) as qty",\n});',
			3,
		),
	],
)
def test_sql_function_in_the_fields_of_a_client_query_is_reported(call, line):
	assert lines_by_rule(call + "\n") == {"v16-sql-function-string-fields": [line]}


def test_sql_function_passed_to_another_method_is_not_reported():
	source = 'frappe.call({ method: "digest.api.stock", args: { fields: ["sum(actual_qty) as qty"] } });\n'
	assert lines_by_rule(source) == {}


@pytest.mark.parametrize(
	"call",
	[
		'frappe.db.get_list("Sales Invoice", { fields: ["name", "due_date"] });',
		'frappe.db.get_list("Sales Invoice", { filters: { due_date: ["<", today] } });',
		'frappe.db.get_list("Customer", { filters: [["Sales Invoice", "due_date", "<", today]] });',
		'frappe.db.get_value("Sales Invoice", name, "due_date");',
		'frappe.db.set_value("Sales Invoice", name, "due_date", today);',
		'frappe.db.set_value("Sales Invoice", name, { due_date: today });',
		'frappe.call("frappe.client.get_value", { doctype: "Sales Invoice", fieldname: ["due_date"] });',
	],
)
def test_field_named_beside_its_doctype_is_reported(call):
	assert lines_matched(DUE_DATE, call + "\n") == [1]


@pytest.mark.parametrize(
	"call",
	[
		'frappe.db.get_list(doctype, { fields: ["due_date"] });',
		'frappe.db.get_list("Purchase Invoice", { fields: ["due_date"] });',
		'frappe.db.get_value("Sales Invoice", { status: "due_date" }, "name");',
		'const help = \'frappe.db.get_value("Sales Invoice", name, "due_date")\';',
	],
)
def test_field_not_named_beside_its_doctype_is_not_reported(call):
	assert lines_matched(DUE_DATE, call + "\n") == []


@pytest.mark.parametrize(
	"call",
	[
		'frappe.db\n\t.get_value("Sales Invoice", name, "due_date")\n\t.then((r) => r);',
		'frappe\n\t.call({ method: "frappe.client.get_value", args: { doctype: "Sales Invoice", fieldname: "due_date" } });',
	],
)
def test_field_named_in_a_client_query_split_at_a_dot_is_reported(call):
	assert lines_matched(DUE_DATE, call + "\n") == [2]


@pytest.mark.parametrize(
	"reference",
	[
		"form.doc.due_date",
		'form.doc["due_date"]',
		"form.doc?.due_date",
		"form.doc.due_date = today",
		"form.fields_dict.due_date",
		'form.fields_dict["due_date"]',
		'form.set_value("due_date", today)',
		"form.set_value({ due_date: today })",
		'form.set_df_property("due_date", "read_only", 1)',
		'form.toggle_reqd(["customer", "due_date"], true)',
		'form.set_query("due_date", () => ({}))',
		'form.get_field("due_date")',
		"items.forEach((row) => form.doc.due_date)",
	],
)
def test_field_a_form_handler_reaches_is_reported(reference):
	source = f'frappe.ui.form.on("Sales Invoice", {{\n\trefresh(form) {{\n\t\t{reference};\n\t}},\n}});\n'
	assert lines_matched(DUE_DATE, source) == [3]


@pytest.mark.parametrize(
	"handler",
	[
		"due_date(frm) {}",
		"due_date: function (frm) {}",
		"due_date: (frm) => {}",
		"async due_date(frm) {}",
		'"due_date": function (frm) {}',
	],
)
def test_handler_named_after_a_field_is_reported(handler):
	assert lines_matched(DUE_DATE, f'frappe.ui.form.on("Sales Invoice", {{\n\t{handler},\n}});\n') == [2]


@pytest.mark.parametrize(
	"source",
	[
		"frm.doc.due_date;",
		'frappe.ui.form.on("Purchase Invoice", { refresh(frm) { frm.doc.due_date; } });',
		"frappe.ui.form.on(doctype, { refresh(frm) { frm.doc.due_date; } });",
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { frm.doc[fieldname]; } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { other.doc.due_date; } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { this.frm.doc.due_date; } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { rows.map((frm) => frm.doc.due_date); } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { frm = other; frm.doc.due_date; } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { frm.set_query("due_date", "items", query); } });',
		'frappe.ui.form.on("Sales Invoice", { refresh(frm) { frm.add_fetch("due_date", "a", "b"); } });',
		'frappe.ui.form.on("Sales Invoice", { due_date: handler });',
	],
)
def test_field_a_form_handler_does_not_reach_is_not_reported(source):
	assert lines_matched(DUE_DATE, source + "\n") == []


def test_set_query_on_a_child_table_reports_the_table():
	match = Match(type="doctype_field", fields=("Sales Invoice.items",))
	source = 'frappe.ui.form.on("Sales Invoice", { refresh(frm) { frm.set_query("item_code", "items", query); } });\n'
	assert lines_matched(match, source) == [1]


@pytest.mark.parametrize(
	"body",
	[
		"locals[dt][dn].rate;",
		"let row = locals[dt][dn];\n\t\trow.rate;",
		"var a = 1, row = locals[dt][dn];\n\t\trow.rate;",
	],
)
def test_field_of_a_child_row_is_reported(body):
	source = f'frappe.ui.form.on("Sales Invoice Item", {{\n\tqty(frm, dt, dn) {{\n\t\t{body}\n\t}},\n}});\n'
	assert lines_matched(ITEM_RATE, source) == [body.count("\n") + 3]


@pytest.mark.parametrize(
	"body",
	[
		"frm.doc.rate;",
		"locals[dn][dt].rate;",
		"let row = locals[dt][dn].parent;\n\t\trow.rate;",
		"let row = locals[dt][dn];\n\t\trows.forEach((row) => row.rate);",
		"let row = locals[dt][dn];\n\t\trow = other;\n\t\trow.rate;",
	],
)
def test_field_off_the_child_row_is_not_reported(body):
	source = f'frappe.ui.form.on("Sales Invoice Item", {{\n\tqty(frm, dt, dn) {{\n\t\t{body}\n\t}},\n}});\n'
	assert lines_matched(ITEM_RATE, source) == []


def test_undeclared_import_is_not_matched_in_client_code():
	match = Match(type="undeclared_import", paths=("bleach",), dependencies=("bleach",))
	assert lines_matched(match, 'frappe.xcall("bleach.clean", { html });\n') == []


@pytest.mark.parametrize(
	"source",
	['frappe.ui.form.on("Newsletter", {});', 'frappe.listview_settings["Newsletter"] = {};'],
)
def test_script_registered_on_a_removed_doctype_is_a_warning(source):
	assert [finding.rule.severity for finding in scanner.scan(source, "fixture.js")] == ["warning"]


def test_a_call_beside_a_registered_script_keeps_the_error():
	source = 'frappe.ui.form.on("Newsletter", {}); frappe.db.exists("Newsletter", "Launch");'
	assert [finding.rule.severity for finding in scanner.scan(source, "fixture.js")] == ["error"]


def test_stylesheet_comments_urls_and_slashes_stay_on_their_line():
	source = (
		'@import "frappe/public/scss/common";\n'
		"// .octicon went away in v16\n"
		".banner { background: url(//cdn.example.com/banner.png); } .octicon-mail { color: red; }\n"
		".grid { grid-area: 1 / 2; font: 12px/1.5 Inter; width: calc(100% / 3); } // .octicon too\n"
		".octicon { display: none; }\n"
	)
	assert lines_by_rule(source, "digest/public/scss/digest.scss") == {"v16-removed-octicons": [3, 5]}


@pytest.mark.parametrize(
	"call",
	[
		'frappe.call({ method: "digest.api.send_digest", type: "GET" });',
		'createResource({ url: "digest.api.send_digest", method: "GET" });',
		'fetch("/api/method/digest.api.send_digest");',
		'fetch("/api/method/digest.api.send_digest", { method: "GET" });',
		'$.get("/api/method/digest.api.send_digest");',
		'$.ajax({ url: "/api/method/digest.api.send_digest" });',
		'axios.get("/api/method/digest.api.send_digest");',
	],
)
def test_request_by_a_rejected_http_method_is_reported(call):
	assert lines_matched(POST_ONLY, f"{call}\n") == [1]


@pytest.mark.parametrize(
	"call",
	[
		'frappe.call({ method: "digest.api.send_digest" });',
		'frappe.call({ method: "digest.api.send_digest", type: request_type });',
		'createResource({ url: "digest.api.send_digest" });',
		'fetch("/api/method/digest.api.send_digest", { method: "POST" });',
		'fetch("/api/method/digest.api.send_digest", options);',
		'$.ajax({ url: "/api/method/digest.api.send_digest", type: "POST" });',
	],
)
def test_request_the_method_accepts_or_that_is_computed_is_not_reported(call):
	assert lines_matched(POST_ONLY, f"{call}\n") == []
