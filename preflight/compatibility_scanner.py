import ast
import re
from pathlib import Path

import semantic_version
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

try:
	import tomllib
except ModuleNotFoundError:  # python 3.10, which frappe v15 still runs on
	import tomli as tomllib

from preflight.hooks_scanner import assigned_names
from preflight.models import Finding, Rule

PYTHON_RELEASES = tuple(Version(f"3.{minor}.{patch}") for minor in range(8, 30) for patch in (0, 99))


def parse_required_app_name(requirement: str) -> str:
	"""Mirrors frappe.installer.parse_required_app_name from v16, which v15 does not have."""
	name = requirement.rstrip("/").split("#")[0]
	name = name.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
	return name.split("@")[0].removesuffix(".git")


def checked_out_branch(app_root: Path) -> str | None:
	"""The branch the app's checkout is on, or None when HEAD is detached or there is no checkout. A
	worktree's `.git` is a file naming the git dir that holds its HEAD."""
	git_dir = app_root / ".git"
	try:
		if git_dir.is_file():
			git_dir = app_root / git_dir.read_text(encoding="utf-8").removeprefix("gitdir:").strip()
		head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
	except OSError:
		return None
	return head.removeprefix("ref: refs/heads/") if head.startswith("ref: refs/heads/") else None


def is_frappe_branch(branch: str, frappe_major: int) -> bool:
	"""True on the version branch of the frappe the bench runs (version-15-hotfix on v15), or on a branch
	cut from it (mergify/bp/version-15-hotfix/pr-1), which the upgrade switches to the target's. An
	app's own release branch, like Insights' version-3, stays."""
	return bool(re.search(rf"(^|/)version-{frappe_major}(-hotfix|-beta)?(/|$)", branch))


def declared_dependencies(app_root: Path) -> set[str]:
	"""The canonical names of the packages the app asks pip for: its pyproject's `[project].dependencies`,
	and a requirements.txt, which older apps still install from. A file that cannot be read declares
	nothing."""
	requirements = []
	try:
		data = tomllib.loads((app_root / "pyproject.toml").read_text(encoding="utf-8"))
		requirements += data.get("project", {}).get("dependencies", [])
	except (OSError, ValueError):
		pass
	try:
		lines = (app_root / "requirements.txt").read_text(encoding="utf-8").splitlines()
		requirements += [line.partition("#")[0].strip() for line in lines]
	except (OSError, ValueError):
		pass
	names = set()
	for requirement in requirements:
		try:
			names.add(canonicalize_name(Requirement(requirement).name))
		except InvalidRequirement:
			continue
	return names


def shares_a_python(first: SpecifierSet, second: SpecifierSet) -> bool:
	"""Whether any Python release satisfies both. Each minor is tried at .0 and .99, so a bound on a
	patch release (">=3.14.2") still counts its minor."""
	return any(first.contains(release) and second.contains(release) for release in PYTHON_RELEASES)


def named_versions(specifiers: SpecifierSet) -> set[Version]:
	"""Each version `specifiers` names, and one just above it, which `>` and `!=` let through."""
	versions = set()
	for specifier in specifiers:
		try:
			version = Version(specifier.version.removesuffix(".*"))
		except InvalidVersion:
			continue
		versions |= {version, Version(f"{version.base_version}.1")}
	return versions


def can_coexist(first: SpecifierSet, second: SpecifierSet) -> bool:
	"""Whether a version satisfies both. Only 0 and the `named_versions` of either are tried, which is
	exact for the pins frappe writes (`==`, `~=`, `>=` with `<`); a pair whose shared versions all lie
	past a `!=` wildcard (`!=1.*`) reads as a clash."""
	both = first & second
	return any(
		both.contains(version, prereleases=True)
		for version in {Version("0"), *named_versions(first), *named_versions(second)}
	)


def quoted_line(lines: list[str], start: int, text: str) -> int | None:
	"""The first line from `start` on that quotes `text`, or None when none does."""
	return next(
		(
			number
			for number, line in enumerate(lines, 1)
			if number >= start and (f'"{text}"' in line or f"'{text}'" in line)
		),
		None,
	)


def toml_line(lines: list[str], table: str, key: str) -> int | None:
	"""The line `key` is set on inside `[table]`, or None when it is not found; tomllib keeps no
	positions."""
	current = ""
	for number, line in enumerate(lines, 1):
		stripped = line.strip()
		if stripped.startswith("["):
			current = stripped.strip("[]").strip()
		elif current == table and stripped.partition("=")[0].strip().strip("\"'") == key:
			return number
	return None


def finding_on(rule: Rule, file: str, lines: list[str], line: int | None) -> Finding:
	return Finding(rule=rule, file=file, line=line, snippet=lines[line - 1].strip() if line else "")


class CompatibilityScanner:
	"""Rules on whether the bench can install the target: its Python, and each app's pyproject.toml
	and required_apps."""

	def __init__(self, rules: list[Rule]):
		self.rules_by_type: dict[str, list[Rule]] = {}
		for rule in rules:
			self.rules_by_type.setdefault(rule.match.type, []).append(rule)

	def scan_environment(self, python_version: str) -> list[Finding]:
		return [
			Finding(rule=rule, file="env/bin/python", line=None, snippet=f"Python {python_version}")
			for rule in self.rules_by_type.get("bench_python", ())
			if not SpecifierSet(rule.match.python).contains(python_version)
		]

	def scan_pyproject(self, source: str, file: str) -> list[Finding]:
		"""Raises ValueError when the file, or a bound or dependency in it, does not parse."""
		data = tomllib.loads(source)
		lines = source.splitlines()
		findings = []

		if requires_python := data.get("project", {}).get("requires-python"):
			line = toml_line(lines, "project", "requires-python")
			findings += [
				finding_on(rule, file, lines, line)
				for rule in self.rules_by_type.get("requires_python", ())
				if not shares_a_python(SpecifierSet(requires_python), SpecifierSet(rule.match.python))
			]

		bench = data.get("tool", {}).get("bench", {})
		if frappe_bound := bench.get("frappe-dependencies", {}).get("frappe"):
			line = toml_line(lines, "tool.bench.frappe-dependencies", "frappe")
			bound = semantic_version.SimpleSpec(frappe_bound)
			findings += [
				finding_on(rule, file, lines, line)
				for rule in self.rules_by_type.get("frappe_bound", ())
				if semantic_version.Version(rule.match.frappe) not in bound
			]

		dependencies_line = toml_line(lines, "project", "dependencies")
		for rule in self.rules_by_type.get("dependency_pins", ()):
			pins = {canonicalize_name(pin.name): pin for pin in map(Requirement, rule.match.dependencies)}
			for dependency in data.get("project", {}).get("dependencies", ()):
				requirement = Requirement(dependency)
				pin = pins.get(canonicalize_name(requirement.name))
				if pin and not can_coexist(requirement.specifier, pin.specifier):
					findings.append(
						Finding(
							rule=rule,
							file=file,
							line=quoted_line(lines, dependencies_line or 1, dependency),
							snippet=f"{dependency} (frappe pins {pin})",
						)
					)
		return findings

	def scan_required_apps(self, source: str, file: str, apps_on_bench: set[str]) -> list[Finding]:
		"""Raises SyntaxError if `source` is not valid Python."""
		lines = source.splitlines()
		findings = []
		for node in ast.parse(source, filename=file).body:
			if not any(name.id == "required_apps" for name in assigned_names(node)):
				continue
			if not isinstance(node.value, ast.List | ast.Tuple):
				continue
			for entry in node.value.elts:
				if (
					isinstance(entry, ast.Constant)
					and isinstance(entry.value, str)
					and parse_required_app_name(entry.value) not in apps_on_bench
				):
					findings += [
						finding_on(rule, file, lines, entry.lineno)
						for rule in self.rules_by_type.get("required_apps", ())
					]
		return findings
