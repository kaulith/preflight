from pathlib import Path

import pytest

from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURE = Path(__file__).parent / "fixtures" / "violations_v17_templates.py"
RULE_LINES = {
	"v17-postgres-modify-values": 2,
	"v17-postgres-get-transaction-status": 4,
	"v17-postgres-set-isolation-level": 5,
	"v17-postgres-copy-expert": 6,
}

scanner = PythonScanner([rule for rule in load_rules("v17") if rule.id in RULE_LINES])


def test_each_rule_reports_its_line():
	findings = scanner.scan(FIXTURE.read_text(), FIXTURE.name)
	assert {finding.rule.id: finding.line for finding in findings} == RULE_LINES


@pytest.mark.parametrize(
	"source",
	(
		"from frappe.database.postgres.database import PostgresDatabase",
		"status = frappe.db._conn.info.transaction_status",
		'frappe.db.sql("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED")',
		'frappe.db._cursor.copy("COPY tabToDo TO STDOUT")',
	),
)
def test_replacement_is_not_reported(source):
	assert scanner.scan(f"import frappe\n{source}\n", "app.py") == []
