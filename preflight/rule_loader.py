import re
from pathlib import Path
from typing import NamedTuple

import semantic_version
import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet

from preflight.models import FIX_TIMINGS, MATCH_TYPES, SEVERITIES, Match, Rule, RuleSet

RULES_PATH = Path(__file__).parent / "rules"
TARGET = re.compile(r"v\d+")
RULESET_FILE = "target.yaml"
DOCTYPE_FIELD = re.compile(r"[^.]+\.\w+")
FIELDNAME = re.compile(r"\w+")
FILTER_FIELDNAME = re.compile(r"\w+(?:\.\w+)?")
URL_HOSTS = ("private",)


class RuleError(Exception):
	pass


class MatchKeys(NamedTuple):
	required: tuple[str, ...]
	optional: tuple[str, ...] = ()


def invalid_text(key: str, value) -> str | None:
	return None if isinstance(value, str) and value.strip() else f"{key} must be non-empty text"


def invalid_severity(key: str, value) -> str | None:
	return None if value in SEVERITIES else f"{key} must be one of {SEVERITIES}, got {value!r}"


def invalid_string_list(key: str, value) -> str | None:
	if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
		return None
	return f"{key} must be a non-empty list of strings"


def invalid_positive_number(key: str, value) -> str | None:
	if isinstance(value, int) and not isinstance(value, bool) and value > 0:
		return None
	return f"{key} must be a number above 0, got {value!r}"


def first_invalid_pattern(patterns: tuple[str, ...]) -> str | None:
	for pattern in patterns:
		try:
			re.compile(pattern)
		except re.error as e:
			return f"match.patterns: {pattern!r} is not a valid regex, {e}"
	return None


def invalid_patterns(key: str, value) -> str | None:
	return invalid_string_list(key, value) or first_invalid_pattern(value)


def invalid_requirements(key: str, value) -> str | None:
	if problem := invalid_string_list(key, value):
		return problem
	for requirement in value:
		try:
			Requirement(requirement)
		except InvalidRequirement as e:
			return f"{key}: {requirement!r} is not a requirement, {e}"
	return None


def invalid_python_specifier(key: str, specifier) -> str | None:
	problem = f"{key} must be a Python version specifier such as '>=3.14', got {specifier!r}"
	if not isinstance(specifier, str) or not specifier:
		return problem
	try:
		SpecifierSet(specifier)
	except InvalidSpecifier:
		return problem
	return None


def invalid_node_specifier(key: str, specifier) -> str | None:
	problem = f"{key} must be a node version specifier such as '>=24', got {specifier!r}"
	if not isinstance(specifier, str) or not specifier:
		return problem
	try:
		SpecifierSet(specifier)
	except InvalidSpecifier:
		return problem
	return None


def invalid_doctype_fields(key: str, value) -> str | None:
	if problem := invalid_string_list(key, value):
		return problem
	for entry in value:
		if not DOCTYPE_FIELD.fullmatch(entry):
			return f"{key}: {entry!r} must name a doctype and a field, such as 'Sales Invoice.due_date'"
	return None


def invalid_fieldname(key: str, value) -> str | None:
	if isinstance(value, str) and FIELDNAME.fullmatch(value):
		return None
	return f"{key} must be a field name such as 'document_type', got {value!r}"


def invalid_filters(key: str, value) -> str | None:
	if not isinstance(value, dict) or not value:
		return f"{key} must be a non-empty mapping of field names to values"
	for fieldname, filter_value in value.items():
		if not (isinstance(fieldname, str) and FILTER_FIELDNAME.fullmatch(fieldname)):
			return (
				f"{key} key must be a field name such as 'allowed', or a Link field and a field of the doctype"
				f" it links to such as 'module.custom', got {fieldname!r}"
			)
		if not isinstance(filter_value, (str, int, float)):
			return f"{key}.{fieldname} must be one value, got {filter_value!r}"
	return None


def invalid_url_host(key: str, value) -> str | None:
	return None if value in URL_HOSTS else f"{key} must be one of {URL_HOSTS}, got {value!r}"


def invalid_fix(key: str, value) -> str | None:
	return None if value in FIX_TIMINGS else f"{key} must be one of {FIX_TIMINGS}, got {value!r}"


def invalid_frappe_version(key: str, version) -> str | None:
	try:
		semantic_version.Version(version)
	except (ValueError, TypeError):
		return f"{key} must be a frappe version such as '16.53.0', got {version!r}"
	return None


MATCH_KEY_CHECKS = {
	"paths": invalid_string_list,
	"patterns": invalid_patterns,
	"keys": invalid_string_list,
	"doctypes": invalid_string_list,
	"fields": invalid_doctype_fields,
	"filters": invalid_filters,
	"title_field": invalid_fieldname,
	"with_kwargs": invalid_string_list,
	"with_positional_args": invalid_positive_number,
	"returns": invalid_positive_number,
	"url_host": invalid_url_host,
	"python": invalid_python_specifier,
	"frappe": invalid_frappe_version,
	"node": invalid_node_specifier,
	"branch": invalid_text,
	"dependencies": invalid_requirements,
}

MATCH_TYPE_KEYS = {
	"import_path": MatchKeys(("paths",)),
	"call": MatchKeys(("paths",), ("with_kwargs", "with_positional_args", "url_host", "returns")),
	"pattern": MatchKeys(("patterns",)),
	"string_contains": MatchKeys(("paths",)),
	"hook_key": MatchKeys(("keys",)),
	"override_subclass": MatchKeys(("keys",)),
	"returns_none": MatchKeys(("keys",)),
	"unreadable_function": MatchKeys(("keys",)),
	"missing_hook": MatchKeys(("keys", "paths")),
	"doctype": MatchKeys(("doctypes",)),
	"doctype_field": MatchKeys(("fields",)),
	"select_field": MatchKeys(("patterns",)),
	"undeclared_import": MatchKeys(("paths", "dependencies")),
	"site_record": MatchKeys(("doctypes",), ("filters", "title_field")),
	"bench_python": MatchKeys(("python",)),
	"requires_python": MatchKeys(("python",)),
	"frappe_bound": MatchKeys(("frappe",)),
	"dependency_pins": MatchKeys(("dependencies",)),
	"required_apps": MatchKeys(()),
	"bench_node": MatchKeys(("node",)),
	"target_branch": MatchKeys(("branch",)),
	"dependency_wheels": MatchKeys(("python",)),
}


def invalid_match(key: str, match) -> str | None:
	if not isinstance(match, dict):
		return f"{key} must be a mapping with a type"
	if match.get("type") not in MATCH_TYPES:
		return f"{key}.type must be one of {MATCH_TYPES}, got {match.get('type')!r}"
	required, optional = MATCH_TYPE_KEYS[match["type"]]
	if unknown := [name for name in match if name not in ("type", *required, *optional)]:
		allowed = ", ".join(("type", *required, *optional))
		return f"{key}.{unknown[0]} is not a key of a {match['type']} rule, which takes {allowed}"
	for name in (*required, *(name for name in optional if name in match)):
		if problem := MATCH_KEY_CHECKS[name](f"{key}.{name}", match.get(name)):
			return problem
	return None


RULE_KEY_CHECKS = {
	"id": invalid_text,
	"title": invalid_text,
	"severity": invalid_severity,
	"match": invalid_match,
	"message": invalid_text,
	"replacement": invalid_text,
	"references": invalid_string_list,
}

OPTIONAL_RULE_KEY_CHECKS = {
	"fix": invalid_fix,
	"shim": invalid_text,
}


def invalid_rule(data, file_stem: str) -> str | None:
	keys = ", ".join((*RULE_KEY_CHECKS, *OPTIONAL_RULE_KEY_CHECKS))
	if not isinstance(data, dict):
		return f"invalid rule, expected the keys {keys}"
	if unknown := [key for key in data if key not in RULE_KEY_CHECKS and key not in OPTIONAL_RULE_KEY_CHECKS]:
		return f"{unknown[0]} is not a key of a rule, which takes {keys}"
	for key, check in RULE_KEY_CHECKS.items():
		if problem := check(key, data.get(key)):
			return problem
	for key, check in OPTIONAL_RULE_KEY_CHECKS.items():
		if key in data and (problem := check(key, data[key])):
			return problem
	if data["id"] != file_stem:
		return f"id {data['id']!r} must match the file name"
	return None


def first_shared_doctype(rules: list[Rule]) -> str | None:
	"""Two doctype rules on one doctype would shadow each other: the scanners key a doctype to one rule."""
	claimed: dict[str, str] = {}
	for rule in rules:
		if rule.match.type != "doctype":
			continue
		for doctype in rule.match.doctypes:
			if doctype in claimed:
				return f"{rule.id}: doctype {doctype!r} is already matched by {claimed[doctype]}"
			claimed[doctype] = rule.id
	return None


def released_targets(rules_path: Path = RULES_PATH) -> list[str]:
	"""The targets whose target.yaml says they are released, which is what --target offers."""
	targets = []
	for path in sorted(rules_path.iterdir()):
		if path.is_dir() and TARGET.fullmatch(path.name):
			try:
				released = load_ruleset(path.name, rules_path).released
			except RuleError:
				continue
			if released:
				targets.append(path.name)
	return targets


def load_ruleset(target: str, rules_path: Path = RULES_PATH) -> RuleSet:
	"""The target's `target.yaml`: whether the version is out, and when and against what its rules were
	last checked."""
	path = rules_path / target / RULESET_FILE
	try:
		data = yaml.safe_load(path.read_text(encoding="utf-8"))
	except OSError as e:
		raise RuleError(f"{target}: no {RULESET_FILE}") from e
	except (yaml.YAMLError, UnicodeDecodeError) as e:
		raise RuleError(f"{target}/{RULESET_FILE}: invalid, {type(e).__name__}: {e}") from e
	if not isinstance(data, dict) or set(data) != {"released", "checked", "against"}:
		raise RuleError(f"{target}/{RULESET_FILE}: must hold exactly the keys released, checked, against")
	if not isinstance(data["released"], bool):
		raise RuleError(f"{target}/{RULESET_FILE}: released must be true or false")
	for key in ("checked", "against"):
		if problem := invalid_text(key, data[key]):
			raise RuleError(f"{target}/{RULESET_FILE}: {problem}, quoted when it is a date")
	return RuleSet(target=target, released=data["released"], checked=data["checked"], against=data["against"])


def load_rules(target: str, rules_path: Path = RULES_PATH) -> list[Rule]:
	ruleset = rules_path / target
	rules = (
		[load_rule(path) for path in sorted(ruleset.glob("*.yaml")) if path.name != RULESET_FILE]
		if TARGET.fullmatch(target)
		else []
	)
	if not rules:
		available = ", ".join(released_targets(rules_path))
		raise RuleError(f"No rules for target {target!r}. Available targets: {available}")
	load_ruleset(target, rules_path)
	if problem := first_shared_doctype(rules):
		raise RuleError(problem)
	return rules


def load_rule(path: Path) -> Rule:
	try:
		data = yaml.safe_load(path.read_text(encoding="utf-8"))
	except (yaml.YAMLError, UnicodeDecodeError) as e:
		raise RuleError(f"{path.name}: invalid rule, {type(e).__name__}: {e}") from e
	if problem := invalid_rule(data, path.stem):
		raise RuleError(f"{path.name}: {problem}")
	match = {key: tuple(value) if isinstance(value, list) else value for key, value in data["match"].items()}
	if filters := match.get("filters"):
		match["filters"] = tuple(filters.items())
	return Rule(
		id=data["id"],
		title=data["title"],
		severity=data["severity"],
		match=Match(**match),
		message=data["message"].strip(),
		replacement=data["replacement"].strip(),
		references=tuple(data["references"]),
		fix=data.get("fix", ""),
		shim=data.get("shim", "").strip(),
	)
