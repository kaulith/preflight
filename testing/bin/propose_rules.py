"""The doctypes and data fields a release removed that no rule covers yet.

Diffs the DocType JSON of two sets of app trees and says what the trees show about where each one
went. A tree is an app package directory, read as data: nothing in it is imported or run. It
proposes; it writes no rule.

	python testing/bin/propose_rules.py --before <tree>... --after <tree>... --target v16 [--json]
"""

import argparse
import ast
import json
import sys
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from preflight.models import rules_by_doctype, rules_by_doctype_field
from preflight.rule_loader import RuleError, load_rules

LAYOUT_FIELDTYPES = frozenset(
	("Section Break", "Column Break", "Tab Break", "Fold", "Heading", "HTML", "Button", "Image")
)
TABLE_FIELDTYPES = ("Table", "Table MultiSelect")
RENAME_ARGUMENTS = {
	"rename_field": ("doctype", "old_fieldname", "new_fieldname"),
	"rename_doc": ("doctype", "old", "new"),
}


@dataclass(frozen=True)
class Doctype:
	name: str
	file: str
	fields: dict[str, str]
	child_tables: frozenset[str]


@dataclass(frozen=True)
class Rename:
	"""A rename call with literal names. `doctype` is None when the call computes it."""

	function: str
	doctype: str | None
	old: str
	new: str
	patch: str

	@property
	def call(self) -> tuple:
		return self.function, self.doctype, self.old, self.new


def app_doctypes(tree: Path) -> dict[str, Doctype]:
	"""Every doctype in the tree, by name, with its data fields. A file that cannot be read stops the
	run: its doctype would otherwise be reported as removed."""
	doctypes = {}
	for path in sorted(tree.glob("**/doctype/*/*.json")):
		if path.stem != path.parent.name:
			continue
		try:
			data = json.loads(path.read_text(encoding="utf-8"))
		except (OSError, ValueError) as e:
			sys.exit(f"{path}: unreadable, {e}")
		if not isinstance(data, dict) or data.get("doctype") != "DocType":
			continue
		fields = [field for field in data.get("fields", ()) if field.get("fieldname")]
		doctypes[data["name"]] = Doctype(
			name=data["name"],
			file=str(path.relative_to(tree.parent)),
			fields={
				field["fieldname"]: field.get("fieldtype", "Data")
				for field in fields
				if field.get("fieldtype", "Data") not in LAYOUT_FIELDTYPES
			},
			child_tables=frozenset(
				field["options"]
				for field in fields
				if field.get("fieldtype") in TABLE_FIELDTYPES and field.get("options")
			),
		)
	return doctypes


def patch_sources(tree: Path) -> Iterator[tuple[str, str]]:
	"""(file, source) of everything the tree's patches.txt runs. A patch file it does not list never
	runs, so it shows nothing about where a field went."""
	patches = tree / "patches.txt"
	if not patches.exists():
		return
	for line in patches.read_text(encoding="utf-8").splitlines():
		entry = line.partition("#")[0].strip()
		if entry.startswith("execute:"):
			yield str(patches.relative_to(tree.parent)), entry.removeprefix("execute:")
		elif entry and not entry.startswith("["):
			module = tree.parent / f"{entry.replace('.', '/')}.py"
			if module.is_file():
				yield str(module.relative_to(tree.parent)), module.read_text(encoding="utf-8")


def literal_argument(call: ast.Call, position: int, keyword: str) -> str | None:
	if len(call.args) > position:
		node = call.args[position]
	else:
		node = next((kw.value for kw in call.keywords if kw.arg == keyword), None)
	return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def rename_calls(tree: Path) -> tuple[list[Rename], list[str]]:
	"""The rename_field and DocType rename_doc calls the tree's patches make, and the patches that
	could not be parsed."""
	renames, unparsable = [], []
	for file, source in patch_sources(tree):
		try:
			with warnings.catch_warnings():
				warnings.simplefilter("ignore", SyntaxWarning)
				module = ast.parse(source)
		except (SyntaxError, ValueError):
			unparsable.append(file)
			continue
		for call in ast.walk(module):
			if not isinstance(call, ast.Call):
				continue
			function = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
			if function not in RENAME_ARGUMENTS:
				continue
			doctype, old, new = (
				literal_argument(call, position, keyword)
				for position, keyword in enumerate(RENAME_ARGUMENTS[function])
			)
			if old and new and (function == "rename_field" or doctype == "DocType"):
				renames.append(Rename(function, doctype, old, new, file))
	return renames, unparsable


def evidence(kind: str, to: str, where: str) -> dict:
	return {"kind": kind, "to": to, "where": where}


def sorted_evidence(entries: list[dict]) -> list[dict]:
	return sorted(entries, key=lambda entry: (entry["kind"], entry["to"], entry["where"]))


def doctype_evidence(
	name: str, app: str, before: dict, after: dict, now: dict, renames: list[Rename]
) -> list[dict]:
	"""A rename to a doctype that exists after, or the same doctype in another app's tree: moved
	there, or already there when this app's copy went."""
	found = [
		evidence("rename_doc", rename.new, rename.patch)
		for rename in renames
		if rename.function == "rename_doc" and rename.old == name and rename.new in now
	]
	found += [
		evidence(
			"already_in_app" if name in before.get(other, ()) else "moved_app", other, doctypes[name].file
		)
		for other, doctypes in after.items()
		if other != app and name in doctypes
	]
	return sorted_evidence(found)


def field_evidence(
	old: Doctype, doctype: Doctype, fieldname: str, was: dict, now: dict, renames: list[Rename]
) -> list[dict]:
	"""A rename to a field the doctype has after, or a field of this name that a child table or a
	sibling table gained. One that table already had shows nothing: rows share names like `amount`."""
	name = doctype.name
	before_fields = old.fields

	def gained(table: str) -> bool:
		return (
			table in now
			and fieldname in now[table].fields
			and fieldname not in (was[table].fields if table in was else ())
		)

	found = [
		evidence("rename_field", rename.new, rename.patch)
		for rename in renames
		if rename.function == "rename_field"
		and rename.old == fieldname
		and rename.new in doctype.fields
		and (rename.doctype == name or (rename.doctype is None and rename.new not in before_fields))
	]
	siblings = (
		{table for parent in now.values() if name in parent.child_tables for table in parent.child_tables}
		- doctype.child_tables
		- {name}
	)
	found += [evidence("on_child", table, now[table].file) for table in doctype.child_tables if gained(table)]
	found += [evidence("on_sibling", table, now[table].file) for table in siblings if gained(table)]
	return sorted_evidence(found)


def propose(before_trees: list[Path], after_trees: list[Path], target: str) -> dict:
	rules = load_rules(target)
	doctype_rules = rules_by_doctype(rules)
	field_rules = rules_by_doctype_field(rules)
	before = {tree.name: app_doctypes(tree) for tree in before_trees}
	after = {tree.name: app_doctypes(tree) for tree in after_trees}
	was = {name: doctype for doctypes in before.values() for name, doctype in doctypes.items()}
	now = {name: doctype for doctypes in after.values() for name, doctype in doctypes.items()}

	old_calls, unparsable = set(), []
	for tree in before_trees:
		calls, failed = rename_calls(tree)
		old_calls |= {rename.call for rename in calls}
		unparsable += failed
	renames = []
	for tree in after_trees:
		calls, failed = rename_calls(tree)
		renames += [rename for rename in calls if rename.call not in old_calls]
		unparsable += failed

	doctypes, fields = [], []
	removed_doctypes = removed_fields = 0
	for app, app_before in before.items():
		for name, doctype in app_before.items():
			if name not in after[app]:
				removed_doctypes += 1
				if name not in doctype_rules:
					doctypes.append(
						{
							"app": app,
							"doctype": name,
							"evidence": doctype_evidence(name, app, before, after, now, renames),
						}
					)
			current = after[app].get(name) or now.get(name)
			if not current:
				continue
			for fieldname, fieldtype in doctype.fields.items():
				if fieldname in current.fields:
					continue
				removed_fields += 1
				if (name, fieldname) not in field_rules:
					fields.append(
						{
							"app": app,
							"doctype": name,
							"field": fieldname,
							"fieldtype": fieldtype,
							"evidence": field_evidence(doctype, current, fieldname, was, now, renames),
						}
					)
	doctypes.sort(key=lambda row: (row["app"], row["doctype"]))
	fields.sort(key=lambda row: (row["app"], row["doctype"], row["field"]))
	return {
		"target": target,
		"before": sorted(before),
		"after": sorted(after),
		"totals": {
			"doctypes_removed": removed_doctypes,
			"doctypes_without_rule": len(doctypes),
			"doctypes_without_rule_or_evidence": sum(not row["evidence"] for row in doctypes),
			"fields_removed": removed_fields,
			"fields_without_rule": len(fields),
			"fields_without_rule_or_evidence": sum(not row["evidence"] for row in fields),
		},
		"doctypes": doctypes,
		"fields": fields,
		"unparsable_patches": sorted(set(unparsable)),
	}


def describe(entries: list[dict]) -> str:
	return "; ".join(f"{e['kind']} {e['to']} ({e['where']})" for e in entries) or "no evidence"


def table(result: dict) -> str:
	lines = []
	for app in result["before"]:
		removed = {row["doctype"]: row for row in result["doctypes"] if row["app"] == app}
		by_doctype: dict[str, list[dict]] = {}
		for row in result["fields"]:
			if row["app"] == app:
				by_doctype.setdefault(row["doctype"], []).append(row)
		lines.append(app)
		for name in sorted(set(removed) | set(by_doctype)):
			status = f": removed, {describe(removed[name]['evidence'])}" if name in removed else ""
			lines.append(f"  {name}{status}")
			lines += [
				f"    {row['field']} ({row['fieldtype']}): {describe(row['evidence'])}"
				for row in by_doctype.get(name, ())
			]
		lines.append("")
	totals = result["totals"]
	lines.append(
		f"doctypes: {totals['doctypes_removed']} removed, {totals['doctypes_without_rule']} with no rule, "
		f"{totals['doctypes_without_rule_or_evidence']} of those with no evidence"
	)
	lines.append(
		f"data fields: {totals['fields_removed']} removed, {totals['fields_without_rule']} with no rule, "
		f"{totals['fields_without_rule_or_evidence']} of those with no evidence"
	)
	if result["unparsable_patches"]:
		lines.append(f"patches not parsed: {', '.join(result['unparsable_patches'])}")
	return "\n".join(lines)


def app_trees(parser: argparse.ArgumentParser, option: str, paths: list[Path]) -> list[Path]:
	trees = sorted((path.resolve() for path in paths), key=lambda tree: tree.name)
	for tree in trees:
		if not tree.is_dir():
			parser.error(f"{option}: {tree} is not a directory")
	if len({tree.name for tree in trees}) != len(trees):
		parser.error(f"{option}: two trees for one app")
	return trees


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="List removed doctypes and fields no rule covers.")
	parser.add_argument("--before", nargs="+", type=Path, required=True, help="app package directories")
	parser.add_argument("--after", nargs="+", type=Path, required=True, help="app package directories")
	parser.add_argument("--target", required=True)
	parser.add_argument("--json", action="store_true")
	args = parser.parse_args()
	before_trees = app_trees(parser, "--before", args.before)
	after_trees = app_trees(parser, "--after", args.after)
	if missing := {tree.name for tree in before_trees} - {tree.name for tree in after_trees}:
		parser.error(f"--after: no tree for {', '.join(sorted(missing))}")
	try:
		result = propose(before_trees, after_trees, args.target)
	except RuleError as e:
		parser.error(str(e))
	print(json.dumps(result, indent="\t", sort_keys=True) if args.json else table(result))
