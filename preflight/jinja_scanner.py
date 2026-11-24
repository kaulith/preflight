"""Doctypes and doc fields read by Jinja templates. A template is parsed and walked, never compiled or
rendered: it is code from an app or a site, and a scan must not run it."""

import json
import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import replace
from typing import NamedTuple

from jinja2 import Environment, TemplateSyntaxError, nodes
from jinja2.lexer import newline_re
from jinja2.visitor import NodeVisitor

from preflight.js_scanner import SNIPPET_LENGTH
from preflight.models import Finding, Rule, child_doctypes, rules_by_doctype, rules_by_doctype_field
from preflight.python_scanner import DOC_APIS
from preflight.sources import MALFORMED_RECORD

# What marks a template Jinja cannot read as a frappe client-side microtemplate: a `{%=` or `{%~` tag, or
# a tag opening or closing a JavaScript block, `{% if(!doc) { %}` and `{% } %}`.
MICROTEMPLATE = re.compile(r"\{%[=~]|\{\s*%\}|\{%\s*\}")
# The print format builder's fieldtypes whose entry holds a template frappe renders with the doc.
BUILDER_HTML_FIELDTYPES = ("HTML", "Custom HTML")
# The match types about how a template renders, rather than the doctypes and fields it names.
RENDER_MATCH_TYPES = ("template_global", "template_fetched_doc")


class Held(NamedTuple):
	"""What a name or an expression may hold: docs of these doctypes, a table of rows of these, or a doc
	the template fetched through a template_fetched_doc rule's APIs."""

	docs: frozenset[str] = frozenset()
	rows: frozenset[str] = frozenset()
	fetched: bool = False


NOTHING = Held()


def reads_rendering(rule: Rule) -> bool:
	"""True for a rule about how a template renders or runs its SQL."""
	return rule.match.type in RENDER_MATCH_TYPES or rule.match.safe_sql_only


def renders_html(print_format: Mapping) -> bool:
	"""True when frappe renders the print format's html as Jinja: a custom format, or a standard one with
	no builder layout. A JS or report format renders in the browser, a raw one prints its raw_commands, and
	a beta one its layout."""
	if (
		print_format.get("print_format_type") == "JS"
		or print_format.get("print_format_for") == "Report"
		or print_format.get("raw_printing")
		or print_format.get("print_format_builder_beta")
	):
		return False
	return bool(print_format.get("custom_format")) or (
		print_format.get("standard") == "Yes" and not print_format.get("format_data")
	)


def renders_layout(print_format: Mapping) -> bool:
	"""True when frappe prints the print format from its builder layout, which a custom format overrides
	unless the layout is the beta builder's."""
	return (
		bool(print_format.get("format_data"))
		and print_format.get("print_format_for") != "Report"
		and bool(print_format.get("print_format_builder_beta") or not print_format.get("custom_format"))
	)


def renders_subject(notification: Mapping) -> bool:
	"""True when the notification's channel renders its subject: Slack and SMS send only the message."""
	return notification.get("channel") not in ("Slack", "SMS")


def builder_fields(layout) -> Iterable[dict]:
	"""The field entries of a builder layout: a list of them, or the beta builder's `sections` of `columns`
	of `fields`."""
	if isinstance(layout, dict):
		return [
			field
			for section in layout["sections"]
			for column in section["columns"]
			for field in column["fields"]
		]
	return layout


def bind(names: dict[str, Held], target: nodes.Node, held: Held = NOTHING):
	"""Give the target name what it now holds. Names unpacked from a tuple hold nothing known."""
	if isinstance(target, nodes.Name):
		names[target.name] = held
	for name in target.find_all(nodes.Name):
		names[name.name] = NOTHING


def argument(node: nodes.Call, keyword: str) -> nodes.Expr | None:
	"""The first argument a call passes, or the one passed by `keyword`."""
	if node.args:
		return node.args[0]
	return next((passed.value for passed in node.kwargs if passed.key == keyword), None)


def string_value(node: nodes.Node | None) -> str | None:
	if isinstance(node, nodes.Const) and isinstance(node.value, str):
		return node.value
	return None


def loaded_doctype(node: nodes.Call) -> str | None:
	"""The doctype a call that loads or makes a doc names as a literal, `frappe.get_doc("Lead", name)`."""
	method = node.node
	if (
		isinstance(method, nodes.Getattr)
		and isinstance(method.node, nodes.Name)
		and f"{method.node.name}.{method.attr}" in DOC_APIS
	):
		return string_value(argument(node, "doctype"))
	return None


def global_path(node: nodes.Expr) -> str | None:
	"""The dotted path of a name and its attributes, `frappe.db.commit`."""
	attributes = []
	while isinstance(node, nodes.Getattr):
		attributes.append(node.attr)
		node = node.node
	return ".".join((node.name, *reversed(attributes))) if isinstance(node, nodes.Name) else None


def bound_names(tree: nodes.Template) -> set[str]:
	"""The names the template's macros and imports bind, which hide a render global of that name."""
	names = set()
	for node in tree.find_all((nodes.Macro, nodes.Import, nodes.FromImport)):
		if isinstance(node, nodes.FromImport):
			names.update(name[1] if isinstance(name, tuple) else name for name in node.names)
		else:
			names.add(node.target if isinstance(node, nodes.Import) else node.name)
	return names


class JinjaScanner:
	"""The rules a template can match, as the tables a template visitor reads."""

	def __init__(self, rules: list[Rule]):
		self.environment = Environment()
		self.doctype_rules = rules_by_doctype(rules)
		self.field_rules = rules_by_doctype_field(rules)
		self.child_doctypes = child_doctypes(rules)
		self.global_rules: dict[str, list[Rule]] = {}
		self.fetched_doc_rules = [rule for rule in rules if rule.match.type == "template_fetched_doc"]
		self.fetch_apis = frozenset(path for rule in self.fetched_doc_rules for path in rule.match.paths)
		self.safe_sql_rules = [
			([re.compile(pattern) for pattern in rule.match.patterns], rule)
			for rule in rules
			if rule.match.safe_sql_only
		]
		for rule in rules:
			if rule.match.type == "template_global":
				for path in rule.match.paths:
					self.global_rules.setdefault(path, []).append(rule)

	def scan(
		self, source: str, file: str, doc_doctypes: Collection[str] = (), restricted: bool = False
	) -> list[Finding]:
		"""Raises jinja2.TemplateSyntaxError if `source` is not a valid template. A microtemplate is not
		Jinja, so it has no findings. `doc_doctypes` are the doctypes of the `doc` the template renders with.
		`restricted` says frappe already renders it with restrict_globals on the version being left, so
		the target takes nothing from it."""
		try:
			tree = self.environment.parse(source)
		except TemplateSyntaxError:
			if MICROTEMPLATE.search(source):
				return []
			raise
		lines = newline_re.sub("\n", source).split("\n")
		visitor = TemplateVisitor(
			self, file, lines, {"doc": Held(docs=frozenset(doc_doctypes))}, restricted, bound_names(tree)
		)
		visitor.visit(tree)
		return list(visitor.findings.values())

	def scan_layout(self, format_data: str, file: str, doctype: str) -> tuple[list[Finding], int]:
		"""The fields a print format's builder layout names and those its HTML entries read, each with no
		line, and how many of those templates do not parse. A layout that cannot be read counts as one."""
		found: list[Finding] = []
		unparsed = 0
		try:
			for field in builder_fields(json.loads(format_data)):
				fieldname = field.get("fieldname")
				child = self.child_doctypes.get((doctype, fieldname))
				columns = field.get("visible_columns") or field.get("table_columns") or ()
				for field_doctype, name in (
					(doctype, fieldname),
					*((child, column.get("fieldname")) for column in columns),
				):
					found += [
						Finding(rule=rule, file=file, line=None, snippet=f'"fieldname": "{name}"')
						for rule in self.field_rules.get((field_doctype, name), ())
					]
				if field.get("fieldtype") in BUILDER_HTML_FIELDTYPES:
					try:
						found += self.scan(field.get("html") or field.get("options") or "", file, (doctype,))
					except (TemplateSyntaxError, RecursionError):
						unparsed += 1
		except MALFORMED_RECORD:
			return [], 1
		return list(dict.fromkeys(replace(finding, line=None) for finding in found)), unparsed


class TemplateVisitor(NodeVisitor):
	"""Walks one template, keeping what each name holds the way Jinja scopes it: a for, with, macro, call,
	filter or block body binds names of its own, and an if does not."""

	def __init__(
		self,
		rules: JinjaScanner,
		file: str,
		lines: list[str],
		names: dict[str, Held],
		restricted: bool = False,
		shadowed: Collection[str] = (),
	):
		self.rules = rules
		self.file = file
		self.lines = lines
		self.names = names
		self.template_names = names
		self.restricted = restricted
		self.shadowed = shadowed
		self.findings: dict[tuple[str, int], Finding] = {}

	def report(self, rules: Iterable[Rule], line: int):
		for rule in rules:
			snippet = self.lines[line - 1].strip()[:SNIPPET_LENGTH]
			self.findings.setdefault(
				(rule.id, line), Finding(rule=rule, file=self.file, line=line, snippet=snippet)
			)

	def report_field(self, doc: nodes.Expr, fieldname: str | None, line: int):
		for doctype in sorted(self.held(doc).docs):
			self.report(self.rules.field_rules.get((doctype, fieldname), ()), line)

	def table_rows(self, doc: nodes.Expr, fieldname: str | None) -> frozenset[str]:
		"""The child doctype of the table field `fieldname` on the doc `doc` holds."""
		return frozenset(
			child
			for doctype in self.held(doc).docs
			if (child := self.rules.child_doctypes.get((doctype, fieldname)))
		)

	def held(self, node: nodes.Node) -> Held:
		"""What the expression holds: a bound name, a table of a doc, one row or a slice of a table, or a
		doc a call loads or fetches."""
		if isinstance(node, nodes.Name):
			return self.names.get(node.name, NOTHING)
		if isinstance(node, nodes.Getattr):
			return Held(rows=self.table_rows(node.node, node.attr))
		if isinstance(node, nodes.Getitem):
			if isinstance(node.arg, nodes.Slice):
				return Held(rows=self.held(node.node).rows)
			if (fieldname := string_value(node.arg)) is not None:
				return Held(rows=self.table_rows(node.node, fieldname))
			return Held(docs=self.held(node.node).rows)
		if isinstance(node, nodes.Call):
			fetched = self.fetches_doc(node)
			if doctype := loaded_doctype(node):
				return Held(docs=frozenset((doctype,)), fetched=fetched)
			if fetched:
				return Held(fetched=True)
			if isinstance(node.node, nodes.Getattr) and node.node.attr == "get":
				return Held(rows=self.table_rows(node.node.node, string_value(argument(node, "key"))))
		return NOTHING

	def is_global(self, name: str) -> bool:
		"""False when the template binds `name` itself, so it is not frappe's global."""
		return name not in self.names and name not in self.shadowed

	def fetches_doc(self, node: nodes.Call) -> bool:
		path = global_path(node.node) if self.rules.fetch_apis else None
		return path in self.rules.fetch_apis and self.is_global(path.partition(".")[0])

	def report_fetched_doc(self, read: nodes.Getattr, called: bool):
		"""A read on a fetched doc that lands on a dict method, or a call to a method SafeDoc lacks."""
		if self.restricted:
			return
		for rule in self.rules.fetched_doc_rules:
			breaks = (
				read.attr not in (*rule.match.keys, *rule.match.allowed_methods)
				if called
				else read.attr in rule.match.keys
			)
			if breaks and self.held(read.node).fetched:
				self.report((rule,), read.lineno)

	def report_global_call(self, node: nodes.Call):
		"""A call to a global the target takes from this template, and SQL sent through frappe's guard,
		which every template's `frappe.db.sql` is."""
		path = global_path(node.node)
		if not path or not self.is_global(path.partition(".")[0]):
			return
		if not self.restricted:
			self.report(self.rules.global_rules.get(path, ()), node.lineno)
		if path == "frappe.db.sql" and (query := string_value(argument(node, "query"))) is not None:
			self.report(
				(
					rule
					for patterns, rule in self.rules.safe_sql_rules
					if any(pattern.search(query) for pattern in patterns)
				),
				node.lineno,
			)

	def visit_scope(self, body: Iterable[nodes.Node], names: dict[str, Held]):
		"""Visit `body` in a scope that starts from `names`; what it binds is gone after it."""
		outer = self.names
		self.names = dict(names)
		for node in body:
			self.visit(node)
		self.names = outer

	def visit_Getattr(self, node: nodes.Getattr):
		self.report_field(node.node, node.attr, node.lineno)
		self.report_fetched_doc(node, called=False)
		self.generic_visit(node)

	def visit_Getitem(self, node: nodes.Getitem):
		self.report_field(node.node, string_value(node.arg), node.lineno)
		self.generic_visit(node)

	def visit_Call(self, node: nodes.Call):
		"""`doc.get("f")` reads a field and `frappe.get_doc("X", name)` a doctype. A method's own name is no
		field, so only what it is called on is visited."""
		method = node.node
		if isinstance(method, nodes.Getattr) and method.attr == "get":
			self.report_field(method.node, string_value(argument(node, "key")), node.lineno)
		if isinstance(method, nodes.Getattr):
			self.report_fetched_doc(method, called=True)
		self.report_global_call(node)
		if rule := self.rules.doctype_rules.get(loaded_doctype(node)):
			self.report((rule,), node.lineno)
		self.visit(method.node if isinstance(method, nodes.Getattr) else method)
		for child in node.iter_child_nodes(exclude=("node",)):
			self.visit(child)

	def visit_Assign(self, node: nodes.Assign):
		self.visit(node.node)
		bind(self.names, node.target, self.held(node.node))

	def visit_AssignBlock(self, node: nodes.AssignBlock):
		if node.filter:
			self.visit(node.filter)
		self.visit_scope(node.body, self.names)
		bind(self.names, node.target)

	def visit_If(self, node: nodes.If):
		"""An if has no scope, so after it a name may hold what any branch left it holding, or what it held
		before when no branch ran."""
		self.visit(node.test)
		for branch in node.elif_:
			self.visit(branch.test)
		outer = self.names
		ends = []
		for body in (node.body, *(branch.body for branch in node.elif_), node.else_):
			self.names = dict(outer)
			for child in body:
				self.visit(child)
			ends.append(self.names)
		self.names = outer
		for name in {name for end in ends for name in end}:
			held = [end.get(name, NOTHING) for end in ends]
			outer[name] = Held(
				frozenset().union(*(each.docs for each in held)),
				frozenset().union(*(each.rows for each in held)),
				any(each.fetched for each in held),
			)

	def visit_For(self, node: nodes.For):
		self.visit(node.iter)
		scope = dict(self.names)
		bind(scope, node.target, Held(docs=self.held(node.iter).rows))
		self.visit_scope([*([node.test] if node.test else ()), *node.body], scope)
		self.visit_scope(node.else_, self.names)

	def visit_With(self, node: nodes.With):
		scope = dict(self.names)
		for target, value in zip(node.targets, node.values):
			self.visit(value)
			bind(scope, target, self.held(value))
		self.visit_scope(node.body, scope)

	def visit_Macro(self, node: nodes.Macro | nodes.CallBlock):
		for default in node.defaults:
			self.visit(default)
		scope = dict(self.names)
		for parameter in node.args:
			bind(scope, parameter)
		self.visit_scope(node.body, scope)

	def visit_CallBlock(self, node: nodes.CallBlock):
		self.visit(node.call)
		self.visit_Macro(node)

	def visit_FilterBlock(self, node: nodes.FilterBlock):
		self.visit(node.filter)
		self.visit_scope(node.body, self.names)

	def visit_Block(self, node: nodes.Block):
		"""A block sees the template's top-level names, and the names around it only when it is scoped."""
		self.visit_scope(node.body, self.names if node.scoped else self.template_names)
