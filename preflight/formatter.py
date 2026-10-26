import json
import platform
import re
from collections import Counter
from pathlib import Path
from textwrap import indent

import click

from preflight import __version__
from preflight.models import SEVERITIES, Finding, Report, Rule, meets_severity

SEVERITY_COLORS = {"error": "red", "warning": "yellow", "info": "cyan"}
FIX_LABELS = {"before": "Fix before upgrading", "with-upgrade": "Fix with the upgrade", "": "Fix"}
SHIM_HEADING = "Shim that runs on both versions"
JSON_SCHEMA_VERSION = 1
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_LEVELS = {"error": "error", "warning": "warning", "info": "note"}
CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def python_version() -> str:
	"""The interpreter doing the parsing, which is what decides whether a file can be read."""
	return platform.python_version()


def printable(text: str) -> str:
	"""Snippets, paths and reasons come from the code and site being scanned; a control character in them is
	printed escaped, so an escape sequence cannot rewrite the terminal or its clipboard."""
	return CONTROL_CHARACTER.sub(lambda match: repr(match[0])[1:-1], text)


def file_label(finding: Finding) -> str:
	"""An app's file from the bench's apps directory, which holds each app's repository; a site record or
	a part of the bench by its name."""
	return f"{finding.app}/{finding.file}" if finding.app else finding.file


def location(finding: Finding) -> str:
	"""Doctype fields, site records and the bench have no line; everything else read from a file does."""
	return f"{file_label(finding)}:{finding.line}" if finding.line else file_label(finding)


def at_or_above(findings: list[Finding], minimum: str) -> list[Finding]:
	return [finding for finding in findings if meets_severity(finding.rule.severity, minimum)]


def left_out(heading: str, items: list[str], note: str) -> list[str]:
	"""A block naming what the counts leave out, which is what they have to be read against."""
	return [
		"",
		click.style(f"{heading} ({len(items)})", fg="yellow", bold=True),
		*(f"    {printable(item)}" for item in items),
		f"  {note}",
	]


def format_report(report: Report, minimum: str = "info", fail_on: str = "error") -> str:
	"""The report as a terminal page, printing only findings of `minimum` severity or worse."""
	findings = at_or_above(report.findings, minimum)
	scope = report.site or "code only"
	title = (
		f"Preflight {scope}: frappe {report.frappe_version} → {report.target}"
		if report.frappe_version
		else f"Preflight {scope} → {report.target}"
	)
	lines = [click.style(title, bold=True)]
	if report.ruleset:
		lines.append(f"Rules checked {report.ruleset.checked} against {report.ruleset.against}")
	lines.append(f"Apps scanned: {', '.join(report.apps) or 'none'}")

	findings_by_rule: dict[Rule, list[Finding]] = {}
	for finding in findings:
		findings_by_rule.setdefault(finding.rule, []).append(finding)

	counts = {}
	for level in SEVERITIES:
		rules = sorted(
			(rule for rule in findings_by_rule if rule.severity == level), key=lambda rule: rule.id
		)
		if not rules:
			continue
		counts[level] = sum(len(findings_by_rule[rule]) for rule in rules)
		heading = f"{level.upper()} ({counts[level]})"
		lines += ["", click.style(heading, fg=SEVERITY_COLORS[level], bold=True)]
		for rule in rules:
			lines += ["", f"  {click.style(rule.id, bold=True)}: {rule.title}", f"  {rule.message}"]
			for finding in sorted(
				findings_by_rule[rule], key=lambda finding: (file_label(finding), finding.line or 0)
			):
				pending = (
					click.style("  [pending patch, stops bench migrate]", fg="red")
					if finding.stops_migrate
					else ""
				)
				lines.append(f"    {printable(location(finding))}  {printable(finding.snippet)}{pending}")
			lines.append(f"  {FIX_LABELS[rule.fix]}: {rule.replacement}")
			if rule.shim:
				lines += [f"  {SHIM_HEADING}:", indent(rule.shim, "      ")]

	if report.upstream_apps:
		upstream = at_or_above(report.upstream_findings, minimum)
		lines += left_out(
			"Upstream apps, not counted",
			[
				f"{app} on {branch}: {sum(finding.app == app for finding in upstream)} found"
				for app, branch in report.upstream_apps.items()
			],
			f"These apps are on frappe's own version branch: switching them to the {report.target} branch"
			" replaces this code, so what is found in it is upstream's to fix and not in the counts below."
			" --app <name> lists an app's findings.",
		)

	if ran_patches := at_or_above(report.ran_patch_findings, minimum):
		lines += left_out(
			"Rules hit in patches already run, not counted",
			[
				f"{rule_id}: {count} found"
				for rule_id, count in sorted(Counter(finding.rule.id for finding in ran_patches).items())
			],
			"Patch Log records these patches as run, so bench migrate does not run them again and what they"
			f" call can be gone on {report.target}. They are not in the counts below.",
		)

	if report.missing_apps:
		lines += left_out(
			"Not scanned, no code on this bench",
			report.missing_apps,
			"The site lists these apps as installed and this bench does not hold them, so nothing"
			" of theirs was read. Their customisations and site scripts still were.",
		)

	if report.unparsable_files:
		lines += left_out(
			f"Not scanned, python {python_version()} could not parse them",
			report.unparsable_files,
			"A file this python cannot read counts as clean, so the counts below are short by"
			" whatever those files hold. Either the file is broken, or it is written for a newer"
			" python than the bench runs.",
		)

	if report.unreadable_files:
		lines += left_out(
			"Not scanned, could not be read",
			report.unreadable_files,
			"Each is named with the reason. Nothing in them was checked, so the counts below are short by"
			" whatever they hold; an app is listed here when importing it fails.",
		)

	if report.not_checked:
		lines += left_out(
			"Not checked",
			report.not_checked,
			"Each names what was skipped and why.",
		)

	hidden = len(report.findings) - len(findings)
	lines.append("")
	if counts:
		lines.append(", ".join(f"{count} {level}" for level, count in counts.items()))
		if hidden:
			lines.append(f"{hidden} more below {minimum}, not shown.")
	elif hidden:
		lines.append(f"No findings at or above {minimum}, and {hidden} below it, not shown.")
	else:
		clean = "No known incompatibilities found"
		if report.missing_apps or report.unparsable_files or report.unreadable_files or report.not_checked:
			clean += " in what was scanned"
		lines.append(click.style(f"{clean}.", fg="green"))
	dropped = [
		f"{count} {reason}"
		for count, reason in (
			(report.suppressed, "suppressed by an ignore comment"),
			(report.baselined, "in the baseline"),
		)
		if count
	]
	if dropped:
		lines.append(f"{' and '.join(dropped)}, not counted.")
	lines.append("Only APIs covered by the rules are checked; a clean report does not make the upgrade safe.")
	return "\n".join(lines)


def json_finding(finding: Finding) -> dict:
	rule = finding.rule
	return {
		"rule": rule.id,
		"severity": rule.severity,
		"title": rule.title,
		"message": rule.message,
		"replacement": rule.replacement,
		"fix": rule.fix or None,
		"shim": rule.shim or None,
		"references": list(rule.references),
		"app": finding.app,
		"source": finding.source,
		"file": finding.file,
		"line": finding.line,
		"snippet": finding.snippet,
		"stops_migrate": finding.stops_migrate,
	}


def format_json(report: Report, minimum: str = "info", fail_on: str = "error") -> str:
	"""The same report as one JSON object, for CI to read off stdout.

	`schema_version` goes up when a key is removed or changes meaning; a new key can arrive without it.
	`summary` counts what the lists hold, so `upstream` and `ran_patches` are at or above `severity` too.
	"""
	findings = at_or_above(report.findings, minimum)
	upstream = at_or_above(report.upstream_findings, minimum)
	ran_patches = at_or_above(report.ran_patch_findings, minimum)
	return json.dumps(
		{
			"schema_version": JSON_SCHEMA_VERSION,
			"preflight_version": __version__,
			"site": report.site,
			"target": report.target,
			"rules": (
				{"checked": report.ruleset.checked, "against": report.ruleset.against}
				if report.ruleset
				else None
			),
			"python": python_version(),
			"frappe_version": report.frappe_version or None,
			"severity": minimum,
			"fail_on": fail_on,
			"verdict": "fail" if report.fails(fail_on) else "pass",
			"summary": {
				**{
					level: sum(finding.rule.severity == level for finding in findings) for level in SEVERITIES
				},
				"below_severity": len(report.findings) - len(findings),
				"suppressed": report.suppressed,
				"baselined": report.baselined,
				"upstream": len(upstream),
				"ran_patches": len(ran_patches),
			},
			"apps": report.apps,
			"missing_apps": report.missing_apps,
			"findings": [json_finding(finding) for finding in findings],
			"upstream": [
				{
					"app": app,
					"branch": branch,
					"findings": [json_finding(finding) for finding in upstream if finding.app == app],
				}
				for app, branch in report.upstream_apps.items()
			],
			"ran_patch_findings": [json_finding(finding) for finding in ran_patches],
			"unparsable_files": report.unparsable_files,
			"unreadable_files": report.unreadable_files,
			"not_checked": report.not_checked,
		},
		indent=2,
	)


def format_html(report: Report, minimum: str = "info", fail_on: str = "error") -> str:
	"""The same report as one page that fetches nothing, with the JSON embedded for its script to render.

	`<` is escaped so a `</script>` inside a snippet cannot close the block holding the JSON.
	"""
	page = (Path(__file__).parent / "report.html").read_text(encoding="utf-8")
	return page.replace("{{ report }}", format_json(report, minimum, fail_on).replace("<", "\\u003c"))


def format_sarif(report: Report, minimum: str = "info", fail_on: str = "error") -> str:
	"""The counted findings as SARIF 2.1.0, for code scanning to annotate the lines they are on.

	Code scanning rejects a result with no file, so site records, the bench and an app's upstream
	remote are left out and only counted in a notification. It also requires a start line, so a
	finding in a file with no line of its own, like a key missing from pyproject.toml, is placed on
	line 1. With one app scanned, as `--path .` from its checkout, a file is from the app's repository
	root, which is the checkout's; with several, from the bench's apps directory.
	"""
	shown = at_or_above(report.findings, minimum)
	findings = [
		finding for finding in shown if finding.source == "app" and finding.rule.match.type != "target_branch"
	]
	rules = sorted({finding.rule for finding in findings}, key=lambda rule: rule.id)
	descriptors = []
	for rule in rules:
		help_text = f"{FIX_LABELS[rule.fix]}: {rule.replacement}"
		if rule.shim:
			help_text += f"\n\n{SHIM_HEADING}:\n{rule.shim}"
		urls = [reference for reference in rule.references if reference.startswith(("http://", "https://"))]
		descriptors.append(
			{
				"id": rule.id,
				"shortDescription": {"text": rule.title},
				"fullDescription": {"text": rule.message},
				"help": {"text": help_text},
				**({"helpUri": urls[0]} if urls else {}),
				"defaultConfiguration": {"level": SARIF_LEVELS[rule.severity]},
			}
		)
	run = {
		"tool": {"driver": {"name": "preflight", "version": __version__, "rules": descriptors}},
		"results": [
			{
				"ruleId": finding.rule.id,
				"ruleIndex": rules.index(finding.rule),
				"level": SARIF_LEVELS[finding.rule.severity],
				"message": {
					"text": finding.rule.message
					+ (
						f" The patch has not run yet, so bench migrate runs it on {report.target} and stops on it."
						if finding.stops_migrate
						else ""
					)
				},
				"locations": [
					{
						"physicalLocation": {
							"artifactLocation": {
								"uri": finding.file if len(report.apps) == 1 else file_label(finding)
							},
							"region": {"startLine": finding.line or 1},
						}
					}
				],
			}
			for finding in findings
		],
	}
	if without_file := len(shown) - len(findings):
		run["invocations"] = [
			{
				"executionSuccessful": True,
				"toolExecutionNotifications": [
					{
						"level": "note",
						"message": {
							"text": f"{without_file} found on site records, the bench or an app's upstream remote,"
							" not in these results: code scanning places a result in a file of the repository."
							" The text and JSON reports list them."
						},
					}
				],
			}
		]
	return json.dumps({"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": [run]}, indent=2)
