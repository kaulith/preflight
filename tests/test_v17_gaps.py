import json
from pathlib import Path

import pytest

from preflight.app_scan import Scanners, scan_app
from preflight.jinja_scanner import JinjaScanner
from preflight.models import Report
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import RuleError, load_rule, load_rules

FIXTURES = Path(__file__).parent / "fixtures"
EXEC_GLOBALS = "v17-template-exec-globals"
FETCHED_DOC = "v17-template-fetched-doc"
CTE = "v17-safe-sql-cte"
OUTFILE = "v17-safe-sql-outfile-word"
EXPLAIN = "v17-safe-sql-explain-analyze"
NESTEDSET = "v17-nestedset-after-insert"
RULE_IDS = {EXEC_GLOBALS, FETCHED_DOC, CTE, OUTFILE, EXPLAIN, NESTEDSET}

RULES = [rule for rule in load_rules("v17") if rule.id in RULE_IDS]
jinja = JinjaScanner(RULES)
python = PythonScanner(RULES)


def template_rules(source, **kwargs):
	return {finding.rule.id for finding in jinja.scan(source, "fixture.html", **kwargs)}


def python_rules(source, **kwargs):
	return {finding.rule.id for finding in python.scan(source, "fixture.py", **kwargs)}


def test_template_rules_report_their_lines():
	source = (FIXTURES / "violations_v17_gaps.html").read_text()
	findings = jinja.scan(source, "violations_v17_gaps.html")
	assert {finding.rule.id: finding.line for finding in findings} == {
		EXEC_GLOBALS: 1,
		FETCHED_DOC: 3,
		CTE: 4,
		OUTFILE: 5,
		EXPLAIN: 6,
	}


def test_nestedset_rule_reports_its_line():
	source = (FIXTURES / "violations_v17_gaps.py").read_text()
	findings = python.scan(source, "violations_v17_gaps.py")
	assert {finding.rule.id: finding.line for finding in findings} == {NESTEDSET: 6}


@pytest.mark.parametrize(
	"source",
	(
		"{{ frappe.db.get_value('ToDo', name, 'status') }}",
		"{{ frappe.format_date(doc.posting_date) }}",
		"{% if frappe.sendmail %}{% endif %}",
		"{% set frappe = helpers %}{{ frappe.sendmail() }}",
		"{% macro run_script() %}{% endmacro %}{{ run_script() }}",
		"{% from 'macros.html' import run_script %}{{ run_script() }}",
		"<script>frappe.call({method: 'ping'})</script>",
	),
)
def test_template_global_near_misses(source):
	assert EXEC_GLOBALS not in template_rules(source)


@pytest.mark.parametrize(
	"source",
	(
		"{% for row in doc.items %}{{ row.qty }}{% endfor %}",
		"{{ doc.get_formatted('total') }}{{ doc.get_url() }}",
		"{% set order = frappe.get_doc('Sales Order', name) %}{% for row in order.get('items') %}{% endfor %}",
		"{% set order = frappe.get_doc('Sales Order', name) %}{{ order['items'] }}{{ order.customer }}",
		"{% set order = frappe.get_doc('Sales Order', name) %}{% for key, value in order.items() %}{% endfor %}",
		"{% set order = frappe.get_cached_doc('Company', name) %}{{ order.get_formatted('credit_limit') }}",
		"{% set frappe = helpers %}{{ frappe.get_doc('Sales Order', name).items }}",
	),
)
def test_fetched_doc_near_misses(source):
	assert FETCHED_DOC not in template_rules(source)


@pytest.mark.parametrize(
	"source",
	(
		"{{ frappe.get_doc('Sales Order', name).items }}",
		"{{ frappe.get_last_doc('Sales Order').get_url() }}",
		"{% if draft %}{% set order = frappe.get_cached_doc('Sales Order', name) %}{% endif %}{{ order.values }}",
		"{% with order = frappe.get_doc(doctype, name) %}{{ order.as_dict() }}{% endwith %}",
	),
)
def test_fetched_doc_reads_that_break(source):
	assert FETCHED_DOC in template_rules(source)


def test_restricted_template_keeps_only_the_sql_rules():
	source = "{{ frappe.sendmail() }}{{ frappe.get_doc('ToDo', name).items }}{{ frappe.db.sql('with a as (select 1) select * from a') }}"
	assert template_rules(source, restricted=True) == {CTE}


@pytest.mark.parametrize(
	"query, rule_id",
	(
		("  WITH totals AS (select 1) select * from totals", CTE),
		("select 'dumpfile' as note", OUTFILE),
		("EXPLAIN (costs off, analyse true) select 1", EXPLAIN),
	),
)
def test_sql_rules_read_only_sql_that_passes_the_guard(query, rule_id):
	source = f"import frappe\nfrappe.db.sql({query!r})\n"
	assert python_rules(source) == set()
	assert python_rules(source, safe_sql=True) == {rule_id}
	assert {finding.rule.id for finding in python.scan_sql(query, "report.json")} == {rule_id}


@pytest.mark.parametrize(
	"query",
	(
		"select name from tabToDo",
		"explain select name from tabToDo",
		"select 1 into outfile '/tmp/report.csv'",
		"with totals as (select 1) select * from totals into dumpfile '/tmp/report.csv'",
		"explain analyze select password from __Auth",
		"update tabToDo set description = 'outfile'",
	),
)
def test_sql_v16_already_rejects_or_v17_accepts(query):
	assert not {finding.rule.id for finding in python.scan_sql(query, "report.json")}


def test_multisql_never_reaches_the_guard():
	source = 'import frappe\nfrappe.db.multisql({"mariadb": "with a as (select 1) select * from a"})\n'
	assert python_rules(source, safe_sql=True) == set()


@pytest.mark.parametrize(
	"source",
	(
		"from frappe.model.document import Document\nclass Note(Document):\n\tdef after_insert(self):\n\t\tsuper().after_insert()\n",
		"from frappe.utils.nestedset import NestedSet\nclass Territory(NestedSet, Audited):\n\tdef after_insert(self):\n\t\tsuper().after_insert()\n",
		"from frappe.utils.nestedset import NestedSet\nclass Territory(NestedSet):\n\tdef on_update(self):\n\t\tsuper().on_update()\n",
		'from frappe.utils.nestedset import NestedSet\nclass Territory(NestedSet):\n\tdef after_insert(self):\n\t\tafter_insert = getattr(super(), "after_insert", None)\n\t\tif after_insert:\n\t\t\tafter_insert()\n',
		"from frappe.utils.nestedset import NestedSet\nclass Territory(NestedSet):\n\tclass Inner(Base):\n\t\tdef after_insert(self):\n\t\t\tsuper().after_insert()\n",
	),
)
def test_nestedset_near_misses(source):
	assert python_rules(source) == set()


@pytest.mark.parametrize(
	"call",
	("super(Territory, self).after_insert()", "NestedSet.after_insert(self)"),
)
def test_nestedset_call_forms(call):
	source = f"from frappe.utils.nestedset import NestedSet\nclass Territory(NestedSet):\n\tdef after_insert(self):\n\t\t{call}\n"
	assert python_rules(source) == {NESTEDSET}


def test_aliased_nestedset_base():
	source = "from frappe.utils import nestedset as tree\nclass Territory(tree.NestedSet):\n\tdef after_insert(self):\n\t\tsuper().after_insert()\n"
	assert python_rules(source) == {NESTEDSET}


@pytest.fixture
def app_path(tmp_path):
	path = tmp_path / "digest" / "digest"
	path.mkdir(parents=True)
	(path / "hooks.py").write_text('app_name = "digest"\n', encoding="utf-8")
	return path


def write(path, text):
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(text, encoding="utf-8")


def scan(app_path, rules=RULES):
	report = Report(site=None, target="v17", apps=["digest"])
	scan_app(report, Scanners(rules), "digest", app_path)
	return report


def test_app_surfaces_that_flip_are_reported(app_path):
	call = "{{ frappe.sendmail() }}"
	write(app_path / "www" / "welcome.html", call)
	write(app_path / "templates" / "emails" / "digest.html", call)
	write(app_path / "website" / "web_template" / "banner" / "banner.html", call)
	write(app_path / "website" / "doctype" / "article" / "templates" / "article.html", call)
	write(
		app_path / "accounts" / "letter_head" / "branch" / "branch.json",
		json.dumps({"doctype": "Letter Head", "content": call, "footer": call}),
	)
	write(
		app_path / "accounts" / "print_format" / "invoice" / "invoice.json",
		json.dumps(
			{"doctype": "Print Format", "custom_format": 1, "html": call, "doc_type": "Sales Invoice"}
		),
	)
	report = scan(app_path)
	assert {finding.file for finding in report.findings if finding.rule.id == EXEC_GLOBALS} == {
		"digest/www/welcome.html",
		"digest/templates/emails/digest.html",
		"digest/website/web_template/banner/banner.html",
		"digest/website/doctype/article/templates/article.html",
		"digest/accounts/letter_head/branch/branch.json",
		"digest/accounts/print_format/invoice/invoice.json",
	}


def test_app_notification_is_not_reported(app_path):
	record = {"doctype": "Notification", "subject": "{{ frappe.sendmail() }}", "document_type": "ToDo"}
	write(app_path / "desk" / "notification" / "reminder" / "reminder.json", json.dumps(record))
	write(app_path / "desk" / "notification" / "reminder" / "reminder.md", "{{ frappe.db.commit() }}")
	assert scan(app_path).findings == []


def test_a_broken_letter_head_is_listed_and_the_scan_goes_on(app_path):
	write(
		app_path / "accounts" / "letter_head" / "branch" / "branch.json",
		json.dumps({"doctype": "Letter Head", "content": ["not text"], "footer": "{{ frappe.sendmail() }}"}),
	)
	write(app_path / "www" / "broken.html", "{% if %}")
	report = scan(app_path)
	assert [finding.file for finding in report.findings] == ["digest/accounts/letter_head/branch/branch.json"]
	assert report.not_checked == [
		"digest: Jinja templates that do not parse (2), the fields they read not checked"
	]


def test_v16_rules_do_not_read_the_new_surfaces(app_path):
	write(
		app_path / "accounts" / "letter_head" / "branch" / "branch.json",
		json.dumps({"doctype": "Letter Head", "content": "{% if %}"}),
	)
	write(
		app_path / "website" / "web_template" / "banner" / "banner.html",
		"{{ frappe.get_doc('Blog Post', x) }}",
	)
	report = scan(app_path, load_rules("v16"))
	assert report.findings == [] and report.not_checked == []


@pytest.mark.parametrize("key", ("safe_sql_only", "super_calls"))
def test_a_flag_is_true_or_left_out(tmp_path, key):
	match_type = "sql_text" if key == "safe_sql_only" else "call"
	target = "patterns: ['x']" if key == "safe_sql_only" else "paths: [frappe.x]"
	path = tmp_path / "v17-flag.yaml"
	path.write_text(
		f"id: v17-flag\ntitle: t\nseverity: info\nmatch:\n  type: {match_type}\n  {target}\n  {key}: false\n"
		"message: m\nreplacement: r\nreferences: [x]\n"
	)
	with pytest.raises(RuleError, match="must be true"):
		load_rule(path)


def test_site_surfaces(monkeypatch):
	frappe = pytest.importorskip("frappe")
	from preflight.scan import scan_site_scripts, scan_site_templates

	call = "{{ frappe.sendmail() }}"
	rows = {
		"Print Format": [],
		"Notification": [
			frappe._dict(name="Reminder", document_type="ToDo", channel="Email", subject=call, message=call)
		],
		"Email Template": [
			frappe._dict(name="Welcome", subject=call, use_html=0, response="", response_html="")
		],
		"Letter Head": [frappe._dict(name="Head Office", content=call, footer="")],
		"Web Template": [frappe._dict(name="Banner", template=call)],
	}
	monkeypatch.setattr("preflight.scan.frappe.get_all", lambda doctype, **kwargs: rows[doctype])
	report = Report(site="test.localhost", target="v17", apps=[])
	scanners = Scanners(RULES)
	scan_site_templates(report, scanners.jinja, scanners.rendering)
	assert {finding.file for finding in report.findings} == {
		"Email Template: Welcome (subject)",
		"Letter Head: Head Office (content)",
		"Web Template: Banner (template)",
	}

	script = 'frappe.db.sql("with a as (select 1) select * from a")'
	monkeypatch.setattr(
		"preflight.scan.site_scripts", lambda: [("Server Script: Digest", "python", script, {})]
	)
	report = Report(site="test.localhost", target="v17", apps=[])
	scan_site_scripts(report, scanners)
	assert [finding.rule.id for finding in report.findings] == [CTE]
