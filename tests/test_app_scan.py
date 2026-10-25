import subprocess
import sys
import types
from pathlib import Path

import pytest

from preflight.app_scan import (
	Scanners,
	add_findings,
	build_path_report,
	ignored_rules,
	scan_app,
	scan_patches,
	scan_python,
)
from preflight.models import Finding, Match, Report, Rule
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

ROOT = Path(__file__).parent.parent
RULES = load_rules("v16")
PATCHES = """[pre_model_sync]
digest.patches.v1_0.rename_digest_fields
execute:frappe.db.set_value("Blog Settings", None, "show_cta_in_blog", 1)

[post_model_sync]
"""
BLEACH = Rule(
	id="v16-undeclared-bleach",
	title="bleach no longer installed by frappe",
	severity="error",
	match=Match(type="undeclared_import", paths=("bleach",), dependencies=("bleach",)),
	message="frappe v16 stops installing bleach.",
	replacement="Declare bleach in the app's dependencies.",
	references=(),
)


@pytest.fixture
def app_path(tmp_path):
	"""The package of `digest`, inside its repository."""
	path = tmp_path / "digest" / "digest"
	path.mkdir(parents=True)
	(path / "hooks.py").write_text('app_name = "digest"\n', encoding="utf-8")
	return path


def test_path_mode_runs_without_frappe(app_path):
	code = (
		'import sys; sys.modules["frappe"] = None; from preflight.commands import preflight_command; '
		f'preflight_command(["--path", {str(app_path.parent)!r}, "--target", "v16"])'
	)
	result = subprocess.run(
		[sys.executable, "-c", code], check=False, cwd=ROOT, capture_output=True, text=True
	)
	assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
	"line, rule_ids",
	[
		(
			'frappe.db.get_value("Blog Post", name)  # preflight: ignore[v16-removed-blog-doctypes]',
			{"v16-removed-blog-doctypes"},
		),
		("frappe.energy_points.get_points(user); // preflight: ignore[a, b]", {"a", "b"}),
		("frappe.energy_points.get_points(user); /* preflight: ignore[a] */", {"a"}),
		('frappe.db.get_value("Blog Post", name)  # preflight: ignore', set()),
	],
)
def test_ignore_comments_name_the_rules_they_suppress(line, rule_ids):
	assert ignored_rules(line) == rule_ids


def test_a_suppressed_finding_is_counted_and_not_reported(app_path):
	(app_path / "api.py").write_text(
		'frappe.db.get_value("Blog Post", name)  # preflight: ignore[v16-removed-blog-doctypes]\n',
		encoding="utf-8",
	)
	report = Report(site=None, target="v16", apps=["digest"])
	scan_app(report, Scanners(RULES), "digest", app_path)
	assert (report.findings, report.suppressed) == ([], 1)


def test_frontend_files_outside_the_package_are_named_from_the_repository_root(app_path):
	(app_path.parent / "frontend" / "src").mkdir(parents=True)
	(app_path.parent / "frontend" / "src" / "points.js").write_text(
		"frappe.energy_points.get_points(user);\n", encoding="utf-8"
	)
	report = Report(site=None, target="v16", apps=["digest"])
	scan_app(report, Scanners(RULES), "digest", app_path)
	assert [(finding.app, finding.file) for finding in report.findings] == [
		("digest", "frontend/src/points.js")
	]


@pytest.mark.parametrize("declared, reported", [({"boto3"}, 1), ({"bleach"}, 0)])
def test_an_import_of_a_package_the_app_declares_is_no_finding(declared, reported):
	finding = Finding(rule=BLEACH, file="digest/utils.py", line=1, snippet="import bleach")
	report = Report(site=None, target="v16", apps=["digest"])
	add_findings(report, [finding], "import bleach\n", "digest", declared=declared)
	assert len(report.findings) == reported


def test_a_file_too_deep_to_compile_is_named_as_unreadable_under_its_app():
	report = Report(site=None, target="v16", apps=["digest"])
	source = "total = " + " + ".join(["amount"] * 200000)
	assert scan_python(report, PythonScanner(RULES), "digest/totals.py", source, "digest") is None
	assert report.unreadable_files[0].startswith("digest/digest/totals.py: ")


def test_execute_lines_in_patches_are_scanned_at_their_line(app_path):
	(app_path / "patches.txt").write_text(PATCHES, encoding="utf-8")
	report = Report(site=None, target="v16", apps=["digest"])
	scan_patches(report, PythonScanner(RULES), "digest", app_path, set())
	assert [(finding.rule.id, finding.file, finding.line) for finding in report.findings] == [
		("v16-removed-blog-doctypes", "digest/patches.txt", 3)
	]


def test_path_mode_reads_pyproject_on_frappe_version_branch(app_path):
	(app_path.parent / ".git").mkdir()
	(app_path.parent / ".git" / "HEAD").write_text("ref: refs/heads/version-15-hotfix\n", encoding="utf-8")
	(app_path.parent / "pyproject.toml").write_text(
		'[project]\nname = "digest"\nrequires-python = ">=3.10,<3.13"\n', encoding="utf-8"
	)
	report = build_path_report(RULES, "v16", [app_path])
	assert [(finding.rule.id, finding.file) for finding in report.findings] == [
		("v16-app-requires-python", "pyproject.toml")
	]


def test_field_of_the_doc_hooks_py_hands_a_doc_event_handler_is_reported(app_path):
	(app_path / "hooks.py").write_text(
		'doc_events = {"Payment Entry": {"validate": "digest.events.validate_payment"}}\n', encoding="utf-8"
	)
	(app_path / "events.py").write_text(
		"def validate_payment(doc, method):\n\tdoc.party_balance = 0\n", encoding="utf-8"
	)
	report = Report(site=None, target="v16", apps=["digest"])
	scan_app(report, Scanners(RULES), "digest", app_path)
	assert [(finding.rule.id, finding.file, finding.line) for finding in report.findings] == [
		("v16-erpnext-removed-fields", "digest/events.py", 2)
	]


def test_function_in_a_module_hooks_py_does_not_name_is_handed_no_doc(app_path):
	(app_path / "hooks.py").write_text(
		'doc_events = {"Payment Entry": {"validate": "digest.events.validate_payment"}}\n', encoding="utf-8"
	)
	(app_path / "payments.py").write_text(
		"def validate_payment(doc, method):\n\tdoc.party_balance = 0\n", encoding="utf-8"
	)
	report = Report(site=None, target="v16", apps=["digest"])
	scan_app(report, Scanners(RULES), "digest", app_path)
	assert report.findings == []


def test_online_checks_get_each_app_root_and_no_frappe_major(monkeypatch, app_path):
	calls = []
	online_scanner = types.ModuleType("preflight.online_scanner")
	online_scanner.OnlineScanner = lambda rules: None
	online_scanner.scan_online = lambda report, scanner, app_roots, frappe_major: calls.append(
		(app_roots, frappe_major)
	)
	monkeypatch.setitem(sys.modules, "preflight.online_scanner", online_scanner)
	build_path_report(RULES, "v16", [app_path], online=True)
	assert calls == [({"digest": app_path.parent}, None)]
