"""The scan of an app's own files, which needs only the files: no site, no bench, and no frappe."""

import re
from collections.abc import Collection, Mapping
from dataclasses import replace
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from preflight.compatibility_scanner import CompatibilityScanner, declared_dependencies
from preflight.hooks_scanner import HooksScanner, hooked_doctypes
from preflight.js_scanner import JSScanner
from preflight.models import Finding, Report, Rule
from preflight.python_scanner import PythonScanner
from preflight.schema_scanner import SchemaScanner, app_doctype_fields
from preflight.sources import frontend_files, is_bundle, read_source, source_files

# Inside a comment: `#` in Python, TOML and patches.txt, `//` or `/*` in JS and SCSS, `<!--` in a Vue
# template.
IGNORE_COMMENT = re.compile(r"(?:#|//|/\*|<!--).*?\bpreflight:\s*ignore\[([^\]]*)\]")
# What --path cannot check, having no bench and no site to read.
PATH_MODE_NOT_CHECKED = (
	"required_apps: --path reads no bench to find them on, not checked",
	"bench Python: --path reads no bench, not checked",
	(
		"site: --path reads no site, its scripts, Custom Fields, Property Setters, records and Patch Log"
		" not checked"
	),
)


class Scanners:
	"""The five scanners, compiled once from one rule set."""

	def __init__(self, rules: list[Rule]):
		self.python = PythonScanner(rules)
		self.js = JSScanner(rules)
		self.hooks = HooksScanner(rules)
		self.schema = SchemaScanner(rules)
		self.compatibility = CompatibilityScanner(rules)


def ignored_rules(line: str) -> set[str]:
	"""The rule ids a `preflight: ignore[rule-a, rule-b]` comment on the line names."""
	return {
		rule_id.strip()
		for comment in IGNORE_COMMENT.finditer(line)
		for rule_id in comment.group(1).split(",")
	}


def add_findings(
	report: Report,
	findings: list[Finding],
	text: str,
	app: str | None = None,
	source: str = "app",
	declared: set[str] = frozenset(),
):
	"""Count the findings read from `text` into the report, as found in `app` and read from `source`.

	An import of a package the app declares is no finding, whatever frappe stops installing. One that an
	ignore comment on its own line names is counted as suppressed instead."""
	lines = text.split("\n")
	for finding in findings:
		if finding.rule.match.type == "undeclared_import" and not declared.isdisjoint(
			canonicalize_name(Requirement(dependency).name) for dependency in finding.rule.match.dependencies
		):
			continue
		if finding.line and finding.rule.id in ignored_rules(lines[finding.line - 1]):
			report.suppressed += 1
			continue
		report.findings.append(replace(finding, app=app, source=source))


def build_path_report(
	rules: list[Rule], target: str, app_paths: list[Path], skip_tests: bool = False, online: bool = False
) -> Report:
	"""Scan each app's files, `app_paths` naming the directory that holds its hooks.py. There is no frappe
	version to compare branches with, so each pyproject.toml is read whatever branch the app is on."""
	scanners = Scanners(rules)
	report = Report(site=None, target=target, apps=[app_path.name for app_path in app_paths])
	for app_path in app_paths:
		scan_app(report, scanners, app_path.name, app_path, skip_tests)
		scan_pyproject(report, scanners.compatibility, app_path.name, app_path.parent)
	report.not_checked += PATH_MODE_NOT_CHECKED
	if online:
		from preflight.online_scanner import OnlineScanner, scan_online

		app_roots = {app_path.name: app_path.parent for app_path in app_paths}
		scan_online(report, OnlineScanner(rules), app_roots, None)
	return report


def scan_app(report: Report, scanners: Scanners, app: str, app_path: Path, skip_tests: bool = False):
	"""The app's Python with its hooks.py, its front-end files anywhere in the repository, the `execute:`
	lines of its patches.txt, and the link fields of its doctypes. Each file is named from the repository
	root, the parent of `app_path`; the report's lists name it under the app as well."""
	app_root = app_path.parent
	declared = declared_dependencies(app_root)
	hooked = hooked_doctypes(app_path)
	for path in source_files(app_path, ".py", skip_tests):
		file = str(path.relative_to(app_root))
		source = read_source(path, f"{app}/{file}", report.unreadable_files)
		if source is None:
			continue
		module = ".".join(path.relative_to(app_root).with_suffix("").parts).removesuffix(".__init__")
		findings = scan_python(report, scanners.python, file, source, app, hooked.get(module, {}))
		if findings is None:
			continue
		if path == app_path / "hooks.py":
			findings += scanners.hooks.scan(source, file, app_path) + scanners.hooks.missing_hooks(
				source, file, app_path
			)
		add_findings(report, findings, source, app, declared=declared)
	for path in frontend_files(app_root, skip_tests):
		file = str(path.relative_to(app_root))
		source = read_source(path, f"{app}/{file}", report.unreadable_files)
		if source is not None and not is_bundle(source):
			add_findings(report, scanners.js.scan(source, file), source, app)
	scan_patches(report, scanners.python, app, app_path, declared)
	report.findings += [
		replace(finding, app=app) for finding in scanners.schema.scan(app_doctype_fields(app_path))
	]


def scan_patches(report: Report, scanner: PythonScanner, app: str, app_path: Path, declared: set[str]):
	"""The `execute:` lines of the app's patches.txt, which are Python that `bench migrate` runs. They are
	scanned as one file with every other line blanked, so each finding keeps its patches.txt line."""
	path = app_path / "patches.txt"
	if not path.is_file():
		return
	file = str(path.relative_to(app_path.parent))
	source = read_source(path, f"{app}/{file}", report.unreadable_files)
	if source is None:
		return
	code = "\n".join(
		line.removeprefix("execute:") if line.startswith("execute:") else "" for line in source.splitlines()
	)
	add_findings(report, scan_python(report, scanner, file, code, app) or [], code, app, declared=declared)


def scan_pyproject(report: Report, scanner: CompatibilityScanner, app: str, app_root: Path):
	path = app_root / "pyproject.toml"
	if not path.is_file():
		return
	source = read_source(path, f"{app}/pyproject.toml", report.unreadable_files)
	if source is None:
		return
	try:
		findings = scanner.scan_pyproject(source, "pyproject.toml")
	except ValueError:
		report.unparsable_files.append(f"{app}/pyproject.toml")
		return
	add_findings(report, findings, source, app)


def scan_python(
	report: Report,
	scanner: PythonScanner,
	file: str,
	source: str,
	app: str | None = None,
	hooked: Mapping[str, Collection[str]] = {},
	docs: Mapping[str, Collection[str]] = {},
) -> list[Finding] | None:
	"""The file's findings, or None when it does not parse, with the file named in the report's lists,
	under `app` when it is one of an app's. `hooked` and `docs` are PythonScanner.scan's."""
	listed = f"{app}/{file}" if app else file
	try:
		return scanner.scan(source, file, hooked, docs)
	except SyntaxError:
		report.unparsable_files.append(listed)
	except (ValueError, RecursionError) as error:
		report.unreadable_files.append(f"{listed}: {error}")
	return None
