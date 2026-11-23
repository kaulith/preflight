from pathlib import Path

from preflight.js_scanner import JSScanner
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
RULE_IDS = {"v17-sanitize-html-allowlist", "v17-erpnext-grey-letterhead", "v17-guest-methods-no-put-delete"}
RULES = [rule for rule in load_rules("v17") if rule.id in RULE_IDS]


def lines_by_rule(findings):
	lines = {}
	for finding in findings:
		lines.setdefault(finding.rule.id, []).append(finding.line)
	return lines


def test_python_violations_report_on_their_lines():
	source = (FIXTURES / "violations_v17_extras.py").read_text()
	assert lines_by_rule(PythonScanner(RULES).scan(source, "app.py")) == {
		"v17-sanitize-html-allowlist": [5, 6],
		"v17-erpnext-grey-letterhead": [7],
	}


def test_put_is_reported():
	source = (FIXTURES / "violations_v17_extras.js").read_text()
	assert lines_by_rule(JSScanner(RULES).scan(source, "app.js")) == {"v17-guest-methods-no-put-delete": [1]}


def test_reading_the_allowlist_and_the_kept_letter_head_are_not_reported():
	source = (
		"import frappe\n"
		"from frappe.utils.html_utils import acceptable_elements\n"
		'allowed = "marquee" in acceptable_elements\n'
		'frappe.get_doc("Letter Head", "Company Letterhead")\n'
	)
	assert PythonScanner(RULES).scan(source, "app.py") == []


def test_get_is_not_reported():
	assert JSScanner(RULES).scan('frappe.call({ method: "frappe.ping", type: "GET" });\n', "app.js") == []
