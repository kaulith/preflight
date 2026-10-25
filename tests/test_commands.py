import json
import sys
import tempfile
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from preflight import __version__, commands
from preflight.models import Finding, Report
from preflight.rule_loader import load_rules

NEWSLETTER = next(rule for rule in load_rules("v16") if rule.id == "v16-removed-newsletter")
FINDING = Finding(
	rule=NEWSLETTER,
	file="digest/api.py",
	line=3,
	snippet="from frappe.email.doctype.newsletter.newsletter import send_newsletter",
	app="digest",
)
BLOG_SETTINGS = 'frappe.db.set_value("Blog Settings", None, "show_cta_in_blog", 1)\n'


@pytest.fixture
def connected(monkeypatch, tmp_path):
	"""A v15 bench at tmp_path whose site test.localhost has digest installed, and no database."""
	frappe = pytest.importorskip("frappe")
	(tmp_path / "sites").mkdir()
	monkeypatch.setattr(sys, "prefix", str(tmp_path / "env"))
	monkeypatch.chdir(tmp_path)
	monkeypatch.setattr(frappe, "init", lambda site, sites_path: None)
	monkeypatch.setattr(frappe, "connect", lambda: None)
	monkeypatch.setattr(frappe, "destroy", lambda: None)
	monkeypatch.setattr(frappe, "get_installed_apps", lambda: ["frappe", "digest"])
	monkeypatch.setattr(frappe, "__version__", "15.123.1")
	return frappe


@pytest.fixture
def app_path(tmp_path):
	"""The repository of `digest`, whose api.py writes to Blog Settings."""
	path = tmp_path / "digest" / "digest"
	path.mkdir(parents=True)
	(path / "hooks.py").write_text('app_name = "digest"\n', encoding="utf-8")
	(path / "api.py").write_text(BLOG_SETTINGS, encoding="utf-8")
	return path


def preflight(monkeypatch, *args: str, findings: tuple[Finding, ...] = ()):
	from preflight import scan

	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=list(findings))
	monkeypatch.setattr(scan, "build_report", lambda *arguments: report)
	return CliRunner().invoke(
		commands.preflight_command, ["--site", "test.localhost", "--target", "v16", *args]
	)


def test_clean_scan_exits_0(monkeypatch, connected):
	assert preflight(monkeypatch).exit_code == 0


def test_finding_at_the_fail_on_level_exits_1(monkeypatch, connected):
	assert preflight(monkeypatch, findings=(FINDING,)).exit_code == 1


def test_fail_on_never_exits_0_with_findings(monkeypatch, connected):
	assert preflight(monkeypatch, "--fail-on", "never", findings=(FINDING,)).exit_code == 0


def test_app_not_installed_on_the_site_exits_2(monkeypatch, connected):
	assert preflight(monkeypatch, "--app", "crm").exit_code == 2


def test_bench_already_on_the_target_exits_2(monkeypatch, connected):
	monkeypatch.setattr(connected, "__version__", "16.50.0")
	result = preflight(monkeypatch)
	assert result.exit_code == 2
	assert "this bench already runs frappe 16.50.0" in result.output


def test_open_launches_the_html_report(monkeypatch, connected, tmp_path):
	monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
	launched = []
	monkeypatch.setattr(click, "launch", launched.append)
	preflight(monkeypatch, "--open")
	assert Path(launched[0]).read_text(encoding="utf-8").startswith("<!doctype html>")


def test_open_launches_nothing_when_the_scan_is_refused(monkeypatch, connected):
	monkeypatch.setattr(connected, "__version__", "16.50.0")
	launched = []
	monkeypatch.setattr(click, "launch", launched.append)
	preflight(monkeypatch, "--open")
	assert launched == []


def test_scan_that_cannot_run_exits_3_with_the_traceback(monkeypatch, connected):
	def refused():
		raise ConnectionRefusedError("Can't connect to MySQL server on '127.0.0.1'")

	monkeypatch.setattr(connected, "connect", refused)
	result = preflight(monkeypatch)
	assert result.exit_code == 3
	assert "ConnectionRefusedError: Can't connect to MySQL server" in result.stderr


def test_version_is_printed_without_a_scan():
	result = CliRunner().invoke(commands.preflight_command, ["--version"])
	assert result.output == f"preflight, version {__version__}\n"


@pytest.mark.parametrize("args", [[], ["--site", "test.localhost", "--path", "."]])
def test_site_and_path_are_one_or_the_other(args):
	assert CliRunner().invoke(commands.preflight_command, ["--target", "v16", *args]).exit_code == 2


def test_unreleased_target_is_refused(app_path):
	result = CliRunner().invoke(commands.preflight_command, ["--path", str(app_path), "--target", "v17"])
	assert result.exit_code == 2
	assert "v17 is not released yet. Available targets: v16" in result.output


def test_unreleased_target_is_checked_when_asked_for(app_path):
	result = CliRunner().invoke(
		commands.preflight_command, ["--path", str(app_path), "--target", "v17", "--unreleased"]
	)
	assert result.exit_code == 0


@pytest.mark.parametrize("named_by", ["package", "repository"])
def test_an_app_is_named_by_its_package_or_its_repository(app_path, named_by):
	assert commands.app_package_dir(app_path if named_by == "package" else app_path.parent) == app_path


def test_a_directory_with_no_hooks_is_no_app(tmp_path):
	result = CliRunner().invoke(commands.preflight_command, ["--path", str(tmp_path), "--target", "v16"])
	assert result.exit_code == 2


def test_each_baseline_entry_excuses_one_finding(app_path, tmp_path):
	(app_path / "api.py").write_text(BLOG_SETTINGS * 3, encoding="utf-8")
	entry = {"rule": "v16-removed-blog-doctypes", "app": "digest", "file": "digest/api.py", "line": 9}
	entry["snippet"] = BLOG_SETTINGS.strip()
	(tmp_path / "baseline.json").write_text(json.dumps({"findings": [entry, entry]}), encoding="utf-8")
	result = CliRunner().invoke(
		commands.preflight_command,
		["--path", str(app_path), "--target", "v16", "--baseline", str(tmp_path / "baseline.json")],
	)
	assert result.exit_code == 1
	assert "1 error" in result.output


def test_a_baseline_that_is_not_a_report_exits_2(app_path, tmp_path):
	(tmp_path / "baseline.json").write_text('{"findings": [{"rule": "v16-removed-blog"}]}', encoding="utf-8")
	result = CliRunner().invoke(
		commands.preflight_command,
		["--path", str(app_path), "--target", "v16", "--baseline", str(tmp_path / "baseline.json")],
	)
	assert result.exit_code == 2
