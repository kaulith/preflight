import json
import os
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path

import click

from preflight import __version__
from preflight.app_scan import build_path_report
from preflight.formatter import format_html, format_json, format_report, format_sarif
from preflight.models import SEVERITIES, Report, Rule
from preflight.rule_loader import RuleError, load_rules, load_ruleset, released_targets

FORMATTERS = {"text": format_report, "json": format_json, "html": format_html, "sarif": format_sarif}
# What a baseline finding is matched on: everything but its line, which moves as the file changes.
BASELINE_KEYS = ("rule", "app", "file", "snippet")


def app_package_dir(path: Path) -> Path:
	"""The app's package directory, the one holding hooks.py: `path` itself, or the one directory in it
	that holds one, so an app is named by its repository root or by its package."""
	path = path.resolve()
	if (path / "hooks.py").is_file():
		return path
	packages = sorted(child for child in path.iterdir() if (child / "hooks.py").is_file())
	if len(packages) != 1:
		raise click.UsageError(f"--path {path}: no app, neither it nor one directory in it holds a hooks.py")
	return packages[0]


def read_baseline(path: Path) -> Counter:
	"""The findings of a report written earlier with --format json, each as often as it appears."""
	try:
		data = json.loads(path.read_text(encoding="utf-8"))
	except (OSError, ValueError) as e:
		raise click.UsageError(f"--baseline {path}: {e}") from e
	findings = data.get("findings") if isinstance(data, dict) else None
	if not isinstance(findings, list) or not all(
		isinstance(entry, dict) and all(key in entry for key in BASELINE_KEYS) for entry in findings
	):
		raise click.UsageError(f"--baseline {path}: not a report written with --format json")
	return Counter(tuple(entry[key] for key in BASELINE_KEYS) for entry in findings)


def scan_site(
	rules: list[Rule], site: str, target: str, apps: tuple[str, ...], skip_tests: bool, online: bool
) -> Report:
	"""Connect to the site from the bench this python's env belongs to (`<bench>/env`), working in its
	sites directory the way bench does. frappe is imported here only, so --path runs without it."""
	sites_path = Path(sys.prefix).parent / "sites"
	if not sites_path.is_dir():
		raise click.UsageError(
			f"--site needs the python of a bench's env; {sites_path} is not a bench's sites"
		)
	import frappe

	from preflight.scan import build_report

	if int(frappe.__version__.split(".")[0]) >= int(target.removeprefix("v")):
		raise click.UsageError(
			f"this bench already runs frappe {frappe.__version__}; --target is the version to upgrade to"
		)
	os.chdir(sites_path)
	try:
		frappe.init(site=site, sites_path=str(sites_path))
		frappe.connect()
		installed = frappe.get_installed_apps()
		if unknown := [app for app in apps if app not in installed]:
			raise click.UsageError(f"not installed on {site}: {', '.join(unknown)}")
		return build_report(rules, site, target, apps, skip_tests, online)
	except frappe.exceptions.IncorrectSitePath as e:
		raise click.UsageError(str(e)) from e
	finally:
		frappe.destroy()


@click.command("preflight")
@click.version_option(version=__version__, prog_name="preflight")
@click.option("--site", help="Site to scan, on the bench whose env runs preflight")
@click.option(
	"--path",
	"paths",
	multiple=True,
	type=click.Path(exists=True, file_okay=False, path_type=Path),
	help="Scan the app in this directory, its repository or its package, with no site or bench; repeatable",
)
@click.option("--target", required=True, help="Version to check against, selects the rule set (e.g. v16)")
@click.option("--unreleased", is_flag=True, hidden=True, help="Allow a target that is not released yet")
@click.option("--app", "apps", multiple=True, help="Scan only this app of the site; repeatable")
@click.option(
	"--severity",
	type=click.Choice(SEVERITIES),
	default="info",
	help="Lowest severity to report",
)
@click.option(
	"--fail-on",
	type=click.Choice((*SEVERITIES, "never")),
	default="error",
	help="Lowest severity that exits 1",
)
@click.option(
	"--format", "output_format", type=click.Choice(tuple(FORMATTERS)), default="text", help="Report format"
)
@click.option("--open", "open_report", is_flag=True, help="Also open the HTML report in a browser")
@click.option(
	"--baseline",
	type=click.Path(dir_okay=False, path_type=Path),
	help="Leave out the findings of this earlier --format json report",
)
@click.option("--online", is_flag=True, help="Also run the checks that ask git remotes, node and PyPI")
@click.option("--skip-tests", is_flag=True, help="Skip test files and tests directories")
def preflight_command(
	site: str | None,
	paths: tuple[Path, ...],
	target: str,
	unreleased: bool,
	apps: tuple[str, ...],
	severity: str,
	fail_on: str,
	output_format: str,
	open_report: bool,
	baseline: Path | None,
	online: bool,
	skip_tests: bool,
):
	"""Report APIs removed, renamed or deprecated in the target version"""
	if bool(site) == bool(paths):
		raise click.UsageError("Pass --site to scan a site, or --path to scan an app's files: one of the two")
	if paths and apps:
		raise click.UsageError("--app picks apps of a site; with --path, pass each app's directory")
	try:
		rules = load_rules(target)
		ruleset = load_ruleset(target)
	except RuleError as e:
		raise click.UsageError(str(e)) from e
	if not ruleset.released and not unreleased:
		raise click.UsageError(
			f"{target} is not released yet. Available targets: {', '.join(released_targets())}"
		)
	baselined = read_baseline(baseline) if baseline else Counter()
	app_paths = [app_package_dir(path) for path in paths]

	try:
		if site:
			report = scan_site(rules, site, target, apps, skip_tests, online)
		else:
			report = build_path_report(rules, target, app_paths, skip_tests, online)
		report.ruleset = ruleset
		counted = []
		for finding in report.findings:
			key = (finding.rule.id, finding.app, finding.file, finding.snippet)
			if baselined[key]:
				baselined[key] -= 1
				report.baselined += 1
			else:
				counted.append(finding)
		report.findings = counted
		click.echo(FORMATTERS[output_format](report, severity, fail_on))
		if open_report:
			with tempfile.NamedTemporaryFile(
				"w", encoding="utf-8", prefix="preflight-", suffix=".html", delete=False
			) as page:
				page.write(format_html(report, severity, fail_on))
			click.echo(f"HTML report: {page.name}", err=True)
			click.launch(page.name)
	except click.ClickException:
		raise
	except Exception:  # noqa: BLE001
		traceback.print_exc()
		sys.exit(3)
	if report.fails(fail_on):
		sys.exit(1)
