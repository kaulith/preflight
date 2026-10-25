import pytest

frappe = pytest.importorskip("frappe")

from preflight.app_scan import Scanners
from preflight.models import Report
from preflight.rule_loader import load_rules
from preflight.scan import scan_site_scripts

RULES = load_rules("v16")

SERVER_SCRIPT = """blog_posts = frappe.get_test_records("Blog Post")
frappe.response["message"] = len(blog_posts)
"""

CLIENT_SCRIPT = """frappe.ui.form.on("Blog Post", {
	refresh(frm) {
		frm.dashboard.add_comment(frappe.energy_points.get_points(frm.doc.name));
	},
});
"""


@pytest.fixture
def seeded_scripts(site, require_doctypes):
	require_doctypes("Blog Post")
	try:
		server_script = frappe.get_doc(
			doctype="Server Script",
			name="Blog Post digest",
			script_type="API",
			api_method="blog_post_digest",
			script=SERVER_SCRIPT,
		).insert()
		client_script = frappe.get_doc(
			doctype="Client Script",
			name="Blog Post review",
			dt="Blog Post",
			view="Form",
			enabled=1,
			script=CLIENT_SCRIPT,
		).insert()
		report = frappe.get_doc(
			doctype="Report",
			report_name="Blog Post Engagement",
			ref_doctype="Blog Post",
			report_type="Script Report",
			is_standard="No",
			report_script=SERVER_SCRIPT,
			javascript=CLIENT_SCRIPT,
		).insert()
		yield server_script.name, client_script.name, report.name
	finally:
		frappe.db.rollback()


def scan(site: str) -> Report:
	report = Report(site=site, target="v16", apps=[])
	scan_site_scripts(report, Scanners(RULES))
	return report


def test_site_scripts_are_reported_under_their_name(site, seeded_scripts):
	server_script, client_script, report = seeded_scripts
	found = {(finding.rule.id, finding.file) for finding in scan(site).findings}
	assert ("v16-deprecated-get-test-records", f"Server Script: {server_script}") in found
	assert ("v16-removed-energy-points-js", f"Client Script: {client_script}") in found
	assert ("v16-deprecated-get-test-records", f"Report: {report} (report_script)") in found
	assert ("v16-removed-energy-points-js", f"Report: {report} (javascript)") in found


def test_disabled_scripts_are_not_reported(site, seeded_scripts):
	server_script, client_script, _ = seeded_scripts
	frappe.db.set_value("Server Script", server_script, "disabled", 1)
	frappe.db.set_value("Client Script", client_script, "enabled", 0)
	labels = {finding.file for finding in scan(site).findings}
	assert f"Server Script: {server_script}" not in labels
	assert f"Client Script: {client_script}" not in labels


@pytest.mark.parametrize(
	"script_type, fields, reported",
	[
		("DocType Event", {"doctype_event": "Before Save"}, True),
		("API", {"api_method": "payment_entry_balance"}, False),
	],
)
def test_field_of_the_doc_a_doctype_event_script_runs_with_is_reported(
	site, require_doctypes, script_type, fields, reported
):
	require_doctypes("Payment Entry")
	try:
		frappe.get_doc(
			doctype="Server Script",
			name="Payment Entry balance",
			script_type=script_type,
			reference_doctype="Payment Entry",
			script="doc.party_balance = 0\n",
			**fields,
		).insert()
		found = {(finding.rule.id, finding.file, finding.line) for finding in scan(site).findings}
		assert (
			("v16-erpnext-removed-fields", "Server Script: Payment Entry balance", 1) in found
		) == reported
	finally:
		frappe.db.rollback()


def test_field_of_the_doc_a_notification_condition_reads_is_reported(site, require_doctypes):
	require_doctypes("Lead")
	try:
		frappe.get_doc(
			doctype="Notification",
			name="Lead follow up",
			subject="Follow up with the lead",
			document_type="Lead",
			event="New",
			channel="Email",
			condition='doc.source == "Exhibition"',
		).insert()
		found = {(finding.rule.id, finding.file, finding.line) for finding in scan(site).findings}
		assert ("v16-erpnext-utm-fields", "Notification: Lead follow up", 1) in found
	finally:
		frappe.db.rollback()


def test_scan_issues_no_writes(site, seeded_scripts):
	writes = frappe.db.transaction_writes
	scan(site)
	assert frappe.db.transaction_writes == writes
