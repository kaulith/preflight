"""The scan of an app's own files, which needs only the files: no site, no bench, and no frappe."""

import json
import re
from collections.abc import Collection, Iterator, Mapping
from dataclasses import replace
from pathlib import Path

from jinja2 import TemplateSyntaxError
from jinja2.lexer import newline_re
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from preflight.compatibility_scanner import CompatibilityScanner, declared_dependencies
from preflight.hooks_scanner import HooksScanner, hooked_doctypes
from preflight.jinja_scanner import JinjaScanner, renders_html, renders_layout, renders_subject
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
# The file beside a standard notification's record that holds its message, by message_type.
NOTIFICATION_BODY_SUFFIXES = {"HTML": ".html", "Markdown": ".md", "Plain Text": ".txt"}


class Scanners:
	"""The six scanners, compiled once from one rule set."""

	def __init__(self, rules: list[Rule]):
		self.python = PythonScanner(rules)
		self.js = JSScanner(rules)
		self.jinja = JinjaScanner(rules)
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


def patch_places(app: str, app_path: Path) -> Iterator[tuple[str, set[tuple[str, str, int | None]]]]:
	"""Each patch of the app's patches.txt as Patch Log names it, with the places a finding in it is read
	from. Patches are told apart the way frappe's patch_handler tells them: by the line, stripped, `#`
	comment and all; a `finally:` patch is logged without the tag. A module patch is its file; an
	`execute:` patch is its patches.txt line."""
	try:
		text = (app_path / "patches.txt").read_text(encoding="utf-8", errors="replace")
	except OSError:
		return
	for number, line in enumerate(text.split("\n"), 1):
		patch = line.strip()
		if not patch or patch.startswith(("#", ";", "[")):
			continue
		if patch.startswith("finally:"):
			patch = patch.replace("finally:", "")
		if patch.startswith("execute:"):
			yield patch, {(app, f"{app_path.name}/patches.txt", number)}
		else:
			module = patch.split(maxsplit=1)[0].replace(".", "/")
			package = module.split("/")[0]
			yield patch, {(package, f"{module}.py", None), (package, f"{module}/__init__.py", None)}


def note_counted_patch_findings(report: Report, app_paths: list[Path]):
	"""Say how many counted findings are in patches. --path has no Patch Log to set aside the ones already
	run, and leaving them all out would hide a patch still to run, which stops `bench migrate`."""
	places = {
		place
		for app_path in app_paths
		for _, patch_place in patch_places(app_path.name, app_path)
		for place in patch_place
	}
	found = sum(
		bool(places & {(finding.app, finding.file, finding.line), (finding.app, finding.file, None)})
		for finding in report.findings
	)
	if found:
		report.not_checked.append(
			"patches: --path reads no Patch Log to show which already ran, so what is found in them is counted"
			f" ({found} found); --site sets aside those already run, --baseline records them"
		)


def scan_app(report: Report, scanners: Scanners, app: str, app_path: Path, skip_tests: bool = False):
	"""The app's Python with its hooks.py, its front-end files anywhere in the repository, its Jinja
	templates, the `execute:` lines of its patches.txt, and the link fields of its doctypes. Each file is
	named from the repository root, the parent of `app_path`; the report's lists name it under the app as
	well."""
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
	scan_templates(report, scanners.jinja, app, app_path, skip_tests)
	scan_query_reports(report, scanners.python, app, app_path, skip_tests)
	scan_patches(report, scanners.python, app, app_path, declared)
	report.findings += [
		replace(finding, app=app) for finding in scanners.schema.scan(app_doctype_fields(app_path))
	]


def scan_template(
	report: Report,
	scanner: JinjaScanner,
	template: str,
	file: str,
	doc_doctypes: Collection[str] = (),
	app: str | None = None,
	source: str = "app",
	embedded: bool = False,
) -> bool:
	"""Count the template's findings into the report, False when it does not parse. One `embedded` in a
	JSON file has no line there, so its findings carry the template's line as their snippet alone."""
	template = newline_re.sub("\n", template)
	try:
		findings = scanner.scan(template, file, doc_doctypes)
	except (TemplateSyntaxError, RecursionError):
		return False
	if embedded:
		findings = list(dict.fromkeys(replace(finding, line=None) for finding in findings))
	add_findings(report, findings, template, app, source)
	return True


def note_unparsed_templates(report: Report, owner: str, unparsed: int):
	if unparsed:
		report.not_checked.append(
			f"{owner}: Jinja templates that do not parse ({unparsed}), the fields they read not checked"
		)


def scan_template_file(
	report: Report,
	scanner: JinjaScanner,
	app: str,
	app_root: Path,
	path: Path,
	doc_doctypes: Collection[str] = (),
) -> bool:
	"""False when the file holds a template that does not parse. One that cannot be read is listed as such."""
	file = str(path.relative_to(app_root))
	template = read_source(path, f"{app}/{file}", report.unreadable_files)
	return template is None or scan_template(report, scanner, template, file, doc_doctypes, app)


def scan_print_format(
	report: Report, scanner: JinjaScanner, app: str, app_root: Path, path: Path, record: dict
) -> int:
	"""How many of the print format's templates do not parse. The `.html` beside its record is what frappe
	renders in place of its html field."""
	if record.get("disabled"):
		return 0
	unparsed = 0
	file = str(path.relative_to(app_root))
	doctype = record.get("doc_type")
	doc_doctypes = (doctype,) if doctype else ()
	if renders_html(record):
		if (html_file := path.with_suffix(".html")).is_file():
			unparsed += not scan_template_file(report, scanner, app, app_root, html_file, doc_doctypes)
		elif record.get("html"):
			unparsed += not scan_template(
				report, scanner, record["html"], file, doc_doctypes, app, embedded=True
			)
	if doctype and renders_layout(record):
		findings, failed = scanner.scan_layout(record["format_data"], file, doctype)
		add_findings(report, findings, "", app)
		unparsed += failed
	return unparsed


def scan_notification(
	report: Report, scanner: JinjaScanner, app: str, app_root: Path, path: Path, record: dict
) -> int:
	"""How many of the notification's templates do not parse: its subject, and the message frappe reads
	from the file beside its record."""
	if not record.get("enabled", 1):
		return 0
	unparsed = 0
	doc_doctypes = (record["document_type"],) if record.get("document_type") else ()
	if record.get("subject") and renders_subject(record):
		file = str(path.relative_to(app_root))
		unparsed += not scan_template(
			report, scanner, record["subject"], file, doc_doctypes, app, embedded=True
		)
	body = path.with_suffix(NOTIFICATION_BODY_SUFFIXES.get(record.get("message_type"), ".md"))
	if body.is_file():
		unparsed += not scan_template_file(report, scanner, app, app_root, body, doc_doctypes)
	return unparsed


def scan_templates(report: Report, scanner: JinjaScanner, app: str, app_path: Path, skip_tests: bool = False):
	"""The app's print formats and notifications, each with the doctype it renders, and the HTML under
	templates/ and www/, which renders with no doc the file can name."""
	app_root = app_path.parent
	unparsed = 0
	for directory in ("templates", "www"):
		for path in source_files(app_path / directory, ".html", skip_tests):
			unparsed += not scan_template_file(report, scanner, app, app_root, path)
	for path in source_files(app_path, ".json", skip_tests):
		if path.stem != path.parent.name or path.parents[1].name not in ("print_format", "notification"):
			continue
		source = read_source(path, f"{app}/{path.relative_to(app_root)}", report.unreadable_files)
		if source is None:
			continue
		try:
			record = json.loads(source)
		except ValueError:
			unparsed += 1
			continue
		if not isinstance(record, dict):
			continue
		if record.get("doctype") == "Print Format":
			unparsed += scan_print_format(report, scanner, app, app_root, path, record)
		elif record.get("doctype") == "Notification":
			unparsed += scan_notification(report, scanner, app, app_root, path, record)
	note_unparsed_templates(report, app, unparsed)


def scan_query_reports(
	report: Report, scanner: PythonScanner, app: str, app_path: Path, skip_tests: bool = False
):
	"""The SQL of the app's Query Reports. It has no line in the JSON file, so each finding carries the
	query's line as its snippet alone."""
	app_root = app_path.parent
	for path in source_files(app_path, ".json", skip_tests):
		if path.stem != path.parent.name or path.parents[1].name != "report":
			continue
		file = str(path.relative_to(app_root))
		source = read_source(path, f"{app}/{file}", report.unreadable_files)
		if source is None:
			continue
		try:
			record = json.loads(source)
		except ValueError:
			report.unparsable_files.append(f"{app}/{file}")
			continue
		if (
			isinstance(record, dict)
			and record.get("report_type") == "Query Report"
			and record.get("query")
			and not record.get("disabled")
		):
			findings = scanner.scan_sql(record["query"], file)
			add_findings(report, [replace(finding, line=None) for finding in findings], source, app)


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
