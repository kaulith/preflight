import ast
import ipaddress
import re
from collections.abc import Collection, Iterable, Iterator, Mapping
from urllib.parse import urlsplit

from preflight.models import Finding, Match, Rule, child_doctypes, rules_by_doctype, rules_by_doctype_field

# Framework APIs whose first argument, or `doctype` keyword, is a doctype name.
DOCTYPE_APIS = frozenset(
	{
		"frappe.get_doc",
		"frappe.get_cached_doc",
		"frappe.get_last_doc",
		"frappe.get_single",
		"frappe.get_single_value",
		"frappe.new_doc",
		"frappe.delete_doc",
		"frappe.reload_doctype",
		"frappe.get_all",
		"frappe.get_list",
		"frappe.get_value",
		"frappe.get_cached_value",
		"frappe.get_meta",
		"frappe.db.get_all",
		"frappe.db.get_list",
		"frappe.db.get_value",
		"frappe.db.get_values",
		"frappe.db.get_single_value",
		"frappe.db.get_singles_dict",
		"frappe.db.set_value",
		"frappe.db.set_single_value",
		"frappe.db.exists",
		"frappe.db.count",
		"frappe.db.delete",
		"frappe.qb.DocType",
		"frappe.qb.from_",
		"frappe.qb.into",
		"frappe.qb.update",
		"frappe.qb.get_query",
	}
)

# Framework APIs that load or make a doc of the doctype their first argument, or `doctype` keyword, names.
DOC_APIS = frozenset(
	{"frappe.get_doc", "frappe.get_cached_doc", "frappe.get_last_doc", "frappe.get_single", "frappe.new_doc"}
)

# Document methods that read or write the field their first argument names, with that argument's keyword.
DOC_FIELD_METHODS = {"get": "key", "set": "key", "db_set": "fieldname"}

# Framework APIs that load `[module]/[dt]/[dn]/[dn].json`, with dt and dn scrubbed.
RELOAD_DOC_APIS = frozenset(
	{"frappe.reload_doc", "frappe.modules.reload_doc", "frappe.modules.utils.reload_doc"}
)

# Query APIs that run frappe.get_list's DatabaseQuery, which takes a dict, or a list of lists, passed as
# the fields for the filters, and the filters then for the fields.
LIST_QUERY_APIS = frozenset({"frappe.get_all", "frappe.get_list", "frappe.db.get_all", "frappe.db.get_list"})
LIST_QUERY_ARGUMENTS = {
	"fields": 1,
	"filters": 2,
	"or_filters": 3,
	"group_by": 4,
	"order_by": 5,
	"pluck": None,
}
VALUE_QUERY_ARGUMENTS = {"filters": 1, "fieldname": 2, "order_by": None}

# The arguments of each doctype API that name fields of its doctype, by keyword, with the position each
# is also taken at, or None for one passed only by keyword.
FIELD_ARGUMENTS = {
	**dict.fromkeys(LIST_QUERY_APIS, LIST_QUERY_ARGUMENTS),
	"frappe.qb.get_query": {"fields": 1, "filters": 2, "order_by": 3, "group_by": 4, "or_filters": None},
	"frappe.get_value": VALUE_QUERY_ARGUMENTS,
	"frappe.db.get_value": VALUE_QUERY_ARGUMENTS,
	"frappe.db.get_values": VALUE_QUERY_ARGUMENTS,
	"frappe.get_cached_value": {"name": 1, "fieldname": 2},
	"frappe.get_single_value": {"fieldname": 1},
	"frappe.db.get_single_value": {"fieldname": 1},
	"frappe.db.set_single_value": {"fieldname": 1},
	"frappe.db.set_value": {"dn": 1, "field": 2},
	"frappe.db.exists": {"dn": 1},
	"frappe.db.count": {"filters": 1},
	"frappe.db.delete": {"filters": 1},
}
# The arguments above that are filters: a dict keyed by field, or a list of conditions.
FILTER_ARGUMENTS = frozenset({"filters", "or_filters", "name", "dn"})

# Query APIs that send their fields through frappe.database.query on v16: the `fields` or `fieldname`
# argument, or what a list query plucks when it passes no fields.
SELECT_FIELD_APIS = frozenset(
	{
		*LIST_QUERY_APIS,
		"frappe.qb.get_query",
		"frappe.get_value",
		"frappe.db.get_value",
		"frappe.db.get_values",
	}
)

FIELD_MARK = re.compile(r"[(),]")

# One field a select, an order by or a group by names: plain or backticked, qualified by its doctype's
# table or not, with an alias or a sort order after it.
FIELD_REFERENCE = re.compile(r"(?:`tab([^`]+)`\.)?`?(\w+)`?(?:\s+as\s+.+|\s+(?:asc|desc))?", re.IGNORECASE)

# Helpers apps call to read the frappe version, such as crm's is_frappe_version("16", above=True).
VERSION_HELPERS = frozenset({"is_frappe_version", "get_frappe_version"})

# A doctype's table named in SQL.
TABLE_NAME = re.compile(r"`tab([^`]+)`")

# Framework APIs that run the SQL text they are given, with the keyword of that argument.
SQL_APIS = {"frappe.db.sql": "query", "frappe.db.multisql": "sql_dict"}

# A server method named in a URL.
API_METHOD = re.compile(r"/api/(?:v\d+/)?method/([\w.]+)")

# Request APIs, with the HTTP method each sends, or None for one that takes it as its first argument.
REQUEST_APIS = {
	"requests.get": "GET",
	"frappe.make_get_request": "GET",
	"frappe.integrations.utils.make_get_request": "GET",
	"requests.request": None,
	"frappe.integrations.utils.make_request": None,
}

IMPORT_ERRORS = frozenset({"ImportError", "ModuleNotFoundError"})

# What parsing a file raises when it cannot be read as code: a null byte, or nesting past the parser's stack.
PYTHON_PARSE_ERRORS = (SyntaxError, ValueError, RecursionError, MemoryError)

LONGEST_ATTRIBUTE_CHAIN = 64

# Framework APIs that resolve a dotted path given as a string.
ATTR_APIS = frozenset(
	{
		"frappe.get_attr",
		"frappe.get_module",
		"frappe.call",
		"frappe.enqueue",
		"frappe.utils.background_jobs.enqueue",
	}
)


def split_fields(text: str) -> list[str]:
	"""frappe.database.query's COMMA_PATTERN, `,\\s*(?![^()]*\\))`: a comma splits unless the next parenthesis
	after it closes. Read from the end, as that regex rescans the rest of the string at every comma."""
	fields = []
	end = len(text)
	inside = False
	for mark in reversed(list(FIELD_MARK.finditer(text))):
		if mark[0] == ",":
			if not inside:
				fields.append(text[mark.end() : end])
				end = mark.start()
		else:
			inside = mark[0] == ")"
	fields.append(text[:end])
	return fields[::-1]


def call_uses_argument(node: ast.Call, match: Match) -> bool:
	"""True when the call passes the argument the rule narrows to, by keyword or by position.

	A rule that narrows to no argument matches every call to the path.
	"""
	if not (match.with_kwargs or match.with_positional_args):
		return True
	if match.with_positional_args and len(node.args) >= match.with_positional_args:
		return True
	keywords = {keyword.arg for keyword in node.keywords}
	return bool(match.with_kwargs) and keywords.issuperset(match.with_kwargs)


def argument(node: ast.Call, position: int | None, keyword: str) -> ast.expr | None:
	"""The argument a call passes in `position`, or by `keyword`."""
	if position is not None and position < len(node.args):
		return node.args[position]
	return next((passed.value for passed in node.keywords if passed.arg == keyword), None)


def string_value(node: ast.expr | None) -> str | None:
	if isinstance(node, ast.Constant) and isinstance(node.value, str):
		return node.value
	return None


def field_text(node: ast.expr | None) -> str | None:
	"""A field string as v16 reads it. An f-string's substitutions read as plain field names, so only the
	SQL written around them decides."""
	if isinstance(node, ast.JoinedStr):
		return "".join(part.value if isinstance(part, ast.Constant) else "field" for part in node.values)
	return string_value(node)


def string_elements(node: ast.expr | None) -> list[ast.expr]:
	"""The strings and f-strings `node` holds: itself, or the elements of a list or tuple."""
	elements = node.elts if isinstance(node, ast.List | ast.Tuple) else [node]
	return [element for element in elements if field_text(element) is not None]


def url_host(url: ast.expr | None) -> str | None:
	"""The host a URL literal names. An f-string names one when its leading literal part holds the host
	whole: followed by the path, or by the port."""
	text = string_value(url.values[0] if isinstance(url, ast.JoinedStr) and url.values else url)
	if not text:
		return None
	try:
		parsed = urlsplit(text)
	except ValueError:
		return None
	runs_into_substitution = (
		isinstance(url, ast.JoinedStr) and len(url.values) > 1 and text.endswith(parsed.netloc)
	)
	if runs_into_substitution and ":" not in parsed.netloc.rpartition("@")[2].rpartition("]")[2]:
		return None
	return parsed.hostname


def names_private_host(node: ast.Call) -> bool:
	"""True when the URL the call requests names localhost or an address that is not globally routable,
	which v16 blocks Server Script requests to. A hostname needs DNS to be judged, so it never matches."""
	host = url_host(argument(node, 0, "url"))
	if not host:
		return False
	if host == "localhost":
		return True
	try:
		return not ipaddress.ip_address(host).is_global
	except ValueError:
		return False


def field_arguments(api: str, node: ast.Call) -> dict[str, ast.expr | None]:
	"""The arguments a doctype API call names fields in, by keyword, with the fields and filters of a list
	query swapped where v16 swaps them."""
	passed = {
		keyword: value
		for keyword, position in FIELD_ARGUMENTS.get(api, {}).items()
		if (value := argument(node, position, keyword)) is not None
	}
	fields = passed.get("fields")
	if api in LIST_QUERY_APIS and (
		isinstance(fields, ast.Dict)
		or (isinstance(fields, ast.List) and fields.elts and isinstance(fields.elts[0], ast.List))
	):
		passed["fields"], passed["filters"] = passed.get("filters"), fields
	return passed


def filter_fields(doctype: str, filters: ast.expr | None) -> Iterator[tuple[str, str, ast.expr]]:
	"""The fields filters name, with the doctype of each: a dict's keys, and the field of each
	[field, operator, value] or [doctype, field, operator, value] condition in a list."""
	if isinstance(filters, ast.Dict):
		yield from ((doctype, key.value, key) for key in filters.keys if string_value(key) is not None)
	elif isinstance(filters, ast.List | ast.Tuple):
		for condition in filters.elts:
			if not isinstance(condition, ast.List | ast.Tuple):
				continue
			names = [string_value(element) for element in condition.elts]
			if len(names) == 4 and names[0] and names[1]:
				yield names[0], names[1], condition.elts[1]
			elif len(names) == 3 and names[0]:
				yield doctype, names[0], condition.elts[0]


def scrub(name: str | None) -> str:
	"""frappe.scrub: `Blog Post` becomes `blog_post`."""
	return (name or "").replace(" ", "_").replace("-", "_").lower()


def controller_name(doctype: str) -> str:
	"""The controller class a doctype resolves to, the way get_controller spells it."""
	return doctype.replace(" ", "").replace("-", "")


def unpacks_result(target: ast.expr, returns: int) -> bool:
	"""True when `target`, what a call's result is assigned to, unpacks a result of `returns` values: into
	`returns` names, or into no more beside a starred name."""
	if not isinstance(target, ast.Tuple | ast.List):
		return False
	starred = any(isinstance(element, ast.Starred) for element in target.elts)
	return len(target.elts) == returns or (starred and len(target.elts) - 1 <= returns)


def catches_import_error(handler: ast.ExceptHandler) -> bool:
	caught = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
	return any(isinstance(error, ast.Name) and error.id in IMPORT_ERRORS for error in caught)


def rejects_select_field(accepted: list[re.Pattern], fields: str) -> bool:
	"""True when one of the fields in `fields`, split the way v16 splits it, matches none of `accepted`."""
	return any(
		not any(pattern.search(field) for pattern in accepted)
		for field in map(str.strip, split_fields(fields))
		if field
	)


class PythonScanner:
	"""The rule set, compiled into the tables a file visitor reads."""

	def __init__(self, rules: list[Rule]):
		self.import_rules: dict[tuple[str, ...], list[Rule]] = {}
		self.call_rules: dict[tuple[str, ...], list[Rule]] = {}
		self.string_rules: list[tuple[str, Rule]] = []
		self.select_field_rules: list[tuple[list[re.Pattern], Rule]] = []
		self.sql_rules: list[tuple[list[re.Pattern], Rule]] = []
		self.http_rules: dict[str, list[Rule]] = {}
		self.doctype_rules = rules_by_doctype(rules)
		self.scrubbed_doctype_rules = {scrub(doctype): rule for doctype, rule in self.doctype_rules.items()}
		self.field_rules = rules_by_doctype_field(rules)
		self.child_doctypes = child_doctypes(rules)
		self.controllers = {
			(scrub(doctype), controller_name(doctype)): doctype
			for doctype, _ in (*self.field_rules, *self.child_doctypes)
		}
		for rule in rules:
			if rule.match.type == "string_contains":
				self.string_rules += [(path, rule) for path in rule.match.paths]
			elif rule.match.type == "select_field":
				self.select_field_rules.append(
					([re.compile(pattern) for pattern in rule.match.patterns], rule)
				)
			elif rule.match.type == "sql_text":
				self.sql_rules.append(([re.compile(pattern) for pattern in rule.match.patterns], rule))
			elif rule.match.type == "http_method":
				for path in rule.match.paths:
					self.http_rules.setdefault(path, []).append(rule)
			elif rule.match.type in ("import_path", "undeclared_import", "call"):
				table = self.call_rules if rule.match.type == "call" else self.import_rules
				for path in rule.match.paths:
					table.setdefault(tuple(path.split(".")), []).append(rule)
		self.longest_import_path = max(map(len, self.import_rules), default=0)

	def scan_sql(self, query: str, file: str) -> list[Finding]:
		"""The sql_text rules a stored query matches, each on the line its first match starts."""
		lines = query.split("\n")
		findings: dict[str, Finding] = {}
		for patterns, rule in self.sql_rules:
			for pattern in patterns:
				if found := pattern.search(query):
					line = query.count("\n", 0, found.start(found.lastindex or 0)) + 1
					findings.setdefault(
						rule.id, Finding(rule=rule, file=file, line=line, snippet=lines[line - 1].strip())
					)
		return list(findings.values())

	def scan(
		self,
		source: str,
		file: str,
		hooked: Mapping[str, Collection[str]] = {},
		docs: Mapping[str, Collection[str]] = {},
	) -> list[Finding]:
		"""Raises SyntaxError if `source` is not valid Python.

		`hooked` holds the doctypes hooks.py hooks each top-level function and class of the file to, and
		`docs` the doctypes of each doc the code runs with under a name of its own, such as the `doc` of a
		DocType Event server script."""
		tree = ast.parse(source, filename=file)
		hooked_nodes = {
			node: hooked[node.name]
			for node in tree.body
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and node.name in hooked
		}
		visitor = FileVisitor(self, file, source.splitlines(), hooked_nodes, docs)
		visitor.visit(tree)
		return list(visitor.findings.values())


class FileVisitor(ast.NodeVisitor):
	def __init__(
		self,
		rules: PythonScanner,
		file: str,
		lines: list[str],
		hooked: Mapping[ast.AST, Collection[str]] = {},
		docs: Mapping[str, Collection[str]] = {},
	):
		self.rules = rules
		self.file = file
		self.lines = lines
		self.hooked = hooked
		self.aliases: dict[str, tuple[str, ...]] = {}
		self.findings: dict[tuple[str, int], Finding] = {}
		self.import_guarded = False
		self.version_guarded = False
		self.version_names: set[str] = set()
		self.local_strings: dict[str, list[ast.expr]] = {}
		self.docs: dict[str, Collection[str]] = dict(docs)
		self.controller_doctypes: Collection[str] = ()
		self.result_targets: dict[ast.Call, list[ast.expr]] = {}
		self.indexed_calls: set[ast.Call] = set()

	def report(self, rules: Iterable[Rule], line: int):
		if self.version_guarded:
			return
		for rule in rules:
			snippet = self.lines[line - 1].strip()
			self.findings.setdefault(
				(rule.id, line), Finding(rule=rule, file=self.file, line=line, snippet=snippet)
			)

	def check_path(self, parts: tuple[str, ...], line: int):
		for end in range(1, min(len(parts), self.rules.longest_import_path) + 1):
			self.report(self.rules.import_rules.get(parts[:end], ()), line)

	def resolve(self, node: ast.expr) -> tuple[str, ...] | None:
		"""The dotted path of a name and its attributes. Past LONGEST_ATTRIBUTE_CHAIN it is None: each shorter
		chain inside it is visited and resolved on its own, so a rule's path is still found."""
		attributes = []
		while isinstance(node, ast.Attribute):
			if len(attributes) == LONGEST_ATTRIBUTE_CHAIN:
				return None
			attributes.append(node.attr)
			node = node.value
		if not isinstance(node, ast.Name):
			return None
		return self.aliases.get(node.id, (node.id,)) + tuple(reversed(attributes))

	def visit_Import(self, node: ast.Import):
		for alias in node.names:
			parts = tuple(alias.name.split("."))
			if not self.import_guarded:
				self.check_path(parts, alias.lineno)
			if alias.asname:
				self.aliases[alias.asname] = parts

	def visit_ImportFrom(self, node: ast.ImportFrom):
		if node.level:
			return
		for alias in node.names:
			parts = (*node.module.split("."), alias.name)
			if not self.import_guarded:
				self.check_path(parts, alias.lineno)
			self.aliases[alias.asname or alias.name] = parts

	def visit_Try(self, node: ast.Try):
		"""An import in a try that catches ImportError, or in that handler, expects the module may be gone."""
		guarded = self.import_guarded
		self.import_guarded = guarded or any(catches_import_error(handler) for handler in node.handlers)
		for statement in node.body:
			self.visit(statement)
		for handler in node.handlers:
			self.import_guarded = guarded or catches_import_error(handler)
			self.visit(handler)
		self.import_guarded = guarded
		for statement in node.orelse + node.finalbody:
			self.visit(statement)

	def reads_frappe_version(self, node: ast.expr) -> bool:
		"""True when the expression reads the frappe version: frappe.__version__, a name bound from it, or a
		helper such as crm's is_frappe_version."""
		return any(
			(
				isinstance(child, ast.Call)
				and getattr(child.func, "attr", getattr(child.func, "id", None)) in VERSION_HELPERS
			)
			or (isinstance(child, ast.Name) and child.id in self.version_names)
			or (
				isinstance(child, ast.Attribute | ast.Name)
				and self.resolve(child) == ("frappe", "__version__")
			)
			for child in ast.walk(node)
		)

	def visit_If(self, node: ast.If | ast.IfExp):
		"""A test of the frappe version picks the code for each version on purpose, so no branch under it is
		reported: the branch for the newer version only calls what that version has."""
		guarded = self.version_guarded
		self.version_guarded = guarded or self.reads_frappe_version(node.test)
		self.generic_visit(node)
		self.version_guarded = guarded

	visit_IfExp = visit_If

	def visit_scope(
		self,
		node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
		docs: dict[str, Collection[str]],
		controller_doctypes: Collection[str],
	):
		"""A scope reads the strings its own local names hold and the docs they are bound to, not those of
		the code around it."""
		outer = self.local_strings, self.docs, self.controller_doctypes
		self.local_strings, self.docs, self.controller_doctypes = {}, docs, controller_doctypes
		self.generic_visit(node)
		self.local_strings, self.docs, self.controller_doctypes = outer

	def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
		"""A function hooks.py hooks to a doctype's events is given its doc first, and a method of a
		doctype's controller is given it as self."""
		docs = {}
		if parameters := node.args.posonlyargs + node.args.args:
			first = parameters[0].arg
			if doctypes := self.hooked.get(node) or (self.controller_doctypes if first == "self" else ()):
				docs[first] = doctypes
		self.visit_scope(node, docs, ())

	visit_AsyncFunctionDef = visit_FunctionDef

	def visit_ClassDef(self, node: ast.ClassDef):
		"""A class is a doctype's controller when hooks.py overrides the doctype with it, or when it is built
		on the controller of a doctype a doctype_field rule names,
		`erpnext.accounts.doctype.payment_entry.payment_entry.PaymentEntry`."""
		doctypes = set(self.hooked.get(node, ()))
		for base in node.bases:
			parts = self.resolve(base) or ()
			if (doctype := self.rules.controllers.get(parts[-2:])) and parts[-4:-2] == ("doctype", parts[-2]):
				doctypes.add(doctype)
		self.visit_scope(node, {}, doctypes)

	def doc_doctypes(self, node: ast.expr | None) -> Collection[str]:
		"""The doctypes of the doc `node` is: a name bound to one, a row of a doc's table, `doc.items[0]` or
		`doc.append("items")`, or a call that loads or makes one of a doctype it names as a literal,
		`frappe.get_doc("Payment Entry", name)`, or as the doctype key of a dict,
		`frappe.get_doc({"doctype": "Payment Entry"})`."""
		if isinstance(node, ast.Name):
			return self.docs.get(node.id, ())
		if isinstance(node, ast.Subscript) and not isinstance(node.slice, ast.Slice):
			return self.row_doctypes(node.value)
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append":
			return self.table_doctypes(node.func.value, string_value(argument(node, 0, "key")))
		if not (isinstance(node, ast.Call) and ".".join(self.resolve(node.func) or ()) in DOC_APIS):
			return ()
		doctype = argument(node, 0, "doctype")
		if isinstance(doctype, ast.Dict):
			doctype = next(
				(value for key, value in zip(doctype.keys, doctype.values) if string_value(key) == "doctype"),
				None,
			)
		return (doctype.value,) if string_value(doctype) else ()

	def table_doctypes(self, doc: ast.expr, table: str | None) -> set[str]:
		"""The child doctype of the `table` field of the doc `doc` is."""
		return {
			child
			for doctype in self.doc_doctypes(doc)
			if (child := self.rules.child_doctypes.get((doctype, table)))
		}

	def row_doctypes(self, rows: ast.expr) -> set[str]:
		"""The child doctype of the rows `rows` reads off a doc: `doc.items` or `doc.get("items")`."""
		if isinstance(rows, ast.Attribute):
			return self.table_doctypes(rows.value, rows.attr)
		if isinstance(rows, ast.Call) and isinstance(rows.func, ast.Attribute) and rows.func.attr == "get":
			return self.table_doctypes(rows.func.value, string_value(argument(rows, 0, "key")))
		return set()

	def loop_rows(self, target: ast.expr, rows: ast.expr) -> dict[str, set[str]]:
		"""The name a loop over a doc's table gives each row, with its child doctype, in
		`for row in doc.items` and `for index, row in enumerate(doc.items)`."""
		if (
			isinstance(rows, ast.Call)
			and isinstance(rows.func, ast.Name)
			and rows.func.id == "enumerate"
			and rows.args
			and isinstance(target, ast.Tuple)
			and len(target.elts) == 2
		):
			target, rows = target.elts[1], rows.args[0]
		doctypes = self.row_doctypes(rows)
		return {target.id: doctypes} if doctypes and isinstance(target, ast.Name) else {}

	def visit_loop_header(self, target: ast.expr, rows: ast.expr):
		"""What a loop reads comes first, so `for doc in doc.items` reads the table of the doc before it."""
		self.visit(rows)
		bound = self.loop_rows(target, rows)
		self.visit(target)
		self.docs.update(bound)

	def visit_For(self, node: ast.For | ast.AsyncFor):
		self.visit_loop_header(node.target, node.iter)
		for statement in node.body + node.orelse:
			self.visit(statement)

	visit_AsyncFor = visit_For

	def visit_ListComp(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
		"""A comprehension's names end with it, and its loops run before what it builds."""
		outer = dict(self.docs)
		for generator in node.generators:
			self.visit_loop_header(generator.target, generator.iter)
			for condition in generator.ifs:
				self.visit(condition)
		for part in (node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,):
			self.visit(part)
		self.docs = outer

	visit_SetComp = visit_GeneratorExp = visit_DictComp = visit_ListComp

	def report_appended_fields(self, node: ast.Call):
		"""The keys of the row `doc.append("items", {"qty": 1})` adds."""
		row = argument(node, 1, "value")
		if isinstance(row, ast.Dict):
			for doctype in self.doc_doctypes(node):
				for key in filter(None, row.keys):
					self.report(self.rules.field_rules.get((doctype, string_value(key)), ()), key.lineno)

	def report_doc_field(self, doc: ast.expr, fieldname: str | None, line: int):
		"""A field read or written on a doc: `doc.party_balance`, or `doc.get("party_balance")`."""
		for doctype in self.doc_doctypes(doc):
			self.report(self.rules.field_rules.get((doctype, fieldname), ()), line)

	def bind_doc(self, target: ast.expr, value: ast.expr | None):
		if isinstance(target, ast.Name) and (doctypes := self.doc_doctypes(value)):
			self.docs[target.id] = doctypes

	def visit_Name(self, node: ast.Name):
		"""A name given anything else no longer holds the doc it was bound to."""
		if not isinstance(node.ctx, ast.Load):
			self.docs.pop(node.id, None)

	def visit_Subscript(self, node: ast.Subscript):
		if isinstance(node.value, ast.Call):
			self.indexed_calls.add(node.value)
		self.generic_visit(node)

	def hold_strings(self, name: str, strings: list[ast.expr]):
		"""Record strings a local name is given, which a query later in the scope may pass as its fields.
		A name keeps every string it was given, as the branches of an if may each give it its own.
		Strings under a version guard belong to one version, so they are left out."""
		if not self.version_guarded:
			self.local_strings.setdefault(name, []).extend(strings)

	def visit_Assign(self, node: ast.Assign):
		if isinstance(node.value, ast.Call):
			self.result_targets[node.value] = node.targets
		self.generic_visit(node)
		for target in node.targets:
			self.bind_doc(target, node.value)
			if isinstance(target, ast.Name):
				self.hold_strings(target.id, string_elements(node.value))
				if self.reads_frappe_version(node.value):
					self.version_names.add(target.id)

	def visit_AnnAssign(self, node: ast.AnnAssign):
		self.generic_visit(node)
		self.bind_doc(node.target, node.value)

	def visit_AugAssign(self, node: ast.AugAssign):
		self.generic_visit(node)
		if isinstance(node.target, ast.Name) and isinstance(node.op, ast.Add):
			self.hold_strings(node.target.id, string_elements(node.value))

	def hold_appended_strings(self, node: ast.Call):
		"""`fields.append("...")` and `fields.extend([...])` on a local name."""
		method = node.func
		if (
			isinstance(method, ast.Attribute)
			and isinstance(method.value, ast.Name)
			and method.attr in ("append", "extend")
			and node.args
		):
			added = node.args[0] if method.attr == "extend" else ast.List(elts=[node.args[0]])
			self.hold_strings(method.value.id, string_elements(added))

	def field_strings(self, fields: ast.expr | None) -> list[ast.expr]:
		"""The strings and f-strings passed as fields: alone, in a list or tuple, or held by a local name."""
		if isinstance(fields, ast.Name):
			return self.local_strings.get(fields.id, [])
		return string_elements(fields)

	def visit_Dict(self, node: ast.Dict):
		for key, value in zip(node.keys, node.values):
			if string_value(key) == "doctype" and (rule := self.rules.doctype_rules.get(string_value(value))):
				self.report((rule,), value.lineno)
		self.generic_visit(node)

	def visit_Attribute(self, node: ast.Attribute):
		if parts := self.resolve(node):
			self.check_path(parts, node.lineno)
		self.report_doc_field(node.value, node.attr, node.end_lineno)
		self.generic_visit(node)

	def visit_Expr(self, node: ast.Expr):
		"""A string standing alone as a statement is a docstring, which names a path without using it."""
		if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
			self.generic_visit(node)

	def visit_Constant(self, node: ast.Constant):
		if isinstance(node.value, str):
			self.report((rule for path, rule in self.rules.string_rules if path in node.value), node.lineno)
			tables = (self.rules.doctype_rules.get(doctype) for doctype in TABLE_NAME.findall(node.value))
			self.report(filter(None, tables), node.lineno)

	def doctype_argument(self, parts: tuple[str, ...], node: ast.Call) -> Rule | None:
		"""The rule for the doctype this call reads, when it names one as a literal."""
		if ".".join(parts) not in DOCTYPE_APIS:
			return None
		return self.rules.doctype_rules.get(string_value(argument(node, 0, "doctype")))

	def reloaded_doctype(self, parts: tuple[str, ...], node: ast.Call) -> Rule | None:
		"""The rule for the doctype `frappe.reload_doc(module, "doctype", name)` reads off disk."""
		if (
			".".join(parts) not in RELOAD_DOC_APIS
			or scrub(string_value(argument(node, 1, "dt"))) != "doctype"
		):
			return None
		return self.rules.scrubbed_doctype_rules.get(scrub(string_value(argument(node, 2, "dn"))))

	def select_fields(self, api: str, arguments: dict[str, ast.expr | None]) -> list[ast.expr]:
		"""The strings and f-strings a query passes as the fields v16 validates. A list query given no
		fields selects the field it plucks."""
		if api not in SELECT_FIELD_APIS:
			return []
		return self.field_strings(
			arguments.get("fields") or arguments.get("fieldname") or arguments.get("pluck")
		)

	def named_fields(
		self, node: ast.Call, arguments: dict[str, ast.expr | None]
	) -> Iterator[tuple[str, str, ast.expr]]:
		"""Each field a doctype API call names in a string literal, as (doctype, fieldname, the string),
		when the call names its doctype as a literal too."""
		if not (doctype := string_value(argument(node, 0, "doctype"))):
			return
		for keyword, value in arguments.items():
			if keyword in FILTER_ARGUMENTS:
				yield from filter_fields(doctype, value)
				continue
			strings = [string for string in self.field_strings(value) if isinstance(string, ast.Constant)]
			if isinstance(value, ast.Dict):
				strings += [key for key in value.keys if string_value(key) is not None]
			for string in strings:
				for field in split_fields(string.value):
					if reference := FIELD_REFERENCE.fullmatch(field.strip()):
						yield reference.group(1) or doctype, reference.group(2), string

	def report_sql_text(self, api: str, node: ast.Call):
		"""The sql_text rules the query of a SQL call matches: a string or f-string, one a local name
		holds, or the query for each database in `frappe.db.multisql`."""
		query = argument(node, 0, SQL_APIS[api])
		queries = (
			[value for value in query.values if field_text(value) is not None]
			if isinstance(query, ast.Dict)
			else self.field_strings(query)
		)
		for text in queries:
			matching = (
				rule
				for patterns, rule in self.rules.sql_rules
				if any(pattern.search(field_text(text)) for pattern in patterns)
			)
			self.report(matching, text.lineno)

	def report_rejected_request(self, api: str, node: ast.Call):
		"""The http_method rules a request matches: a URL naming a server method, sent by an HTTP method
		the server method no longer accepts."""
		sent = REQUEST_APIS[api] or string_value(argument(node, 0, "method"))
		url = field_text(argument(node, 0 if REQUEST_APIS[api] else 1, "url"))
		if sent and url and (called := API_METHOD.search(url)):
			rejecting = (
				rule
				for rule in self.rules.http_rules.get(called.group(1), ())
				if sent.upper() in rule.match.rejected_methods
			)
			self.report(rejecting, node.lineno)

	def attr_path(self, parts: tuple[str, ...], node: ast.Call) -> tuple[str, ...] | None:
		"""The dotted path this call resolves, when it names one as a literal."""
		if ".".join(parts) not in ATTR_APIS:
			return None
		method = next((keyword.value for keyword in node.keywords if keyword.arg == "method"), None)
		if method is None and node.args:
			method = node.args[0]
		if not isinstance(method, ast.Constant) or not isinstance(method.value, str):
			return None
		return tuple(method.value.split("."))

	def result_fits(self, node: ast.Call, returns: int) -> bool:
		"""True when the call's result is indexed or sliced, or unpacked into names that take `returns` values."""
		targets = self.result_targets.get(node, [])
		return node in self.indexed_calls or (
			bool(targets) and all(unpacks_result(target, returns) for target in targets)
		)

	def visit_Call(self, node: ast.Call):
		self.hold_appended_strings(node)
		method = node.func
		if isinstance(method, ast.Attribute) and method.attr in DOC_FIELD_METHODS:
			fieldname = string_value(argument(node, 0, DOC_FIELD_METHODS[method.attr]))
			self.report_doc_field(method.value, fieldname, method.end_lineno)
		if isinstance(method, ast.Attribute) and method.attr == "append":
			self.report_appended_fields(node)
		if parts := self.resolve(node.func):
			api = ".".join(parts)
			rules = self.rules.call_rules.get(parts, ())
			matching = (
				rule
				for rule in rules
				if call_uses_argument(node, rule.match)
				and (not rule.match.url_host or names_private_host(node))
				and not (rule.match.returns and self.result_fits(node, rule.match.returns))
			)
			self.report(matching, node.lineno)
			if rule := self.doctype_argument(parts, node) or self.reloaded_doctype(parts, node):
				self.report((rule,), node.lineno)
			if api in SQL_APIS:
				self.report_sql_text(api, node)
			if api in REQUEST_APIS:
				self.report_rejected_request(api, node)
			arguments = field_arguments(api, node)
			for fields in self.select_fields(api, arguments):
				rejecting = (
					rule
					for accepted, rule in self.rules.select_field_rules
					if rejects_select_field(accepted, field_text(fields))
				)
				self.report(rejecting, fields.lineno)
			for doctype, fieldname, string in self.named_fields(node, arguments):
				self.report(self.rules.field_rules.get((doctype, fieldname), ()), string.lineno)
			if path := self.attr_path(parts, node):
				self.check_path(path, node.lineno)
		self.generic_visit(node)
