import platform
from collections import Counter
from dataclasses import replace
from pathlib import Path

import frappe

from preflight.app_scan import Scanners, add_findings, scan_app, scan_pyproject, scan_python
from preflight.compatibility_scanner import CompatibilityScanner, checked_out_branch, is_frappe_branch
from preflight.models import Finding, Report, Rule
from preflight.schema_scanner import LINK_FIELDTYPES, SchemaRecord

# Where a site stores code, as (doctype, field, language, filters). A disabled script never runs, and a
# standard report's code is in its app's files.
SCRIPT_FIELDS = (
	("Server Script", "script", "python", {"disabled": 0}),
	("Client Script", "script", "js", {"enabled": 1}),
	("Report", "report_script", "python", {"is_standard": "No", "disabled": 0}),
	("Report", "javascript", "js", {"is_standard": "No", "disabled": 0}),
	("Web Form", "client_script", "js", {}),
	("Web Page", "javascript", "js", {}),
	("Web Page", "context_script", "python", {}),
	("Custom HTML Block", "script", "js", {}),
	("Notification", "condition", "python", {"enabled": 1}),
)
# The fields that say which doc a script runs with: a DocType Event server script's `doc` is one of its
# reference doctype, a notification condition's one of its document type.
SCRIPT_DOC_FIELDS = {
	"Server Script": ("script_type", "reference_doctype"),
	"Notification": ("document_type",),
}


def apps_to_scan() -> list[str]:
	"""Every app installed on the site except frappe, which the rules are written from."""
	return [app for app in frappe.get_installed_apps() if app != "frappe"]


def bench_apps() -> list[str]:
	"""Every app on the bench, installed on a site or not, except frappe."""
	return [app for app in frappe.get_all_apps(with_internal_apps=False) if app != "frappe"]


def app_package_path(app: str) -> Path | None:
	"""Where the app's code is, or None when this bench does not hold it.

	get_app_path imports the app to find it, so this raises whatever the app's own `__init__` raises."""
	try:
		path = Path(frappe.get_app_path(app))
	except ModuleNotFoundError as error:
		if error.name != app:
			raise
		return None
	# get_app_path answers with the working directory when the app imports as a namespace package,
	# which is what is left of an app whose files are gone.
	return path if (path / "__init__.py").is_file() else None


def build_report(
	rules: list[Rule],
	site: str,
	target: str,
	apps: tuple[str, ...] = (),
	skip_tests: bool = False,
	online: bool = False,
) -> Report:
	"""Scan `apps`, the ones named with --app, or else every app installed on the site, and every script
	stored on the site, then check that the bench can install the target: the named apps, or every app
	on it. Reads only."""
	scanners = Scanners(rules)
	report = Report(site=site, target=target, apps=[], frappe_version=frappe.__version__)
	frappe_major = int(frappe.__version__.split(".")[0])
	scanned = list(apps) or apps_to_scan()
	app_paths = {}
	for app in scanned:
		try:
			app_path = app_package_path(app)
		except Exception as error:  # noqa: BLE001
			report.unreadable_files.append(f"{app}: {type(error).__name__}: {error}")
			continue
		if not app_path:
			report.missing_apps.append(app)
			continue
		report.apps.append(app)
		app_paths[app] = app_path
		scan_app(report, scanners, app, app_path, skip_tests)
	scan_site_scripts(report, scanners)
	report.findings += [replace(finding, source="site") for finding in scanners.schema.scan(site_schema())]
	report.findings += site_records(rules)

	bench_app_paths = dict(app_paths)
	if not apps:
		for app in bench_apps():
			if app in scanned:
				continue
			try:
				app_path = app_package_path(app)
			except Exception as error:  # noqa: BLE001
				report.not_checked.append(
					f"{app}: {type(error).__name__}: {error}, its pyproject.toml and required_apps not checked"
				)
				continue
			if not app_path:
				report.not_checked.append(
					f"{app}: in apps.txt with no code on this bench, its pyproject.toml and required_apps"
					" not checked"
				)
				continue
			bench_app_paths[app] = app_path
	scan_bench(report, scanners.compatibility, bench_app_paths, frappe_major)

	if online:
		from preflight.online_scanner import OnlineScanner, scan_online

		app_roots = {app: app_path.parent for app, app_path in bench_app_paths.items()}
		scan_online(report, OnlineScanner(rules), app_roots, frappe_major)
	move_upstream_findings(report, bench_app_paths, frappe_major, apps)
	move_ran_patch_findings(report, app_paths)
	return report


def scan_bench(report: Report, scanner: CompatibilityScanner, app_paths: dict[str, Path], frappe_major: int):
	"""The bench's Python, and each app's pyproject.toml and required_apps.

	The pyproject.toml of an app on frappe's version branch is not read: the upgrade switches the app to
	the target's branch, which carries its own."""
	report.findings += [
		replace(finding, source="bench") for finding in scanner.scan_environment(platform.python_version())
	]
	apps_on_bench = set(frappe.get_all_apps(with_internal_apps=False))
	unread: dict[str, list[str]] = {}
	for app, app_path in app_paths.items():
		app_root = app_path.parent
		if (app_root / "pyproject.toml").is_file():
			branch = checked_out_branch(app_root)
			if not branch:
				reason = "no branch checked out" if (app_root / ".git").exists() else "not a git checkout"
				unread.setdefault(reason, []).append(app)
			elif not is_frappe_branch(branch, frappe_major):
				scan_pyproject(report, scanner, app, app_root)
		hooks = app_path / "hooks.py"
		if hooks.is_file():
			file = str(hooks.relative_to(app_root))
			source = hooks.read_text(encoding="utf-8", errors="replace")
			try:
				findings = scanner.scan_required_apps(source, file, apps_on_bench)
			except SyntaxError:
				if f"{app}/{file}" not in report.unparsable_files:
					report.unparsable_files.append(f"{app}/{file}")
				continue
			add_findings(report, findings, source, app)
	for reason, apps in unread.items():
		report.not_checked.append(
			f"pyproject.toml of {', '.join(apps)}: {reason}, requires-python, frappe bound and dependency pins"
			" not checked"
		)


def move_upstream_findings(
	report: Report, app_paths: dict[str, Path], frappe_major: int, apps: tuple[str, ...]
):
	"""Set aside the findings of each app on the version branch of the frappe the bench runs: the upgrade
	replaces its code with upstream's on the target's branch. Not for an app named with --app, nor for
	one --online found no target branch for. An app with no branch checked out, as on Frappe Cloud, cannot
	be told apart: its findings stay counted, and not_checked says so."""
	kept = set(apps) | {
		finding.app for finding in report.findings if finding.rule.match.type == "target_branch"
	}
	found = {finding.app for finding in report.findings}
	unbranched = []
	for app, app_path in app_paths.items():
		if app in kept:
			continue
		branch = checked_out_branch(app_path.parent)
		if branch and is_frappe_branch(branch, frappe_major):
			report.upstream_apps[app] = branch
		elif not branch and app in found:
			unbranched.append(app)
	if unbranched:
		report.not_checked.append(
			f"{', '.join(unbranched)}: no branch checked out to show whether the upgrade replaces their"
			" code, so their findings are counted; pass --app for each of your own apps to leave the rest out"
		)
	report.upstream_findings = [finding for finding in report.findings if finding.app in report.upstream_apps]
	report.findings = [finding for finding in report.findings if finding.app not in report.upstream_apps]


def move_ran_patch_findings(report: Report, app_paths: dict[str, Path]):
	"""Set aside the findings in patches the site has run, which never run again, and mark the ones in
	patches still to run, which `bench migrate` runs on the target, where they raise.

	Patches are told apart the way frappe's patch_handler tells them: by the patches.txt line, stripped,
	`#` comment and all, against the Patch Log rows not skipped; a `finally:` patch is logged without
	the tag. A module patch is its file; an `execute:` patch is its patches.txt line."""
	executed = set(frappe.get_all("Patch Log", filters={"skipped": 0}, pluck="patch"))
	ran, pending = set(), set()
	for app, app_path in app_paths.items():
		try:
			text = (app_path / "patches.txt").read_text(encoding="utf-8", errors="replace")
		except OSError:
			continue
		for number, line in enumerate(text.split("\n"), 1):
			patch = line.strip()
			if not patch or patch.startswith(("#", ";", "[")):
				continue
			if patch.startswith("finally:"):
				patch = patch.replace("finally:", "")
			if patch.startswith("execute:"):
				places = {(app, f"{app_path.name}/patches.txt", number)}
			else:
				module = patch.split(maxsplit=1)[0].replace(".", "/")
				package = module.split("/")[0]
				places = {(package, f"{module}.py", None), (package, f"{module}/__init__.py", None)}
			(ran if patch in executed else pending).update(places)
	counted = []
	for finding in report.findings:
		places = {(finding.app, finding.file, finding.line), (finding.app, finding.file, None)}
		if places & pending:
			counted.append(replace(finding, stops_migrate=True))
		elif places & ran:
			report.ran_patch_findings.append(finding)
		else:
			counted.append(finding)
	report.findings = counted


def scan_site_scripts(report: Report, scanners: Scanners):
	for label, language, script, docs in site_scripts():
		if language == "python":
			findings = scan_python(report, scanners.python, label, script, docs=docs) or []
		else:
			findings = scanners.js.scan(script, label)
		add_findings(report, findings, script, source="site")


def site_schema() -> list[SchemaRecord]:
	"""Every doctype named by a Custom Field or a Property Setter on the site, with the field of it each
	names: the one a Custom Field is inserted after, the one a Property Setter changes. One record holds
	both, as a doctype rule matches every record of its doctype."""
	records = []
	for row in frappe.get_all(
		"Custom Field",
		fields=["name", "dt", "fieldname", "fieldtype", "options", "insert_after"],
		order_by="name",
	):
		label = f"Custom Field: {row.name}"
		snippet = f"custom field {row.fieldname} on {row.dt}"
		if row.insert_after:
			snippet += f" after {row.insert_after}"
		records.append(SchemaRecord(label, row.dt, snippet, row.insert_after or ""))
		if row.fieldtype in LINK_FIELDTYPES and row.options:
			records.append(SchemaRecord(label, row.options, f"{row.fieldtype.lower()} field {row.fieldname}"))
	for row in frappe.get_all("Property Setter", fields=["name", "doc_type", "field_name"], order_by="name"):
		snippet = f"property setter on {row.doc_type}"
		if row.field_name:
			snippet += f" field {row.field_name}"
		records.append(
			SchemaRecord(f"Property Setter: {row.name}", row.doc_type, snippet, row.field_name or "")
		)
	return records


def record_filters(
	doctype: str, filters: tuple[tuple[str, str | int | float], ...], title_field: str
) -> dict | None:
	"""The rule's filters as frappe.get_all takes them on `doctype`, or None when there is nothing to query.

	A filter on a field of the doctype a Link field points to (`module.custom`) becomes the names of the
	records it selects there. None when a table lacks a column the filters read, or when a linked filter
	selects no record, since `in` an empty list matches an empty column on frappe v15."""
	columns = {fieldname.partition(".")[0] for fieldname, _ in filters}
	if not {title_field, *columns} <= set(frappe.db.get_db_table_columns(f"tab{doctype}")):
		return None
	resolved = {}
	for fieldname, value in filters:
		link_field, _, linked_field = fieldname.partition(".")
		if not linked_field:
			resolved[fieldname] = value
			continue
		field = frappe.get_meta(doctype).get_field(link_field)
		if not (
			field
			and field.fieldtype == "Link"
			and linked_field in frappe.db.get_db_table_columns(f"tab{field.options}")
		):
			return None
		names = frappe.get_all(field.options, filters={linked_field: value}, pluck="name")
		if not names:
			return None
		resolved[link_field] = ["in", names]
	return resolved


def site_records(rules: list[Rule]) -> list[Finding]:
	"""The records each site_record rule's filters select, one query per doctype and one per linked filter.
	A doctype whose table is missing, or lacks a column the rule reads, is not queried: its app is not
	installed, or the site never had the field."""
	findings = []
	for rule in rules:
		if rule.match.type != "site_record":
			continue
		title_field = rule.match.title_field or "name"
		conditions = [f"{fieldname} = {value!r}" for fieldname, value in rule.match.filters]
		for doctype in rule.match.doctypes:
			filters = record_filters(doctype, rule.match.filters, title_field)
			if filters is None:
				continue
			findings += [
				Finding(
					rule=rule,
					file=f"{doctype}: {row.name}",
					line=None,
					snippet=", ".join((str(row[title_field]), *conditions)),
					source="site",
				)
				for row in frappe.get_all(
					doctype, filters=filters, fields=["name", title_field], order_by="name"
				)
			]
	return findings


def site_scripts() -> list[tuple[str, str, str, dict[str, set[str]]]]:
	"""Every script on the site that can run, as (label, language, code, the doctypes of the docs it runs
	with by name). The label names the field as well where the doctype holds code in two."""
	fields_per_doctype = Counter(doctype for doctype, *_ in SCRIPT_FIELDS)
	scripts = []
	for doctype, field, language, filters in SCRIPT_FIELDS:
		suffix = f" ({field})" if fields_per_doctype[doctype] > 1 else ""
		scripts += [
			(
				f"{doctype}: {row.name}{suffix}",
				language,
				row[field],
				{"doc": {row.reference_doctype}}
				if row.get("script_type") == "DocType Event"
				else {"doc": {row.document_type}}
				if row.get("document_type")
				else {},
			)
			for row in frappe.get_all(
				doctype,
				fields=["name", field, *SCRIPT_DOC_FIELDS.get(doctype, ())],
				filters=filters,
				order_by="name",
			)
			if row[field]
		]
	return scripts
