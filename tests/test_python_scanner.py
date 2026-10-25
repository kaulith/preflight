import ast
from pathlib import Path

import pytest

from preflight.models import Match, Rule
from preflight.python_scanner import PythonScanner, call_uses_argument
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"

scanner = PythonScanner(load_rules("v16"))


def call_node(source):
	return ast.parse(source).body[0].value


def lines_by_rule(source):
	lines = {}
	for finding in scanner.scan(source, "fixture.py"):
		lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(rule_lines) for rule_id, rule_lines in lines.items()}


def lines_matched(match, source, **scan_arguments):
	rule = Rule(
		id="digest-rule",
		title="Digest rule",
		severity="error",
		match=match,
		message="Digest rule.",
		replacement="None.",
		references=(),
	)
	return sorted(
		finding.line for finding in PythonScanner([rule]).scan(source, "fixture.py", **scan_arguments)
	)


PRIVATE_REQUEST = Match(type="call", paths=("frappe.make_get_request",), url_host="private")
DUE_DATE = Match(type="doctype_field", fields=("Sales Invoice.due_date",))
PARTY_BALANCE = Match(type="doctype_field", fields=("Payment Entry.party_balance",))
BUILD_XLSX_DATA = Match(type="call", paths=("frappe.desk.query_report.build_xlsx_data",), returns=3)


def test_violations_are_reported_on_their_lines():
	assert lines_by_rule((FIXTURES / "violations.py").read_text()) == {
		"v16-build-xlsx-data-applied-filters": [149],
		"v16-build-xlsx-data-returns-three": [148, 149],
		"v16-deprecated-client-get-js": [43],
		"v16-deprecated-country-info-get-translated-dict": [6],
		"v16-deprecated-email-queue-send-mail": [4],
		"v16-deprecated-frappe-test-case": [10],
		"v16-deprecated-get-number-format-info": [12],
		"v16-deprecated-get-test-records": [19],
		"v16-deprecated-gravatar-helpers": [11],
		"v16-deprecated-gzip-helpers": [11, 56],
		"v16-deprecated-make-esc": [11, 27],
		"v16-deprecated-read-multi-pdf": [13],
		"v16-deprecated-show-progress": [63],
		"v16-deprecated-test-runner": [20],
		"v16-deprecated-tests-system-settings": [61, 73],
		"v16-deprecated-tests-utils-helpers": [62],
		"v16-has-permission-raise-exception": [25, 26],
		"v16-make-xlsx-workbook": [112],
		"v16-moved-desk-permission-helpers": [106],
		"v16-moved-frappe-config-helpers": [87],
		"v16-removed-backup-doctypes": [50, 121],
		"v16-removed-backup-integrations": [7, 55],
		"v16-removed-bleach": [139],
		"v16-removed-blog": [14],
		"v16-removed-blog-doctypes": [48, 118],
		"v16-removed-boto3": [140],
		"v16-removed-botocore": [157],
		"v16-removed-cairocffi": [141],
		"v16-removed-changelog-feed": [107],
		"v16-removed-changelog-feed-doctypes": [110],
		"v16-removed-dropbox": [143],
		"v16-removed-energy-point-doctypes": [49, 119],
		"v16-removed-energy-points": [9],
		"v16-removed-geolite2": [146],
		"v16-removed-get-excel-date-format": [108],
		"v16-removed-maxminddb": [156, 160],
		"v16-removed-newsletter": [5, 24],
		"v16-removed-newsletter-doctypes": [47, 120],
		"v16-removed-pkg-resources": [129],
		"v16-removed-posthog": [142],
		"v16-removed-python-stdlib": [127, 134],
		"v16-removed-rq-connection-helpers": [132],
		"v16-removed-s3transfer": [158],
		"v16-removed-test-runner-helpers": [145],
		"v16-removed-transaction-log": [2],
		"v16-removed-transaction-log-doctypes": [51, 117],
		"v16-removed-user-get-roles": [111],
		"v16-removed-user-get-roles-import": [111, 130],
		"v16-removed-workspace-sidebar-items-import": [131],
		"v16-renamed-is-column-missing": [36],
		"v16-sanitize-html-strips-tags": [28],
		"v16-server-script-private-request": [150],
		"v16-sql-function-string-fields": [122],
		"v16-value-cache-nested": [31],
	}


def test_v17_violations_are_reported_on_their_lines():
	findings = PythonScanner(load_rules("v17")).scan((FIXTURES / "violations.py").read_text(), "fixture.py")
	lines = {}
	for finding in findings:
		lines.setdefault(finding.rule.id, []).append(finding.line)
	assert lines == {
		"v17-deprecated-client-get-js": [43],
		"v17-deprecated-country-info-get-translated-dict": [6],
		"v17-deprecated-email-queue-send-mail": [4],
		"v17-deprecated-enqueue-job-name": [82],
		"v17-deprecated-frappe-test-case": [10],
		"v17-deprecated-get-number-format-info": [12],
		"v17-deprecated-get-test-records": [19],
		"v17-deprecated-gravatar-helpers": [11],
		"v17-deprecated-gzip-helpers": [11, 56],
		"v17-deprecated-install-fixtures-underscore": [71],
		"v17-deprecated-is-column-missing": [36],
		"v17-deprecated-make-esc": [11, 27],
		"v17-deprecated-query-limit-page-length": [83],
		"v17-deprecated-query-limit-start": [83],
		"v17-deprecated-query-page-length": [100],
		"v17-deprecated-query-start": [100],
		"v17-deprecated-read-multi-pdf": [13],
		"v17-deprecated-sendmail-retry": [97],
		"v17-deprecated-show-progress": [63],
		"v17-deprecated-tests-system-settings": [61, 73],
		"v17-deprecated-tests-utils-helpers": [62],
		"v17-deprecated-verify-password": [101],
		"v17-moved-chromium-pdf-generator": [74],
		"v17-moved-doctype-layout": [70],
		"v17-moved-max-password-size": [93],
		"v17-removed-get-pdf-smart-shrinking": [98],
		"v17-removed-sidebar-item-group-doctypes": [77],
		"v17-removed-slack-webhook-url": [94],
		"v17-removed-weasyprint": [75],
		"v17-removed-weasyprint-download-pdf": [99],
		"v17-removed-whoosh-search": [72],
		"v17-removed-wkhtmltopdf-helpers": [95],
	}


def test_v17_clean_file_has_no_findings():
	assert PythonScanner(load_rules("v17")).scan((FIXTURES / "clean.py").read_text(), "clean.py") == []


def test_removed_argument_is_caught_when_passed_positionally():
	source = 'frappe.permissions.has_permission("ToDo", "read", doc, user, False)\n'
	assert lines_by_rule(source) == {"v16-has-permission-raise-exception": [1]}


def test_call_below_the_positional_count_is_not_reported():
	assert lines_by_rule('frappe.permissions.has_permission("ToDo", "read", doc, user)\n') == {}


def test_a_rule_narrowed_to_a_positional_count_ignores_a_shorter_call():
	match = Match(type="call", paths=("frappe.permissions.has_permission",), with_positional_args=5)
	assert not call_uses_argument(call_node('has_permission("ToDo", "read", doc)'), match)


def test_a_rule_narrowed_to_no_argument_matches_every_call():
	match = Match(type="call", paths=("frappe.utils.make_esc",))
	assert call_uses_argument(call_node("make_esc()"), match)


def test_dotted_path_inside_a_string_is_reported():
	source = 'frappe.enqueue("frappe.client.get_js", items=items)\n'
	assert lines_by_rule(source) == {"v16-deprecated-client-get-js": [1]}


def test_path_resolved_from_a_string_is_reported():
	assert lines_by_rule('frappe.get_attr("frappe.utils.gzip_compress")(payload)\n') == {
		"v16-deprecated-gzip-helpers": [1]
	}


def test_path_under_a_removed_module_is_reported_from_the_method_keyword():
	source = 'frappe.enqueue(method="frappe.social.doctype.energy_point_log.energy_point_log.review")\n'
	assert lines_by_rule(source) == {"v16-removed-energy-points": [1]}


def test_path_in_a_string_no_api_resolves_is_not_reported():
	assert lines_by_rule('label = "frappe.utils.gzip_compress"\n') == {}


def test_endpoint_named_in_a_docstring_is_not_reported():
	assert lines_by_rule('def get_js():\n\t"""Stands in for frappe.client.get_js."""\n') == {}


def test_path_that_only_shares_a_prefix_is_not_reported():
	assert lines_by_rule('frappe.get_attr("frappe.utils.gzip_compression")\n') == {}


def test_dotted_path_outside_a_string_is_not_reported():
	assert lines_by_rule("value = frappe.client.get_value(doctype, name)\n") == {}


def test_removed_doctype_is_reported_where_an_api_reads_it():
	assert lines_by_rule('rows = frappe.get_all("Blog Post", pluck="name")\n') == {
		"v16-removed-blog-doctypes": [1]
	}


def test_removed_doctype_named_outside_an_api_is_not_reported():
	assert lines_by_rule('frappe.msgprint("Blog Post is gone")\n') == {}


def test_doctype_built_at_runtime_is_not_reported():
	assert lines_by_rule('frappe.get_all(doctype, filters={"name": "Blog Post"})\n') == {}


@pytest.mark.parametrize("fixture", ["clean.py", "clean_erpnext.py"])
def test_clean_file_has_no_findings(fixture):
	assert scanner.scan((FIXTURES / fixture).read_text(), fixture) == []


def test_module_alias_is_resolved():
	source = "import frappe.utils as frappe_utils\n\nfrappe_utils.gzip_decompress(payload)\n"
	assert lines_by_rule(source) == {"v16-deprecated-gzip-helpers": [3]}


def test_multiline_import_reports_the_imported_name_line():
	source = "from frappe.utils import (\n\tcint,\n\tmake_esc,\n)\n"
	assert lines_by_rule(source) == {"v16-deprecated-make-esc": [3]}


def test_relative_import_is_ignored():
	assert lines_by_rule("from .utils import make_esc\n") == {}


def test_call_inside_an_import_guard_is_reported():
	source = "try:\n\tfrappe.utils.make_esc('$')\nexcept ImportError:\n\tpass\n"
	assert lines_by_rule(source) == {"v16-deprecated-make-esc": [2]}


def test_import_under_a_try_catching_another_error_is_reported():
	source = "try:\n\tfrom frappe.utils import make_esc\nexcept KeyError:\n\tmake_esc = None\n"
	assert lines_by_rule(source) == {"v16-deprecated-make-esc": [2]}


def test_finding_carries_file_and_snippet():
	(finding,) = scanner.scan("\nfrappe.utils.make_esc('$')\n", "custom_app/utils.py")
	assert (finding.file, finding.line) == ("custom_app/utils.py", 2)
	assert finding.snippet == "frappe.utils.make_esc('$')"


def test_invalid_python_raises_syntax_error():
	with pytest.raises(SyntaxError):
		scanner.scan("def send_digest(:\n", "broken.py")


@pytest.mark.parametrize(
	"build",
	[
		'\tfields = ["item_code", "sum(actual_qty) as qty"]\n',
		'\tfields = ["item_code"]\n\tfields.append("sum(actual_qty) as qty")\n',
		'\tfields = ["item_code"]\n\tfields += ["sum(actual_qty) as qty"]\n',
		'\tfields = ["item_code"]\n\tfields.extend(["sum(actual_qty) as qty"])\n',
	],
)
def test_fields_built_in_a_local_name_are_checked(build):
	source = "def stock():\n" + build + '\treturn frappe.get_all("Bin", fields=fields)\n'
	assert lines_by_rule(source) == {"v16-sql-function-string-fields": [1 + build.count("\n")]}


def test_fields_built_in_both_branches_of_an_if_are_checked():
	source = (
		"def balances(payable):\n"
		"\tif payable:\n"
		'\t\tfields = ["party", "sum(credit - debit) as balance"]\n'
		"\telse:\n"
		'\t\tfields = ["party", "sum(debit - credit) as balance"]\n'
		'\treturn frappe.get_all("GL Entry", fields=fields)\n'
	)
	assert lines_by_rule(source) == {"v16-sql-function-string-fields": [3, 5]}


def test_fields_a_name_holds_in_another_scope_are_not_checked():
	source = 'fields = ["sum(actual_qty) as qty"]\n\n\ndef stock():\n\treturn frappe.get_all("Bin", fields=fields)\n'
	assert lines_by_rule(source) == {}


def test_f_string_field_with_a_function_around_its_substitution_is_reported():
	source = 'frappe.get_all("Bin", fields=[f"sum({field}) as total"])\n'
	assert lines_by_rule(source) == {"v16-sql-function-string-fields": [1]}


def test_f_string_field_that_is_only_its_substitution_and_an_alias_is_not_reported():
	assert lines_by_rule('frappe.get_all("Bin", fields=[f"{field} as total"])\n') == {}


def test_plucked_field_is_checked_when_no_fields_are_passed():
	source = 'frappe.get_all("Bin", pluck="sum(actual_qty)")\n'
	assert lines_by_rule(source) == {"v16-sql-function-string-fields": [1]}


def test_plucked_field_is_not_checked_beside_fields():
	assert lines_by_rule('frappe.get_all("Bin", fields=["actual_qty"], pluck="sum(actual_qty)")\n') == {}


def test_fields_passed_after_filters_in_their_place_are_checked():
	source = 'frappe.get_all("Bin", {"warehouse": warehouse}, ["sum(actual_qty) as qty"])\n'
	assert lines_by_rule(source) == {"v16-sql-function-string-fields": [1]}


@pytest.mark.parametrize(
	"test",
	[
		'is_frappe_version("15")',
		'frappe.__version__.startswith("15")',
		'int(frappe.__version__.split(".")[0]) < 16',
		'FRAPPE_VERSION.startswith("15")',
	],
)
def test_code_under_a_frappe_version_test_is_not_reported(test):
	source = (
		"FRAPPE_VERSION = frappe.__version__\n\n\n"
		f"def modules():\n\tif {test}:\n\t\treturn frappe.config.get_modules_from_all_apps_for_user()\n"
	)
	assert lines_by_rule(source) == {}


def test_every_branch_of_a_frappe_version_test_is_not_reported():
	source = (
		'if is_frappe_version("16", above=True):\n'
		"\tmodules = get_modules_from_all_apps_for_user()\n"
		"else:\n"
		"\tmodules = frappe.config.get_modules_from_all_apps_for_user()\n"
	)
	assert lines_by_rule(source) == {}


def test_frappe_version_ternary_is_not_reported():
	source = 'escape = frappe.utils.escape_html if is_frappe_version("16") else frappe.utils.make_esc("$")\n'
	assert lines_by_rule(source) == {}


def test_code_after_a_frappe_version_test_is_reported():
	source = 'if is_frappe_version("15"):\n\tpass\nfrappe.utils.make_esc("$")\n'
	assert lines_by_rule(source) == {"v16-deprecated-make-esc": [3]}


def test_fields_a_list_takes_under_a_frappe_version_test_are_not_checked():
	source = (
		"def stock():\n"
		'\tfields = ["item_code"]\n'
		'\tif is_frappe_version("15"):\n'
		'\t\tfields.append("sum(actual_qty) as qty")\n'
		'\treturn frappe.get_all("Bin", fields=fields)\n'
	)
	assert lines_by_rule(source) == {}


@pytest.mark.parametrize(
	"url",
	[
		'"http://localhost:8000/api/method/stock"',
		'"https://10.0.0.5/api/stock"',
		'url="http://[::1]/api/stock"',
		'f"http://169.254.169.254/latest/{path}"',
		'f"http://127.0.0.1:{port}/api/stock"',
	],
)
def test_request_to_a_private_host_is_reported(url):
	assert lines_matched(PRIVATE_REQUEST, f"frappe.make_get_request({url})\n") == [1]


@pytest.mark.parametrize(
	"url",
	[
		'"https://erp.example.com/api/stock"',
		'"https://8.8.8.8/api/stock"',
		'f"http://{host}/api/stock"',
		'f"http://10.0.0.{node}/api/stock"',
		"stock_url",
	],
)
def test_request_whose_host_is_public_or_unknown_is_not_reported(url):
	assert lines_matched(PRIVATE_REQUEST, f"frappe.make_get_request({url})\n") == []


@pytest.mark.parametrize(
	"call",
	[
		'frappe.get_all("Sales Invoice", fields=["name", "due_date as due"])',
		'frappe.get_all("Sales Invoice", fields="name, `tabSales Invoice`.`due_date`")',
		'frappe.get_all("Sales Invoice", filters={"due_date": ("<", today)})',
		'frappe.get_all("Sales Invoice", filters=[["due_date", "<", today]])',
		'frappe.get_all("Customer", filters=[["Sales Invoice", "due_date", "<", today]])',
		'frappe.get_all("Sales Invoice", {"due_date": today}, ["name"])',
		'frappe.get_all("Sales Invoice", order_by="due_date desc")',
		'frappe.get_all("Sales Invoice", pluck="due_date")',
		'frappe.db.get_value("Sales Invoice", name, "due_date")',
		'frappe.db.set_value("Sales Invoice", name, "due_date", today)',
		'frappe.db.set_value("Sales Invoice", name, {"due_date": today})',
	],
)
def test_field_named_beside_its_doctype_is_reported(call):
	assert lines_matched(DUE_DATE, f"{call}\n") == [1]


@pytest.mark.parametrize(
	"call",
	[
		'frappe.get_all(doctype, fields=["due_date"])',
		'frappe.get_all("Purchase Invoice", fields=["due_date"])',
		'frappe.get_all("Sales Invoice", fields=["max(due_date) as due"])',
		'frappe.get_all("Sales Invoice", filters={"status": "due_date"})',
	],
)
def test_field_not_named_beside_its_doctype_is_not_reported(call):
	assert lines_matched(DUE_DATE, f"{call}\n") == []


@pytest.mark.parametrize(
	"source",
	[
		'payment = frappe.get_doc("Payment Entry", name)\nbalance = payment.party_balance\n',
		'payment = frappe.new_doc("Payment Entry")\npayment.party_balance = balance\n',
		'payment = frappe.get_doc({"doctype": "Payment Entry", "party": party})\nbalance = payment.party_balance\n',
		'payment = frappe.get_doc("Payment Entry", name)\nbalance = payment.get("party_balance")\n',
		'payment: Document = frappe.get_doc("Payment Entry", name)\nbalance = payment.party_balance\n',
	],
)
def test_field_of_the_doc_a_name_holds_is_reported(source):
	assert lines_matched(PARTY_BALANCE, source) == [2]


def test_field_of_a_doc_read_as_it_is_loaded_is_reported():
	assert lines_matched(
		PARTY_BALANCE, 'balance = frappe.get_doc("Payment Entry", name).party_balance\n'
	) == [1]


def test_field_of_a_name_bound_again_is_not_reported():
	source = (
		'payment = frappe.get_doc("Payment Entry", name)\n'
		"payment = payment.as_dict()\n"
		"balance = payment.party_balance\n"
	)
	assert lines_matched(PARTY_BALANCE, source) == []


def test_doc_a_name_holds_in_another_scope_is_not_matched():
	source = (
		'payment = frappe.get_doc("Payment Entry", name)\n\n\n'
		"def balance(payment):\n\treturn payment.party_balance\n"
	)
	assert lines_matched(PARTY_BALANCE, source) == []


def test_field_of_self_in_a_class_hooks_py_overrides_a_doctype_with_is_reported():
	source = "class DigestPaymentEntry(Document):\n\tdef validate(self):\n\t\tself.party_balance = 0\n"
	assert lines_matched(PARTY_BALANCE, source, hooked={"DigestPaymentEntry": {"Payment Entry"}}) == [3]


def test_field_of_self_in_a_class_built_on_a_doctype_controller_is_reported():
	source = (
		"from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry\n\n\n"
		"class DigestPaymentEntry(PaymentEntry):\n\tdef validate(self):\n\t\tself.party_balance = 0\n"
	)
	assert lines_matched(PARTY_BALANCE, source) == [6]


def test_field_of_self_in_a_class_built_on_another_class_is_not_reported():
	source = (
		"from erpnext.controllers.accounts_controller import AccountsController\n\n\n"
		"class DigestPaymentEntry(AccountsController):\n\tdef validate(self):\n\t\tself.party_balance = 0\n"
	)
	assert lines_matched(PARTY_BALANCE, source) == []


@pytest.mark.parametrize(
	"assignment",
	[
		"rows, widths = build_xlsx_data(data, [], 1)[:2]",
		"rows = build_xlsx_data(data, [], 1)[0]",
		"rows, widths, styles = build_xlsx_data(data, [], 1)",
		"rows, widths, *_ = build_xlsx_data(data, [], 1)",
	],
)
def test_call_whose_result_is_taken_as_it_returns_it_is_not_reported(assignment):
	source = f"from frappe.desk.query_report import build_xlsx_data\n\n{assignment}\n"
	assert lines_matched(BUILD_XLSX_DATA, source) == []


@pytest.mark.parametrize(
	"assignment",
	["rows, widths = build_xlsx_data(data, [], 1)", 'report["rows"] = build_xlsx_data(data, [], 1)'],
)
def test_call_whose_result_is_not_taken_as_it_returns_it_is_reported(assignment):
	source = f"from frappe.desk.query_report import build_xlsx_data\n\n{assignment}\n"
	assert lines_matched(BUILD_XLSX_DATA, source) == [3]


def test_undeclared_import_is_matched_like_an_import_path():
	match = Match(type="undeclared_import", paths=("bleach",), dependencies=("bleach",))
	assert lines_matched(match, "import bleach\n\nbleach.clean(html)\n") == [1, 3]


def test_undeclared_import_under_an_import_guard_is_not_reported():
	match = Match(type="undeclared_import", paths=("bleach",), dependencies=("bleach",))
	assert lines_matched(match, "try:\n\timport bleach\nexcept ImportError:\n\tbleach = None\n") == []
