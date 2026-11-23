import json

import pytest
from jinja2 import TemplateSyntaxError

from preflight.app_scan import Scanners, scan_app
from preflight.jinja_scanner import JinjaScanner, renders_html, renders_layout
from preflight.models import Report
from preflight.rule_loader import load_rules

RULES = load_rules("v16")
REMOVED_FIELD = "v16-erpnext-removed-fields"
TAX_DETAIL = "v16-erpnext-item-wise-tax-detail"
BLOG_DOCTYPES = "v16-removed-blog-doctypes"

scanner = JinjaScanner(RULES)


def rule_ids(source, doc_doctypes=()):
	return [finding.rule.id for finding in scanner.scan(source, "fixture.html", doc_doctypes)]


@pytest.fixture
def app_path(tmp_path):
	"""The package of `digest`, inside its repository."""
	path = tmp_path / "digest" / "digest"
	path.mkdir(parents=True)
	(path / "hooks.py").write_text('app_name = "digest"\n', encoding="utf-8")
	return path


def write_record(app_path, folder, name, record, **beside):
	"""A `<module>/<folder>/<name>/<name>.json` record, with the files named by suffix beside it."""
	directory = app_path / "accounts" / folder / name
	directory.mkdir(parents=True)
	(directory / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")
	for suffix, text in beside.items():
		(directory / f"{name}.{suffix}").write_text(text, encoding="utf-8")


def scan(app_path, skip_tests=False):
	report = Report(site=None, target="v16", apps=["digest"])
	scan_app(report, Scanners(RULES), "digest", app_path, skip_tests)
	return report


@pytest.mark.parametrize(
	"source",
	[
		"{{ doc.party_balance }}",
		'{{ doc["party_balance"] }}',
		'{{ doc.get("party_balance") }}',
	],
)
def test_field_read_on_the_surface_doc_is_reported(source):
	assert rule_ids(source, ("Payment Entry",)) == [REMOVED_FIELD]


def test_field_on_an_untyped_doc_is_not_reported():
	assert rule_ids("{{ doc.party_balance }}") == []


def test_field_of_another_doctype_is_not_reported():
	assert rule_ids("{{ doc.party_balance }}", ("Sales Invoice",)) == []


def test_finding_keeps_its_template_line():
	finding = scanner.scan("<p>\n{{ doc.party_balance }}\n</p>", "fixture.html", ("Payment Entry",))[0]
	assert (finding.line, finding.snippet) == (2, "{{ doc.party_balance }}")


@pytest.mark.parametrize(
	"source",
	[
		"{% for row in doc.taxes %}{{ row.item_wise_tax_detail }}{% endfor %}",
		'{% for row in doc.get("taxes") %}{{ row.item_wise_tax_detail }}{% endfor %}',
		'{% for row in doc["taxes"] %}{{ row.item_wise_tax_detail }}{% endfor %}',
		"{% for row in doc.taxes[:2] %}{{ row.item_wise_tax_detail }}{% endfor %}",
		"{{ doc.taxes[0].item_wise_tax_detail }}",
		"{{ doc.taxes[-1].item_wise_tax_detail }}",
		"{% set row = doc.taxes[0] %}{{ row.item_wise_tax_detail }}",
		"{% set rows = doc.taxes %}{% for row in rows %}{{ row.item_wise_tax_detail }}{% endfor %}",
		"{% with row = doc.taxes[0] %}{{ row.item_wise_tax_detail }}{% endwith %}",
	],
)
def test_field_read_on_a_child_row_is_reported(source):
	assert rule_ids(source, ("Sales Invoice",)) == [TAX_DETAIL]


def test_field_on_a_table_itself_is_not_a_row_field():
	assert rule_ids("{{ doc.taxes.item_wise_tax_detail }}", ("Sales Invoice",)) == []


@pytest.mark.parametrize(
	"source",
	[
		'{{ frappe.get_doc("Payment Entry", name).party_balance }}',
		'{% set entry = frappe.get_doc("Payment Entry", name) %}{{ entry.party_balance }}',
		'{{ frappe.get_cached_doc(doctype="Payment Entry", name=name).party_balance }}',
	],
)
def test_field_of_a_doc_loaded_with_a_literal_doctype_is_reported(source):
	assert rule_ids(source) == [REMOVED_FIELD]


def test_loading_a_removed_doctype_is_reported():
	assert rule_ids('{% set post = frappe.get_doc("Blog Post", name) %}') == [BLOG_DOCTYPES]


@pytest.mark.parametrize(
	"source",
	[
		'{{ frappe.get_all("Blog Post") }}',
		"{{ frappe.utils.party_balance }}",
		"{{ doc.party_balance() }}",
		"{% for doc in documents %}{{ doc.party_balance }}{% endfor %}",
		"{% set doc = other %}{{ doc.party_balance }}",
		"{% macro total(doc) %}{{ doc.party_balance }}{% endmacro %}",
		"{% with doc = other %}{{ doc.party_balance }}{% endwith %}",
	],
)
def test_what_is_not_a_read_of_the_surface_doc_is_not_reported(source):
	assert rule_ids(source, ("Payment Entry",)) == []


@pytest.mark.parametrize(
	"source, reported",
	[
		("{% for row in doc.taxes %}{% endfor %}{{ row.item_wise_tax_detail }}", False),
		("{% for x in y %}{% set row = doc.taxes[0] %}{% endfor %}{{ row.item_wise_tax_detail }}", False),
		("{% with row = doc.taxes[0] %}{% endwith %}{{ row.item_wise_tax_detail }}", False),
		("{% if a %}{% set row = doc.taxes[0] %}{% endif %}{{ row.item_wise_tax_detail }}", True),
		(
			"{% for row in doc.taxes %}{% block b %}{{ row.item_wise_tax_detail }}{% endblock %}{% endfor %}",
			False,
		),
		(
			(
				"{% for row in doc.taxes %}{% block b scoped %}{{ row.item_wise_tax_detail }}{% endblock %}"
				"{% endfor %}"
			),
			True,
		),
		("{% set row = doc.taxes[0] %}{% block b %}{{ row.item_wise_tax_detail }}{% endblock %}", True),
	],
)
def test_names_follow_jinja_scoping(source, reported):
	assert rule_ids(source, ("Sales Invoice",)) == ([TAX_DETAIL] if reported else [])


@pytest.mark.parametrize(
	"source",
	["{%= doc.party_balance %}", "{%~ doc.party_balance %}", "{% if(!doc) { %}<p></p>{% } %}"],
)
def test_microtemplate_is_skipped(source):
	assert rule_ids(source, ("Payment Entry",)) == []


def test_invalid_template_raises():
	with pytest.raises(TemplateSyntaxError):
		scanner.scan("{% if %}", "fixture.html")


@pytest.mark.parametrize(
	"record, expected",
	[
		({"custom_format": 1}, True),
		({"standard": "Yes"}, True),
		({"standard": "Yes", "format_data": "[]"}, False),
		({"custom_format": 1, "print_format_type": "JS"}, False),
		({"custom_format": 1, "raw_printing": 1}, False),
		({"custom_format": 1, "print_format_for": "Report"}, False),
		({"custom_format": 1, "print_format_builder_beta": 1}, False),
		({"standard": "No"}, False),
	],
)
def test_print_format_html_renders_as_frappe_picks_it(record, expected):
	assert renders_html(record) == expected


@pytest.mark.parametrize(
	"record, expected",
	[
		({"format_data": "[]"}, True),
		({"format_data": "[]", "custom_format": 1}, False),
		({"format_data": "{}", "custom_format": 1, "print_format_builder_beta": 1}, True),
		({"format_data": "[]", "print_format_for": "Report"}, False),
		({}, False),
	],
)
def test_print_format_layout_renders_as_frappe_picks_it(record, expected):
	assert renders_layout(record) == expected


def test_layout_names_a_field_with_no_line():
	findings, unparsed = scanner.scan_layout(
		json.dumps([{"fieldname": "party_balance"}]), "layout.json", "Payment Entry"
	)
	assert [(finding.rule.id, finding.line, finding.snippet) for finding in findings] == [
		(REMOVED_FIELD, None, '"fieldname": "party_balance"')
	]
	assert unparsed == 0


@pytest.mark.parametrize(
	"layout",
	[
		[{"fieldname": "taxes", "visible_columns": [{"fieldname": "item_wise_tax_detail"}]}],
		{
			"sections": [
				{
					"columns": [
						{
							"fields": [
								{
									"fieldname": "taxes",
									"table_columns": [{"fieldname": "item_wise_tax_detail"}],
								}
							]
						}
					]
				}
			]
		},
	],
)
def test_layout_table_columns_are_child_fields(layout):
	findings, _ = scanner.scan_layout(json.dumps(layout), "layout.json", "Sales Invoice")
	assert [finding.rule.id for finding in findings] == [TAX_DETAIL]


@pytest.mark.parametrize(
	"entry",
	[
		{"fieldname": "_custom_html", "fieldtype": "HTML", "options": "{{ doc.party_balance }}"},
		{
			"fieldname": "print_heading_template",
			"fieldtype": "Custom HTML",
			"options": "{{ doc.party_balance }}",
		},
		{"fieldname": "custom_html_header", "fieldtype": "HTML", "html": "{{ doc.party_balance }}"},
	],
)
def test_layout_html_entry_is_read_as_a_template(entry):
	findings, _ = scanner.scan_layout(json.dumps([entry]), "layout.json", "Payment Entry")
	assert [(finding.rule.id, finding.line) for finding in findings] == [(REMOVED_FIELD, None)]


@pytest.mark.parametrize("format_data", ["not json", '{"header": {}}', "[1]"])
def test_layout_that_cannot_be_read_counts_as_unparsed(format_data):
	assert scanner.scan_layout(format_data, "layout.json", "Payment Entry") == ([], 1)


def test_print_format_record_html_has_no_line(app_path):
	write_record(
		app_path,
		"print_format",
		"payment_receipt",
		{
			"doctype": "Print Format",
			"doc_type": "Payment Entry",
			"custom_format": 1,
			"html": "<p>\n{{ doc.party_balance }}</p>",
		},
	)
	assert [(finding.file, finding.line, finding.snippet) for finding in scan(app_path).findings] == [
		(
			"digest/accounts/print_format/payment_receipt/payment_receipt.json",
			None,
			"{{ doc.party_balance }}</p>",
		)
	]


def test_print_format_html_file_replaces_its_record_html(app_path):
	write_record(
		app_path,
		"print_format",
		"payment_receipt",
		{"doctype": "Print Format", "doc_type": "Payment Entry", "standard": "Yes", "html": "<p></p>"},
		html="<p>\n{{ doc.party_balance }}</p>",
	)
	assert [(finding.file, finding.line) for finding in scan(app_path).findings] == [
		("digest/accounts/print_format/payment_receipt/payment_receipt.html", 2)
	]


def test_disabled_print_format_is_not_read(app_path):
	write_record(
		app_path,
		"print_format",
		"payment_receipt",
		{
			"doctype": "Print Format",
			"doc_type": "Payment Entry",
			"custom_format": 1,
			"disabled": 1,
			"html": "{{ doc.party_balance }}",
		},
	)
	assert scan(app_path).findings == []


def test_notification_subject_and_body_file_are_read(app_path):
	write_record(
		app_path,
		"notification",
		"payment_alert",
		{
			"doctype": "Notification",
			"document_type": "Payment Entry",
			"message_type": "HTML",
			"subject": "Balance {{ doc.party_balance }}",
		},
		html="<p>\n{{ doc.party_balance }}</p>",
	)
	assert sorted((finding.file, finding.line or 0) for finding in scan(app_path).findings) == [
		("digest/accounts/notification/payment_alert/payment_alert.html", 2),
		("digest/accounts/notification/payment_alert/payment_alert.json", 0),
	]


def test_disabled_notification_is_not_read(app_path):
	write_record(
		app_path,
		"notification",
		"payment_alert",
		{
			"doctype": "Notification",
			"document_type": "Payment Entry",
			"enabled": 0,
			"subject": "{{ doc.party_balance }}",
		},
	)
	assert scan(app_path).findings == []


def test_slack_notification_subject_is_not_read(app_path):
	write_record(
		app_path,
		"notification",
		"payment_alert",
		{
			"doctype": "Notification",
			"document_type": "Payment Entry",
			"channel": "Slack",
			"subject": "{{ doc.party_balance }}",
		},
	)
	assert scan(app_path).findings == []


@pytest.mark.parametrize("directory", ["templates", "www"])
def test_html_under_templates_and_www_keeps_its_line(app_path, directory):
	(app_path / directory).mkdir()
	(app_path / directory / "posts.html").write_text(
		'<p>\n{{ frappe.get_doc("Blog Post", name).title }}</p>', encoding="utf-8"
	)
	assert [(finding.file, finding.line) for finding in scan(app_path).findings] == [
		(f"digest/{directory}/posts.html", 2)
	]


def test_html_under_templates_has_no_typed_doc(app_path):
	(app_path / "templates").mkdir()
	(app_path / "templates" / "payment.html").write_text("{{ doc.party_balance }}", encoding="utf-8")
	assert scan(app_path).findings == []


def test_skip_tests_leaves_out_templates_in_test_folders(app_path):
	(app_path / "templates" / "tests").mkdir(parents=True)
	(app_path / "templates" / "tests" / "posts.html").write_text(
		'{{ frappe.get_doc("Blog Post", name).title }}', encoding="utf-8"
	)
	assert scan(app_path, skip_tests=True).findings == []


def test_ignore_comment_in_a_template_suppresses_its_line(app_path):
	(app_path / "templates").mkdir()
	(app_path / "templates" / "posts.html").write_text(
		'{{ frappe.get_doc("Blog Post", name).title }} {# preflight: ignore[v16-removed-blog-doctypes] #}',
		encoding="utf-8",
	)
	report = scan(app_path)
	assert (report.findings, report.suppressed) == ([], 1)


def test_templates_that_do_not_parse_fold_into_one_not_checked_line(app_path):
	(app_path / "www").mkdir()
	for name in ("orders", "invoices"):
		(app_path / "www" / f"{name}.html").write_text("{% if %}", encoding="utf-8")
	report = scan(app_path)
	assert report.not_checked == [
		"digest: Jinja templates that do not parse (2), the fields they read not checked"
	]
	assert report.unparsable_files == []
