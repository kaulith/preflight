import json
from dataclasses import dataclass
from pathlib import Path

from preflight.models import Finding, Rule, rules_by_doctype, rules_by_doctype_field
from preflight.sources import source_files

# Fieldtypes whose options name a doctype.
LINK_FIELDTYPES = ("Link", "Table", "Table MultiSelect")


@dataclass(frozen=True)
class SchemaRecord:
	"""One place a doctype is named by the schema rather than by code."""

	label: str
	doctype: str
	snippet: str
	fieldname: str = ""


def app_doctype_fields(app_path: Path) -> list[SchemaRecord]:
	"""Every link and table field in the app's own doctypes, as the doctype it points at."""
	records = []
	for path in source_files(app_path, ".json"):
		if path.stem != path.parent.name or path.parent.parent.name != "doctype":
			continue
		try:
			fields = json.loads(path.read_text(encoding="utf-8"))["fields"]
		except (OSError, ValueError, KeyError, TypeError):
			continue
		file = str(path.relative_to(app_path.parent))
		records += [
			SchemaRecord(file, field["options"], f"{field['fieldtype'].lower()} field {field['fieldname']}")
			for field in fields
			if field.get("fieldtype") in LINK_FIELDTYPES and field.get("options")
		]
	return records


class SchemaScanner:
	"""Doctype and doctype field rules, matched against records that name a doctype, or one of its
	fields, rather than against code."""

	def __init__(self, rules: list[Rule]):
		self.rules = rules_by_doctype(rules)
		self.field_rules = rules_by_doctype_field(rules)

	def scan(self, records: list[SchemaRecord]) -> list[Finding]:
		findings = []
		for record in records:
			rules = [self.rules[record.doctype]] if record.doctype in self.rules else []
			if record.fieldname:
				rules += self.field_rules.get((record.doctype, record.fieldname), [])
			findings += [
				Finding(rule=rule, file=record.label, line=None, snippet=record.snippet) for rule in rules
			]
		return findings
