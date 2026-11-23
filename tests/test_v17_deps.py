from pathlib import Path

import pytest

from preflight.compatibility_scanner import CompatibilityScanner
from preflight.js_scanner import JSScanner
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
RULES = load_rules("v17")

PYTHON_LINES = {
	"v17-pdfkit": [1],
	"v17-psycopg2": [2],
	"v17-mariadb-mysqlclient": [4],
	"v17-event-delete-communication": [5],
	"v17-install-fixtures-add-unsubscribe": [6],
	"v17-raise-error-on-no-output": [8],
	"v17-render-exec-config": [9],
	"v17-build-xlsx-data-visible-idx": [11, 12],
	"v17-build-xlsx-data-ignore-visible-idx": [13],
	"v17-erpnext-make-timesheet-ignore-permissions": [14, 15],
}
JS_LINES = {"v17-get-route-for-icon": [1], "v17-event-delete-communication": [2]}


def lines_by_rule(findings, rule_ids):
	lines = {}
	for finding in findings:
		if finding.rule.id in rule_ids:
			lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(found) for rule_id, found in lines.items()}


def pyproject(dependency):
	return f'[project]\nname = "digest"\ndependencies = ["{dependency}"]\n'


def test_python_violations_report_on_their_lines():
	source = (FIXTURES / "violations_v17_deps.py").read_text()
	assert lines_by_rule(PythonScanner(RULES).scan(source, "app.py"), PYTHON_LINES) == PYTHON_LINES


def test_js_violations_report_on_their_lines():
	source = (FIXTURES / "violations_v17_deps.js").read_text()
	assert lines_by_rule(JSScanner(RULES).scan(source, "app.js"), JS_LINES) == JS_LINES


@pytest.mark.parametrize(
	("rule_id", "source"),
	(
		("v17-pdfkit", "import pdfplumber\n"),
		("v17-psycopg2", "import psycopg\n"),
		("v17-mariadb-mysqlclient", "from frappe.database.mariadb.database import MariaDBDatabase\n"),
		("v17-event-delete-communication", "from frappe.desk.doctype.event.event import get_events\n"),
		(
			"v17-install-fixtures-add-unsubscribe",
			"from frappe.desk.page.setup_wizard.install_fixtures import update_salutations\n",
		),
		("v17-raise-error-on-no-output", "from frappe.utils.error import log_error\n"),
		("v17-render-exec-config", "from frappe.utils.safe_exec import get_safe_globals\n"),
		(
			"v17-build-xlsx-data-visible-idx",
			"from frappe.desk.query_report import build_xlsx_data\nbuild_xlsx_data(data, include_indentation=1)\n",
		),
		(
			"v17-build-xlsx-data-ignore-visible-idx",
			"from frappe.desk.query_report import build_xlsx_data\nbuild_xlsx_data(data, include_filters=1)\n",
		),
		(
			"v17-erpnext-make-timesheet-ignore-permissions",
			'from erpnext.projects.doctype.task.task import make_timesheet\nmake_timesheet("TASK-2026-00001")\n',
		),
	),
)
def test_python_near_miss_is_not_reported(rule_id, source):
	assert lines_by_rule(PythonScanner(RULES).scan(source, "app.py"), {rule_id}) == {}


def test_route_helper_that_stays_is_not_reported():
	findings = JSScanner(RULES).scan("frappe.utils.generate_route(item);\n", "app.js")
	assert lines_by_rule(findings, {"v17-get-route-for-icon"}) == {}


def test_pin_outside_frappe_develop_is_reported():
	findings = CompatibilityScanner(RULES).scan_pyproject(
		pyproject("python-barcode~=0.15.1"), "pyproject.toml"
	)
	assert "v17-app-dependency-pins" in {finding.rule.id for finding in findings}


def test_pin_frappe_develop_accepts_is_not_reported():
	findings = CompatibilityScanner(RULES).scan_pyproject(
		pyproject("python-barcode~=0.16.1"), "pyproject.toml"
	)
	assert "v17-app-dependency-pins" not in {finding.rule.id for finding in findings}
