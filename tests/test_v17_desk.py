from pathlib import Path

import pytest

from preflight.js_scanner import JSScanner
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
RULES = load_rules("v17")

JS_LINES = {
	"v17-datepicker-jquery-plugin": [1, 2, 3],
	"v17-datepicker-options": [4, 5, 6, 7, 8, 9, 10],
	"v17-datepicker-instance-api": [11, 12, 13, 14, 15, 16, 17],
	"v17-datepicker-update-change-event": [18],
	"v17-datepicker-css-classes": [19, 20, 21],
	"v17-guest-methods-post-only": [22, 23],
	"v17-desk-methods-post-only": [24, 25],
	"v17-guest-methods-get-only": [26, 27],
}


def lines_by_rule(source):
	lines = {}
	for finding in JSScanner(RULES).scan(source, "app.js"):
		if finding.rule.id in JS_LINES:
			lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(found) for rule_id, found in lines.items()}


def test_js_violations_report_on_their_lines():
	assert lines_by_rule((FIXTURES / "violations_v17_desk.js").read_text()) == JS_LINES


@pytest.mark.parametrize(
	("rule_id", "line"),
	[
		("v17-datepicker-jquery-plugin", "this.$refs.datepicker(value);"),
		("v17-datepicker-options", 'const options = { language: "de", position: "top", clearButton: true };'),
		("v17-datepicker-instance-api", "field.datepicker.unselectDate(date);"),
		("v17-datepicker-instance-api", 'positioned_datepicker?.$datepicker.classList.contains("-active-");'),
		(
			"v17-datepicker-update-change-event",
			"dialog.fields_dict.to_date.datepicker.update({ maxDate: today });",
		),
		("v17-datepicker-css-classes", '$(".air-datepicker--pointer, .datepicker").addClass("-active-");'),
		("v17-guest-methods-post-only", 'frappe.call({ method: "frappe.core.doctype.user.user.sign_up" });'),
		(
			"v17-desk-methods-post-only",
			'frappe.call({ method: "frappe.core.doctype.error_log.error_log.clear_error_logs" });',
		),
		(
			"v17-guest-methods-get-only",
			'frappe.call({ method: "frappe.email.queue.unsubscribe", type: "GET" });',
		),
	],
)
def test_code_that_still_works_is_not_reported(rule_id, line):
	assert rule_id not in lines_by_rule(line)
