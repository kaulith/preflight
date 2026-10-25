import json
from dataclasses import replace
from pathlib import Path

import click

from preflight import __version__
from preflight.formatter import format_html, format_json, format_report, format_sarif, python_version
from preflight.models import Finding, Report, RuleSet
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
NEWSLETTER = next(rule for rule in load_rules("v16") if rule.id == "v16-removed-newsletter")
NEWSLETTER_IMPORT = Finding(
	rule=NEWSLETTER,
	file="digest/api.py",
	line=5,
	snippet="from frappe.email.doctype.newsletter import newsletter",
	app="digest",
)


def scanned(fixture):
	scanner = PythonScanner(load_rules("v16"))
	findings = scanner.scan((FIXTURES / fixture).read_text(), f"custom_app/{fixture}")
	return Report(site="test.localhost", target="v16", apps=["custom_app"], findings=findings)


def render(fixture):
	return click.unstyle(format_report(scanned(fixture)))


def test_findings_are_grouped_by_severity_then_rule():
	output = render("violations.py")
	assert output.index("ERROR (48)") < output.index("WARNING (20)") < output.index("INFO (1)")
	assert output.index("v16-has-permission-raise-exception") < output.index("v16-removed-newsletter")
	assert "    custom_app/violations.py:5  from frappe.email.doctype.newsletter" in output
	assert output.count("v16-deprecated-make-esc") == 1
	assert "48 error, 20 warning, 1 info" in output


def test_clean_report_says_so():
	output = render("clean.py")
	assert "No known incompatibilities found." in output
	assert "ERROR" not in output


def test_report_filtered_by_severity_says_what_it_left_out():
	report = scanned("violations.py")
	hidden = len([finding for finding in report.findings if finding.rule.severity != "error"])
	output = click.unstyle(format_report(report, "error"))
	assert "WARNING" not in output
	assert f"{hidden} more below error, not shown." in output


def test_report_with_nothing_above_the_floor_does_not_read_as_clean():
	report = scanned("violations.py")
	report.findings = [finding for finding in report.findings if finding.rule.severity == "info"]
	output = click.unstyle(format_report(report, "error"))
	assert "No known incompatibilities found." not in output
	assert "No findings at or above error, and 1 below it, not shown." in output


def test_apps_the_bench_does_not_hold_are_named_as_not_scanned():
	report = scanned("clean.py")
	report.missing_apps.append("print_designer")
	output = click.unstyle(format_report(report))
	assert "Not scanned, no code on this bench (1)" in output
	assert "    print_designer" in output
	assert "No known incompatibilities found in what was scanned." in output


def test_files_the_parser_could_not_read_are_named_with_the_python_doing_the_reading():
	report = scanned("violations.py")
	report.unparsable_files.append("custom_app/newer_syntax.py")
	output = click.unstyle(format_report(report))
	assert f"Not scanned, python {python_version()} could not parse them (1)" in output
	assert "    custom_app/newer_syntax.py" in output


def test_files_that_could_not_be_read_are_named_with_the_reason():
	report = scanned("clean.py")
	report.unreadable_files.append("custom_app/totals.py: maximum recursion depth exceeded")
	output = click.unstyle(format_report(report))
	assert "Not scanned, could not be read (1)" in output
	assert "    custom_app/totals.py: maximum recursion depth exceeded" in output
	assert "No known incompatibilities found in what was scanned." in output


def test_checks_that_were_skipped_are_named_as_not_checked():
	report = scanned("clean.py")
	report.not_checked.append("digest/pyproject.toml: detached HEAD, requires-python not checked")
	output = click.unstyle(format_report(report))
	assert "Not checked (1)" in output
	assert "    digest/pyproject.toml: detached HEAD, requires-python not checked" in output
	assert "No known incompatibilities found in what was scanned." in output


def test_report_header_names_the_frappe_version_and_the_target():
	report = scanned("clean.py")
	report.frappe_version = "15.88.0"
	output = click.unstyle(format_report(report))
	assert output.startswith("Preflight test.localhost: frappe 15.88.0 → v16\n")


def test_report_header_in_path_mode_says_only_code_was_read():
	output = click.unstyle(format_report(Report(site=None, target="v16", apps=["digest"])))
	assert output.startswith("Preflight code only → v16\nApps scanned: digest\n")


def test_report_header_says_when_and_against_what_the_rules_were_checked():
	ruleset = RuleSet(target="v16", released=True, checked="2026-10-25", against="frappe v16.53.0")
	report = Report(site="test.localhost", target="v16", apps=["digest"], ruleset=ruleset)
	assert "\nRules checked 2026-10-25 against frappe v16.53.0\n" in click.unstyle(format_report(report))


def test_app_finding_is_located_from_the_apps_directory():
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[NEWSLETTER_IMPORT])
	output = click.unstyle(format_report(report))
	assert "    digest/digest/api.py:5  from frappe.email.doctype.newsletter import newsletter" in output


def test_findings_with_no_line_in_one_file_are_listed_without_one():
	settings = replace(
		NEWSLETTER_IMPORT, file="digest/doctype/digest_settings/digest_settings.json", line=None
	)
	findings = [
		replace(settings, snippet="link field newsletter"),
		replace(settings, snippet="table field lists"),
	]
	output = click.unstyle(
		format_report(Report(site="test.localhost", target="v16", apps=["digest"], findings=findings))
	)
	assert "    digest/digest/doctype/digest_settings/digest_settings.json  link field newsletter" in output
	assert "    digest/digest/doctype/digest_settings/digest_settings.json  table field lists" in output


def test_fix_says_it_can_ship_before_upgrading():
	finding = replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, fix="before"))
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	assert f"  Fix before upgrading: {NEWSLETTER.replacement}\n" in click.unstyle(format_report(report))


def test_shim_is_printed_under_a_fix_that_needs_the_upgrade():
	shim = "try:\n\tfrom newsletter import newsletter\nexcept ImportError:\n\tfrom frappe.email.doctype import newsletter"
	finding = replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, fix="with-upgrade", shim=shim))
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	output = click.unstyle(format_report(report))
	assert (
		f"  Fix with the upgrade: {NEWSLETTER.replacement}\n  Shim that runs on both versions:\n      try:\n"
		in output
	)


def test_finding_in_a_patch_not_yet_run_is_marked_as_stopping_migrate():
	finding = replace(NEWSLETTER_IMPORT, file="digest/patches/v15_0/send_digest.py", stops_migrate=True)
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	output = click.unstyle(format_report(report))
	assert f"send_digest.py:5  {finding.snippet}  [pending patch, stops bench migrate]\n" in output


def test_upstream_apps_are_named_with_their_branch_and_left_out_of_the_counts():
	report = Report(
		site="test.localhost",
		target="v16",
		apps=["digest", "erpnext"],
		upstream_apps={"erpnext": "version-15"},
		upstream_findings=[replace(NEWSLETTER_IMPORT, app="erpnext", file="erpnext/crm/utils.py")],
	)
	output = click.unstyle(format_report(report))
	assert "Upstream apps, not counted (1)\n    erpnext on version-15: 1 found\n" in output
	assert "No known incompatibilities found." in output


def test_rules_hit_in_patches_already_run_are_counted_by_rule():
	ran = replace(NEWSLETTER_IMPORT, file="digest/patches/v14_0/send_digest.py")
	report = Report(
		site="test.localhost", target="v16", apps=["digest"], ran_patch_findings=[ran, replace(ran, line=9)]
	)
	output = click.unstyle(format_report(report))
	assert (
		"Rules hit in patches already run, not counted (1)\n    v16-removed-newsletter: 2 found\n" in output
	)


def test_footer_names_the_suppressed_and_baselined_counts():
	report = Report(site="test.localhost", target="v16", apps=["digest"], suppressed=2, baselined=3)
	output = click.unstyle(format_report(report))
	assert "\n2 suppressed by an ignore comment and 3 in the baseline, not counted.\n" in output


def test_json_report_names_the_python_that_scanned():
	assert json.loads(format_json(scanned("clean.py")))["python"] == python_version()


def test_json_report_names_the_frappe_and_preflight_versions():
	report = scanned("clean.py")
	report.frappe_version = "15.88.0"
	payload = json.loads(format_json(report))
	assert (payload["frappe_version"], payload["preflight_version"]) == ("15.88.0", __version__)


def test_json_report_names_what_was_not_read_or_not_checked():
	report = scanned("clean.py")
	report.unreadable_files.append("digest: ImportError: cannot import name 'get_url'")
	report.not_checked.append("digest/pyproject.toml: detached HEAD, requires-python not checked")
	payload = json.loads(format_json(report))
	assert payload["unreadable_files"] == report.unreadable_files
	assert payload["not_checked"] == report.not_checked


def test_json_report_carries_the_rule_with_each_finding():
	report = scanned("violations.py")
	payload = json.loads(format_json(report))
	assert payload["site"] == "test.localhost"
	assert payload["target"] == "v16"
	assert len(payload["findings"]) == len(report.findings)
	newsletter = next(
		finding for finding in payload["findings"] if finding["rule"] == "v16-removed-newsletter"
	)
	assert newsletter["severity"] == "error"
	assert newsletter["file"] == "custom_app/violations.py"
	assert newsletter["references"]


def test_json_report_is_filtered_to_the_severity_it_records():
	payload = json.loads(format_json(scanned("violations.py"), "error"))
	assert payload["severity"] == "error"
	assert {finding["severity"] for finding in payload["findings"]} == {"error"}


def test_json_report_of_a_clean_file_has_no_findings():
	assert json.loads(format_json(scanned("clean.py")))["findings"] == []


def test_json_report_keys_are_in_the_frozen_shape():
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[NEWSLETTER_IMPORT])
	payload = json.loads(format_json(report))
	assert list(payload) == [
		"schema_version",
		"preflight_version",
		"site",
		"target",
		"rules",
		"python",
		"frappe_version",
		"severity",
		"fail_on",
		"verdict",
		"summary",
		"apps",
		"missing_apps",
		"findings",
		"upstream",
		"ran_patch_findings",
		"unparsable_files",
		"unreadable_files",
		"not_checked",
	]
	assert list(payload["summary"]) == [
		"error",
		"warning",
		"info",
		"below_severity",
		"suppressed",
		"baselined",
		"upstream",
		"ran_patches",
	]
	assert list(payload["findings"][0]) == [
		"rule",
		"severity",
		"title",
		"message",
		"replacement",
		"fix",
		"shim",
		"references",
		"app",
		"source",
		"file",
		"line",
		"snippet",
		"stops_migrate",
	]


def test_json_report_fails_when_a_finding_is_at_the_fail_on_severity():
	finding = replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, severity="warning"))
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	verdicts = [json.loads(format_json(report, fail_on=level))["verdict"] for level in ("warning", "error")]
	assert verdicts == ["fail", "pass"]


def test_json_summary_counts_what_is_shown_and_what_is_below_the_severity():
	info = replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, severity="info"))
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[NEWSLETTER_IMPORT, info])
	summary = json.loads(format_json(report, "warning"))["summary"]
	assert (summary["error"], summary["info"], summary["below_severity"]) == (1, 0, 1)


def test_json_report_has_null_for_what_is_unset():
	report = Report(
		site=None,
		target="v16",
		apps=["digest"],
		findings=[replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, fix="", shim=""), line=None)],
	)
	payload = json.loads(format_json(report))
	assert (payload["site"], payload["frappe_version"], payload["rules"]) == (None, None, None)
	finding = payload["findings"][0]
	assert (finding["line"], finding["fix"], finding["shim"]) == (None, None, None)


def test_json_report_lists_upstream_findings_under_their_app():
	report = Report(
		site="test.localhost",
		target="v16",
		apps=["digest", "erpnext"],
		upstream_apps={"erpnext": "version-15"},
		upstream_findings=[replace(NEWSLETTER_IMPORT, app="erpnext", file="erpnext/crm/utils.py")],
	)
	payload = json.loads(format_json(report))
	upstream = [(app["app"], app["branch"], len(app["findings"])) for app in payload["upstream"]]
	assert upstream == [("erpnext", "version-15", 1)]
	assert (payload["findings"], payload["summary"]["upstream"]) == ([], 1)


def test_json_report_filters_ran_patch_findings_by_severity():
	ran = replace(NEWSLETTER_IMPORT, rule=replace(NEWSLETTER, severity="info"))
	report = Report(site="test.localhost", target="v16", apps=["digest"], ran_patch_findings=[ran])
	assert json.loads(format_json(report, "warning"))["ran_patch_findings"] == []


def test_html_report_embeds_the_whole_json_even_when_a_snippet_closes_a_script_tag():
	report = scanned("violations.py")
	report.findings = [replace(report.findings[0], snippet='html = "</script>"')]
	page = format_html(report)
	embedded = page.split('<script id="report-data" type="application/json">')[1].split("</script>")[0]
	assert json.loads(embedded) == json.loads(format_json(report))


def test_sarif_locates_a_finding_from_the_app_root_when_one_app_is_scanned():
	report = Report(site=None, target="v16", apps=["digest"], findings=[NEWSLETTER_IMPORT])
	result = json.loads(format_sarif(report))["runs"][0]["results"][0]
	assert result["locations"][0]["physicalLocation"] == {
		"artifactLocation": {"uri": "digest/api.py"},
		"region": {"startLine": 5},
	}


def test_sarif_locates_a_finding_from_the_apps_directory_when_several_apps_are_scanned():
	report = Report(
		site="test.localhost", target="v16", apps=["digest", "erpnext"], findings=[NEWSLETTER_IMPORT]
	)
	result = json.loads(format_sarif(report))["runs"][0]["results"][0]
	assert result["locations"][0]["physicalLocation"]["artifactLocation"] == {"uri": "digest/digest/api.py"}


def test_sarif_describes_each_rule_once():
	findings = [NEWSLETTER_IMPORT, replace(NEWSLETTER_IMPORT, line=9)]
	run = json.loads(format_sarif(Report(site=None, target="v16", apps=["digest"], findings=findings)))[
		"runs"
	][0]
	assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == ["v16-removed-newsletter"]
	assert [result["ruleIndex"] for result in run["results"]] == [0, 0]


def test_sarif_leaves_out_findings_with_no_file_and_says_how_many():
	script = replace(NEWSLETTER_IMPORT, app=None, source="site", file="Server Script: Daily Digest", line=3)
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[script])
	run = json.loads(format_sarif(report))["runs"][0]
	assert run["results"] == []
	notification = run["invocations"][0]["toolExecutionNotifications"][0]
	assert notification["message"]["text"].startswith("1 found on site records, the bench")


def test_sarif_places_a_finding_with_no_line_on_the_first_line_of_its_file():
	missing_key = replace(NEWSLETTER_IMPORT, file="pyproject.toml", line=None)
	report = Report(site=None, target="v16", apps=["digest"], findings=[missing_key])
	result = json.loads(format_sarif(report))["runs"][0]["results"][0]
	assert result["locations"][0]["physicalLocation"] == {
		"artifactLocation": {"uri": "pyproject.toml"},
		"region": {"startLine": 1},
	}


def test_sarif_leaves_out_a_missing_upstream_branch_and_counts_it():
	rule = next(rule for rule in load_rules("v16") if rule.id == "v16-app-target-branch")
	branch = Finding(
		rule=rule,
		file="upstream/version-16",
		line=None,
		snippet="erpnext is on version-15-hotfix; upstream has no branch version-16",
		app="erpnext",
	)
	run = json.loads(format_sarif(Report(site=None, target="v16", apps=["erpnext"], findings=[branch])))[
		"runs"
	][0]
	assert run["results"] == []
	notification = run["invocations"][0]["toolExecutionNotifications"][0]
	assert notification["message"]["text"].startswith(
		"1 found on site records, the bench or an app's upstream"
	)
