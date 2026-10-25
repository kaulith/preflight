import ast
import re
from collections.abc import Iterator
from pathlib import Path

from preflight.models import Finding, Rule
from preflight.python_scanner import FileVisitor, PythonScanner, controller_name, string_value

# Hooks keyed by doctype name: every one v15 reads, and extend_doctype_class, which v16 added.
DOCTYPE_HOOKS = frozenset(
	{
		"doctype_js",
		"doctype_list_js",
		"doctype_tree_js",
		"doctype_calendar_js",
		"doc_events",
		"override_doctype_class",
		"extend_doctype_class",
		"override_doctype_dashboards",
		"permission_query_conditions",
		"has_permission",
		"has_website_permission",
		"standard_queries",
		"default_log_clearing_doctypes",
		"webform_include_js",
		"webform_include_css",
	}
)

# Hooks that hand the doc of the doctype each entry is keyed by to the function or the class it names.
DOC_HOOKS = frozenset({"doc_events", "override_doctype_class"})

DOTTED_PATH = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")


def assigned_names(node: ast.stmt) -> Iterator[ast.Name]:
	"""The plain names a top-level statement of hooks.py binds."""
	if isinstance(node, ast.Assign):
		targets = node.targets
	elif isinstance(node, ast.AnnAssign):
		targets = [node.target]
	else:
		return
	yield from (target for target in targets if isinstance(target, ast.Name))


def dotted_paths(node: ast.expr) -> Iterator[ast.Constant]:
	"""The strings under `node` that are wholly a dotted path, which is how a hook names a function."""
	for child in ast.walk(node):
		if (
			isinstance(child, ast.Constant)
			and isinstance(child.value, str)
			and DOTTED_PATH.fullmatch(child.value)
		):
			yield child


def hooked_doctypes(app_path: Path) -> dict[str, dict[str, set[str]]]:
	"""The doctypes the app's hooks.py hooks each function to under doc_events, and each class to under
	override_doctype_class, by module and then by name. A hooks.py that cannot be read or parsed hooks none."""
	try:
		tree = ast.parse((app_path / "hooks.py").read_text(encoding="utf-8", errors="replace"))
	except (OSError, SyntaxError):
		return {}
	hooked: dict[str, dict[str, set[str]]] = {}
	for node in tree.body:
		if not (
			any(name.id in DOC_HOOKS for name in assigned_names(node)) and isinstance(node.value, ast.Dict)
		):
			continue
		for key, value in zip(node.value.keys, node.value.values):
			if (doctype := string_value(key)) in (None, "*"):
				continue
			for path in dotted_paths(value):
				module, _, name = path.value.rpartition(".")
				hooked.setdefault(module, {}).setdefault(name, set()).add(doctype)
	return hooked


def returns(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.Return]:
	"""The function's own return statements, leaving out those of a function defined inside it."""
	pending: list[ast.AST] = list(function.body)
	while pending:
		node = pending.pop()
		if isinstance(node, ast.Return):
			yield node
		elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
			pending += ast.iter_child_nodes(node)


def ends_every_path(body: list[ast.stmt]) -> bool:
	"""True when no path through `body` runs past its last statement."""
	return any(ends_path(node) for node in body)


def breaks_out(loop: ast.While) -> bool:
	"""True when a `break` leaves the loop: one in its body, outside the loops nested in it, or in the
	else of a nested loop, which runs in the outer one."""
	pending: list[ast.AST] = list(loop.body)
	while pending:
		node = pending.pop()
		if isinstance(node, ast.Break):
			return True
		if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
			pending += node.orelse
		elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
			pending += ast.iter_child_nodes(node)
	return False


def ends_path(node: ast.stmt) -> bool:
	if isinstance(node, (ast.Return, ast.Raise)):
		return True
	if isinstance(node, ast.If):
		return ends_every_path(node.body) and ends_every_path(node.orelse)
	if isinstance(node, ast.Match):
		return any(
			isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None and case.guard is None
			for case in node.cases
		) and all(ends_every_path(case.body) for case in node.cases)
	if isinstance(node, ast.While):
		return isinstance(node.test, ast.Constant) and node.test.value in (True, 1) and not breaks_out(node)
	if isinstance(node, (ast.With, ast.AsyncWith)):
		return ends_every_path(node.body)
	if isinstance(node, ast.Try):
		return ends_every_path(node.finalbody) or (
			(ends_every_path(node.body) or ends_every_path(node.orelse))
			and all(ends_every_path(handler.body) for handler in node.handlers)
		)
	return (
		isinstance(node, ast.Expr)
		and isinstance(node.value, ast.Call)
		and ast.unparse(node.value.func) in ("frappe.throw", "throw")
	)


def can_return_none(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
	"""True when a path through the function falls off the end, or returns with no value or with None."""
	return not ends_every_path(function.body) or any(
		node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None)
		for node in returns(function)
	)


class OverrideResolver:
	"""Reads the classes and functions a hook names, out of the app's own source."""

	def __init__(self, app_path: Path):
		self.app_path = app_path
		self.parsed: dict[
			Path,
			tuple[dict[str, ast.ClassDef], dict[str, ast.FunctionDef | ast.AsyncFunctionDef], dict[str, str]],
		] = {}

	def module_file(self, parts: tuple[str, ...]) -> Path | None:
		if parts and parts[0] == self.app_path.name:
			parts = parts[1:]
		if not parts:
			return None
		module = self.app_path.joinpath(*parts)
		for candidate in (module.with_suffix(".py"), module / "__init__.py"):
			if candidate.is_file():
				return candidate
		return None

	def imported_from(self, path: Path, node: ast.ImportFrom) -> str:
		"""Where an import statement in `path` reads from, as a path from the app root."""
		package = path.relative_to(self.app_path).parts[:-1]
		base = package[: len(package) - node.level + 1] if node.level else ()
		return ".".join((*base, *(node.module.split(".") if node.module else ())))

	def read(
		self, path: Path
	) -> tuple[dict[str, ast.ClassDef], dict[str, ast.FunctionDef | ast.AsyncFunctionDef], dict[str, str]]:
		"""The classes and top-level functions a file defines, and where each name it imports comes from."""
		if path not in self.parsed:
			try:
				tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
			except SyntaxError:
				self.parsed[path] = ({}, {}, {})
				return self.parsed[path]
			classes: dict[str, ast.ClassDef] = {}
			imports: dict[str, str] = {}
			for node in ast.walk(tree):
				if isinstance(node, ast.ClassDef):
					classes[node.name] = node
				elif isinstance(node, ast.ImportFrom) and (module := self.imported_from(path, node)):
					for alias in node.names:
						imports[alias.asname or alias.name] = f"{module}.{alias.name}"
			functions = {
				node.name: node
				for node in tree.body
				if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
			}
			self.parsed[path] = (classes, functions, imports)
		return self.parsed[path]

	def function(
		self, dotted: str, seen: set[str] | None = None
	) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
		"""The top-level function `dotted` names, followed through the imports that bring it into its
		module, or None when it cannot be read."""
		seen = set() if seen is None else seen
		if dotted in seen:
			return None
		seen.add(dotted)
		*module, name = dotted.split(".")
		path = self.module_file(tuple(module))
		if not path:
			return None
		_, functions, imports = self.read(path)
		if name in functions:
			return functions[name]
		return self.function(imports[name], seen) if name in imports else None

	def ancestors(self, dotted: str, seen: set[str] | None = None) -> set[str] | None:
		"""Every class name above `dotted`, or None when the class cannot be read.

		A class the app does not hold, such as a controller imported from frappe, ends the walk
		under its own name; that name is all the caller needs to compare.
		"""
		seen = set() if seen is None else seen
		if dotted in seen:
			return set()
		seen.add(dotted)
		*module, class_name = dotted.split(".")
		path = self.module_file(tuple(module))
		if not path:
			return None
		classes, _, imports = self.read(path)
		node = classes.get(class_name)
		if not node:
			return None
		names = set()
		for base in node.bases:
			name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
			if not name:
				continue
			imported = imports.get(name)
			names.add(imported.rsplit(".", 1)[-1] if imported else name)
			above = self.ancestors(imported or f"{'.'.join(module)}.{name}", seen)
			if above:
				names |= above
		return names


def overrides_missing_the_controller(
	rule: Rule, node: ast.Assign | ast.AnnAssign, file: str, lines: list[str], app_path: Path
) -> list[Finding]:
	"""One finding per entry whose class is read and does not inherit the doctype's controller."""
	if not isinstance(node.value, ast.Dict):
		return []
	resolver = OverrideResolver(app_path)
	findings = []
	for key, value in zip(node.value.keys, node.value.values, strict=True):
		if not (isinstance(key, ast.Constant) and isinstance(value, ast.Constant)):
			continue
		above = resolver.ancestors(value.value)
		if above is None or controller_name(key.value) in above:
			continue
		findings.append(
			Finding(rule=rule, file=file, line=value.lineno, snippet=lines[value.lineno - 1].strip())
		)
	return findings


def functions_matching(
	rule: Rule, node: ast.Assign | ast.AnnAssign, file: str, lines: list[str], app_path: Path
) -> list[Finding]:
	"""One finding per entry whose function can return None, under a `returns_none` rule, or cannot be
	read, under an `unreadable_function` rule."""
	if not isinstance(node.value, ast.Dict):
		return []
	resolver = OverrideResolver(app_path)
	findings = []
	for value in node.value.values:
		for entry in ast.walk(value):
			if not (isinstance(entry, ast.Constant) and isinstance(entry.value, str)):
				continue
			function = resolver.function(entry.value)
			if function is None:
				matched = rule.match.type == "unreadable_function"
			else:
				matched = rule.match.type == "returns_none" and can_return_none(function)
			if matched:
				findings.append(
					Finding(rule=rule, file=file, line=entry.lineno, snippet=lines[entry.lineno - 1].strip())
				)
	return findings


def keys_naming_a_doctype(
	doctype_rules: dict[str, Rule], node: ast.Assign | ast.AnnAssign, file: str, lines: list[str]
) -> list[Finding]:
	"""One finding per key of a doctype-keyed hook that names a doctype a rule matches."""
	if not isinstance(node.value, ast.Dict):
		return []
	return [
		Finding(rule=rule, file=file, line=key.lineno, snippet=lines[key.lineno - 1].strip())
		for key in node.value.keys
		if isinstance(key, ast.Constant) and (rule := doctype_rules.get(key.value))
	]


class HooksScanner:
	"""Rules keyed on a hook an app declares in its hooks.py."""

	def __init__(self, rules: list[Rule]):
		self.python = PythonScanner(rules)
		self.rules_by_key: dict[str, list[Rule]] = {}
		self.override_rules_by_key: dict[str, list[Rule]] = {}
		self.function_rules_by_key: dict[str, list[Rule]] = {}
		self.missing_hook_rules: list[Rule] = []
		for rule in rules:
			if rule.match.type == "hook_key":
				for key in rule.match.keys:
					self.rules_by_key.setdefault(key, []).append(rule)
			elif rule.match.type == "override_subclass":
				for key in rule.match.keys:
					self.override_rules_by_key.setdefault(key, []).append(rule)
			elif rule.match.type in ("returns_none", "unreadable_function"):
				for key in rule.match.keys:
					self.function_rules_by_key.setdefault(key, []).append(rule)
			elif rule.match.type == "missing_hook":
				self.missing_hook_rules.append(rule)

	def scan(self, source: str, file: str, app_path: Path | None = None) -> list[Finding]:
		"""Raises SyntaxError if `source` is not valid Python.

		`app_path` is what lets an `override_subclass`, `returns_none` or `unreadable_function` rule
		read the class or function the hook names; without it those rules report nothing.
		"""
		lines = source.splitlines()
		findings = []
		paths = FileVisitor(self.python, file, lines)
		for node in ast.parse(source, filename=file).body:
			names = list(assigned_names(node))
			if names and node.value:
				for string in dotted_paths(node.value):
					if not any(path in string.value for path, _ in self.python.string_rules):
						paths.check_path(tuple(string.value.split(".")), string.lineno)
			for name in names:
				findings += [
					Finding(rule=rule, file=file, line=name.lineno, snippet=lines[name.lineno - 1].strip())
					for rule in self.rules_by_key.get(name.id, ())
				]
				if name.id in DOCTYPE_HOOKS:
					findings += keys_naming_a_doctype(self.python.doctype_rules, node, file, lines)
				if app_path:
					for rule in self.override_rules_by_key.get(name.id, ()):
						findings += overrides_missing_the_controller(rule, node, file, lines, app_path)
					for rule in self.function_rules_by_key.get(name.id, ()):
						findings += functions_matching(rule, node, file, lines, app_path)
		return findings + list(paths.findings.values())

	def missing_hooks(self, source: str, file: str, app_path: Path) -> list[Finding]:
		"""One finding per `missing_hook` rule whose files the app ships while its hooks.py declares none of
		the rule's keys, naming the first of those files from the repository root. Raises SyntaxError if
		`source` is not valid Python."""
		declared = {
			name.id for node in ast.parse(source, filename=file).body for name in assigned_names(node)
		}
		findings = []
		for rule in self.missing_hook_rules:
			if not declared.isdisjoint(rule.match.keys):
				continue
			shipped = sorted(
				str(path.relative_to(app_path.parent))
				for pattern in rule.match.paths
				for path in app_path.glob(pattern)
			)
			if shipped:
				more = f" and {len(shipped) - 1} more" if len(shipped) > 1 else ""
				findings.append(Finding(rule=rule, file=file, line=None, snippet=shipped[0] + more))
		return findings
