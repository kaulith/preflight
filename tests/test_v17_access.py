from pathlib import Path

import pytest

from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURE = Path(__file__).parent / "fixtures" / "violations_v17_access.py"
ACCESS_RULES = {
	"v17-erpnext-buying-show-pay-button",
	"v17-erpnext-get-bank-cash-account",
	"v17-erpnext-get-company-default",
	"v17-erpnext-outstanding-reference-documents",
	"v17-erpnext-plaid-link-token-update",
	"v17-erpnext-tax-rule-item-filters",
}
rules = [rule for rule in load_rules("v17") if rule.id in ACCESS_RULES]
scanner = PythonScanner(rules)


def lines_by_rule(source):
	lines = {}
	for finding in scanner.scan(source, "fixture.py"):
		lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(rule_lines) for rule_id, rule_lines in lines.items()}


def test_each_access_rule_reports_its_lines():
	assert lines_by_rule(FIXTURE.read_text()) == {
		"v17-erpnext-get-bank-cash-account": [7],
		"v17-erpnext-get-company-default": [8],
		"v17-erpnext-outstanding-reference-documents": [9],
		"v17-erpnext-plaid-link-token-update": [10],
		"v17-erpnext-tax-rule-item-filters": [11, 12],
		"v17-erpnext-buying-show-pay-button": [13],
	}


@pytest.mark.parametrize(
	"source",
	(
		(
			"from erpnext.accounts.doctype.payment_entry.payment_entry import get_bank_cash_account\n"
			"get_bank_cash_account(doc, 'Cash')"
		),
		(
			"from erpnext.accounts.doctype.sales_invoice.services.pos import get_bank_cash_account\n"
			"get_bank_cash_account('Cash', 'Northwind Traders')"
		),
		"doc.get_company_default('cost_center')",
		(
			"from erpnext.accounts.doctype.payment_entry.payment_entry import _get_outstanding_reference_documents\n"
			"_get_outstanding_reference_documents({})"
		),
		(
			"from erpnext.erpnext_integrations.doctype.plaid_settings.plaid_settings import update_bank_account_ids\n"
			"update_bank_account_ids('{}')"
		),
		"frappe.db.get_value('Tax Rule', 'Domestic Sales', 'tax_type')",
		"frappe.db.get_single_value('Buying Settings', 'maintain_same_rate')",
	),
)
def test_code_that_keeps_working_is_not_reported(source):
	assert lines_by_rule(source) == {}
