import re
from bisect import bisect_right
from collections.abc import Iterator
from typing import NamedTuple

from preflight.models import (
	Finding,
	Rule,
	child_doctypes,
	rules_by_doctype,
	rules_by_doctype_field,
	script_registration_rule,
)
from preflight.python_scanner import API_METHOD, FIELD_REFERENCE, FIELD_SEPARATOR, rejects_select_field

QUOTE = "[\"'`]"
NOT_QUOTE_OR_LINE_BREAK = "[^\"'`\\n]*"
SNIPPET_LENGTH = 200
SCRIPT_REGISTRATION = re.compile(r"frappe\s*\.\s*(?:ui\s*\.\s*form\s*\.\s*on\b|listview_settings\b)")

# Client APIs whose first argument is a doctype name, and set_route, which carries
# it as the second.
DOCTYPE_APIS = (
	"frappe.get_doc",
	"frappe.new_doc",
	"frappe.get_list",
	"frappe.get_all",
	"frappe.set_route",
	"frappe.db.get_doc",
	"frappe.db.get_list",
	"frappe.db.get_value",
	"frappe.db.get_single_value",
	"frappe.db.set_value",
	"frappe.db.insert",
	"frappe.db.delete_doc",
	"frappe.db.exists",
	"frappe.db.count",
	"frappe.ui.form.on",
)

CODE_TOKEN = re.compile(r"//|/\*|<!--|[\"'`/{}]")
# A stylesheet has no regex or template literals, and Sass reads an unquoted url() as it stands, so the
# `//` of `url(//cdn.example.com)` opens no comment.
STYLESHEET_TOKEN = re.compile(r"//|/\*|url\(|[\"']")
UNQUOTED_URL = re.compile(r"\s*[^\s\"')][^)\n]*")
COMMENT_CLOSE = {"//": "\n", "/*": "*/", "<!--": "-->"}
NOT_LINE_BREAK = re.compile(r"[^\n]")
QUOTED_TEXT = {quote: re.compile(rf"(?:[^{quote}\\\n]|\\[\s\S])*") for quote in "\"'"}
TEMPLATE_TEXT = re.compile(r"(?:[^`\\$]|\\[\s\S]|\$(?!\{))*")
REGEX_LITERAL = re.compile(r"/(?:[^/\\\[\n]|\\.|\[(?:[^\]\\\n]|\\.)*\])+/")
# A `/` after one of these characters or keywords opens a regex literal; after anything else it divides.
REGEX_PRECEDERS = frozenset("(,=:[!&|?{};+-*%<>~^")
REGEX_KEYWORDS = frozenset(
	{
		"return",
		"typeof",
		"instanceof",
		"in",
		"of",
		"new",
		"delete",
		"void",
		"throw",
		"case",
		"do",
		"else",
		"yield",
		"await",
	}
)
DOTTED_PATH = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
TABLE_NAME = re.compile(r"\\?`tab([^`\\]+)\\?`")

BRACKET = re.compile(r"[()\[\]{}]")
OPENING_BRACKET = {")": "(", "]": "[", "}": "{"}
PART_BREAK = re.compile(r"[,(\[{]")
KEY_BREAK = re.compile(r"[:(\[{]")
PLAIN_KEY = re.compile(r"[A-Za-z_$][\w$]*")
CLIENT_CALL = re.compile(
	r"(?<![\w$.])(frappe\s*\.\s*db\s*\.\s*(?:get_list|get_value|set_value|get_single_value)"
	r"|frappe\s*\.\s*x?call)\s*\("
)

HTTP_CALL = re.compile(
	r"(?<![\w$.])(frappe\s*\.\s*call|createResource|fetch|(?:\$|jQuery)\s*\.\s*(?:get|ajax)|axios\s*\.\s*get)\s*\("
)

# Client APIs that call a server method with their arguments in order, as the method and the name each
# argument has there. frappe.db.get_list passes the object after the doctype as the rest.
CLIENT_QUERIES = {
	"frappe.db.get_list": ("frappe.desk.reportview.get_list", ("doctype",)),
	"frappe.db.get_value": ("frappe.client.get_value", ("doctype", "filters", "fieldname")),
	"frappe.db.set_value": ("frappe.client.set_value", ("doctype", "name", "fieldname")),
	"frappe.db.get_single_value": ("frappe.client.get_single_value", ("doctype", "field")),
}
# Server methods that send their fields through frappe.database.query on v16.
SELECTING_METHODS = frozenset(
	{"frappe.desk.reportview.get_list", "frappe.client.get_list", "frappe.client.get_value"}
)
QUERY_METHODS = SELECTING_METHODS | {"frappe.client.set_value", "frappe.client.get_single_value"}
# The arguments of those methods that name fields, and those of them that are filters.
FIELD_ARGUMENTS = ("fields", "fieldname", "field", "filters", "or_filters", "order_by", "group_by")
FILTER_ARGUMENTS = frozenset({"filters", "or_filters"})

FORM_SCRIPT = re.compile(r"(?<![\w$.])frappe\s*\.\s*ui\s*\.\s*form\s*\.\s*on\s*\(")
HANDLER = re.compile(
	r"\s*(?:async\s+)?(?P<key>[A-Za-z_$][\w$]*|\"[^\"\n]*\"|'[^'\n]*')\s*"
	r"(?:\(|:\s*(?:async\s+)?(?:function\b[^(]*\(|\(|(?P<parameter>[A-Za-z_$][\w$]*)\s*(?==>)))"
)
MEMBER = re.compile(r"\s*(?:\??\.\s*([A-Za-z_$][\w$]*)|(?:\?\.\s*)?(\[))")
CALL_OPENING = re.compile(r"\s*\(")
OBJECT_OPENING = re.compile(r"\s*\{")
SINGLE_PARAMETER = re.compile(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*(?==>)")
CONTROL_STATEMENT = re.compile(r"(?<![\w$.])(?:if|for|while|switch|with)\s*\(")
FUNCTION_BODY = re.compile(r"\s*(?:=>\s*)?(\{)|\s*=>")
EXPRESSION_END = re.compile(r"[,;)\]}(\[{]")
EXPRESSION_CONTINUES = re.compile(r"\s*[?|&+\-*/%<>=(]")

# The methods of frappe's Form that take a fieldname first. add_fetch is not one: with no target doctype
# its link field can be a child table's.
FORM_FIELD_METHODS = frozenset(
	{
		"add_child",
		"clear_table",
		"field_map",
		"get_docfield",
		"get_field",
		"get_formatted",
		"get_sum",
		"refresh_field",
		"reset_currency_labels",
		"scroll_to_field",
		"set_currency_labels",
		"set_df_property",
		"set_indicator_formatter",
		"set_query",
		"set_value",
		"toggle_display",
		"toggle_enable",
		"toggle_reqd",
		"update_in_all_rows",
	}
)
FORM_FIELD_LIST_METHODS = frozenset(
	{
		"field_map",
		"reset_currency_labels",
		"set_currency_labels",
		"toggle_display",
		"toggle_enable",
		"toggle_reqd",
	}
)
# Those whose fieldnames are a child table's once the table is passed, as the argument count that passes
# it and its position.
FORM_TABLE_ARGUMENTS = {"reset_currency_labels": (2, 1), "set_currency_labels": (3, 2), "set_query": (3, 1)}


class Literal(NamedTuple):
	"""A string literal, with the offset its text starts at."""

	offset: int
	text: str


def bracket_pairs(syntax: str) -> dict[int, int]:
	"""Where each bracket closes, for every bracket closed by its own kind."""
	pairs: dict[int, int] = {}
	opened: list[int] = []
	for bracket in BRACKET.finditer(syntax):
		if bracket.group() in "([{":
			opened.append(bracket.start())
		elif opened and syntax[opened[-1]] == OPENING_BRACKET[bracket.group()]:
			pairs[opened.pop()] = bracket.start()
	return pairs


class LiteralReader:
	"""Reads the arguments of a call out of lexed code, as far as they are literals: strings, and arrays
	and objects built of them. Anything else reads as None."""

	def __init__(self, strings: list[tuple[int, str]], syntax: str):
		self.strings = dict(strings)
		self.syntax = syntax
		self.pairs = bracket_pairs(syntax)

	def skip_brackets(self, pattern: re.Pattern, start: int, end: int) -> re.Match | None:
		"""The first match of `pattern` in syntax[start:end] that no bracket holds; the pattern matches
		the opening brackets too, so they can be skipped."""
		while match := pattern.search(self.syntax, start, end):
			if match.group() not in "([{":
				return match
			start = self.pairs.get(match.start(), end) + 1
		return None

	def parts(self, start: int, end: int) -> list[tuple[int, int]]:
		"""The spans between the commas of syntax[start:end] that no bracket holds."""
		parts = []
		while comma := self.skip_brackets(PART_BREAK, start, end):
			parts.append((start, comma.start()))
			start = comma.end()
		return [*parts, (start, end)]

	def value(self, start: int, end: int):
		"""What syntax[start:end] holds: a Literal, a list for an array, a dict keyed by Literal for an
		object, or None for anything else."""
		text = self.syntax[start:end]
		start, end = start + len(text) - len(text.lstrip()), end - len(text) + len(text.rstrip())
		if start >= end:
			return None
		first = self.syntax[start]
		if first in "\"'`":
			body = self.strings.get(start + 1)
			if body is None or start + len(body) + 2 != end or self.syntax[end - 1] != first:
				return None
			return Literal(start + 1, body)
		if self.pairs.get(start) != end - 1:
			return None
		if first == "[":
			return [self.value(*part) for part in self.parts(start + 1, end - 1)]
		if first != "{":
			return None
		entries = {}
		for part_start, part_end in self.parts(start + 1, end - 1):
			if not (colon := self.skip_brackets(KEY_BREAK, part_start, part_end)):
				continue
			key_text = self.syntax[part_start : colon.start()]
			if PLAIN_KEY.fullmatch(name := key_text.strip()):
				key = Literal(part_start + key_text.index(name), name)
			elif not isinstance(key := self.value(part_start, colon.start()), Literal):
				continue
			entries[key] = self.value(colon.end(), part_end)
		return entries

	def arguments(self, opening: int) -> list | None:
		"""The arguments of the call whose parenthesis opens at `opening`."""
		if (closing := self.pairs.get(opening)) is None:
			return None
		return [self.value(*part) for part in self.parts(opening + 1, closing)]


class FormScriptReader(LiteralReader):
	"""Reads the handlers of frappe.ui.form.on calls and the fields they reach through the names frappe
	passes them: the form, and for a child doctype the row's doctype and name."""

	def __init__(self, strings: list[tuple[int, str]], syntax: str):
		super().__init__(strings, syntax)
		statements = {statement.end() - 1 for statement in CONTROL_STATEMENT.finditer(syntax)}
		heads = [(arrow.start(), [arrow[1]], arrow.end()) for arrow in SINGLE_PARAMETER.finditer(syntax)]
		heads += [
			(opening, PLAIN_KEY.findall(syntax, opening, closing), closing + 1)
			for opening, closing in self.pairs.items()
			if syntax[opening] == "(" and opening not in statements
		]
		self.functions = [
			(start, names, end)
			for start, names, parameters_end in heads
			if (end := self.function_end(parameters_end)) is not None
		]

	def function_end(self, parameters_end: int) -> int | None:
		"""Where the function whose parameters end at `parameters_end` ends, or None if no body follows."""
		if not (body := FUNCTION_BODY.match(self.syntax, parameters_end)):
			return None
		if body[1]:
			return self.pairs.get(body.start(1))
		end = self.skip_brackets(EXPRESSION_END, body.end(), len(self.syntax))
		return end.start() if end else len(self.syntax)

	def passed(self, opening: int) -> list[tuple[int, int]]:
		"""The spans of the arguments of the call whose parenthesis opens at `opening`, without the empty
		one a trailing comma leaves."""
		if (closing := self.pairs.get(opening)) is None:
			return []
		return [
			(start, end) for start, end in self.parts(opening + 1, closing) if self.syntax[start:end].strip()
		]

	def handlers(self, start: int, end: int) -> Iterator[tuple[Literal, list[str], int, int]]:
		"""Each function of the object in syntax[start:end], as its key, its parameters and its body's span."""
		if not (opening := OBJECT_OPENING.match(self.syntax, start, end)):
			return
		if (closing := self.pairs.get(opening.end() - 1)) is None:
			return
		for part_start, part_end in self.parts(opening.end(), closing):
			if not (head := HANDLER.match(self.syntax, part_start, part_end)):
				continue
			if head["parameter"]:
				parameters, body = [head["parameter"]], head.end("parameter")
			elif (parameters_end := self.pairs.get(head.end() - 1)) is None:
				continue
			else:
				parameters = [
					self.syntax[name_start:name_end].strip()
					for name_start, name_end in self.parts(head.end(), parameters_end)
				]
				body = parameters_end + 1
			if (body_end := self.function_end(body)) is not None:
				key = self.value(*head.span("key")) or Literal(head.start("key"), head["key"])
				yield key, parameters, body, body_end

	def reads(self, name: str, start: int, end: int) -> list[int]:
		"""Where syntax[start:end] reads a name bound just before it, outside the nested functions with a
		parameter of that name. A name declared or assigned again there is not followed at all."""
		word = rf"(?<![\w$.]){re.escape(name)}(?![\w$])"
		if re.compile(rf"\b(?:let|const|var)\s+{word}|{word}\s*=(?![=>])").search(self.syntax, start, end):
			return []
		hidden = [
			(function_start, function_end)
			for function_start, names, function_end in self.functions
			if name in names and start <= function_start < end
		]
		return [
			read.start()
			for read in re.compile(word).finditer(self.syntax, start, end)
			if not any(low <= read.start() < high for low, high in hidden)
		]

	def member(self, end: int) -> Literal | None:
		"""The name read off the expression ending at `end`, by a dot or by a literal in brackets."""
		if not (access := MEMBER.match(self.syntax, end)):
			return None
		if access[1]:
			return Literal(access.start(1), access[1])
		closing = self.pairs.get(access.start(2))
		name = self.value(access.start(2) + 1, closing) if closing else None
		return name if isinstance(name, Literal) else None

	def method_fields(self, method: str, opening: int) -> list[Literal]:
		"""The fields of the form's own doctype that a call of a Form method names."""
		if not (arguments := [self.value(*part) for part in self.passed(opening)]):
			return []
		if method in FORM_TABLE_ARGUMENTS:
			count, table = FORM_TABLE_ARGUMENTS[method]
			if len(arguments) >= count:
				return literals(arguments[table])
		if method in FORM_FIELD_LIST_METHODS:
			return literals(arguments[0])
		if method == "set_value" and isinstance(arguments[0], dict):
			return list(arguments[0])
		return [arguments[0]] if isinstance(arguments[0], Literal) else []

	def form_fields(self, form: str, start: int, end: int) -> Iterator[Literal]:
		"""The fields syntax[start:end] reaches through the form parameter."""
		for read in self.reads(form, start, end):
			if not (access := MEMBER.match(self.syntax, read + len(form))) or not access[1]:
				continue
			if access[1] in ("doc", "fields_dict"):
				if field := self.member(access.end()):
					yield field
			elif access[1] in FORM_FIELD_METHODS and (call := CALL_OPENING.match(self.syntax, access.end())):
				yield from self.method_fields(access[1], call.end() - 1)

	def row_fields(self, cdt: str, cdn: str, start: int, end: int) -> Iterator[Literal]:
		"""The fields syntax[start:end] reaches through locals[cdt][cdn], directly or by a name bound to it."""
		row = re.compile(
			r"(?:(?:(?<![\w$.])(?:let|const|var)\s+|,\s*)(?P<bound>[A-Za-z_$][\w$]*)\s*=\s*)?"
			rf"(?<![\w$.])locals\s*\[\s*(?P<cdt>{re.escape(cdt)})\s*\]\s*\[\s*(?P<cdn>{re.escape(cdn)})\s*\]"
		)
		visible = {*self.reads(cdt, start, end), *self.reads(cdn, start, end)}
		for access in row.finditer(self.syntax, start, end):
			if not {access.start("cdt"), access.start("cdn")} <= visible:
				continue
			if field := self.member(access.end()):
				yield field
			elif access["bound"] and not EXPRESSION_CONTINUES.match(self.syntax, access.end()):
				block_end = min(
					(
						closing
						for opening, closing in self.pairs.items()
						if self.syntax[opening] == "{" and opening < access.start() < closing
					),
					default=end,
				)
				for read in self.reads(access["bound"], access.end(), min(block_end, end)):
					if field := self.member(read + len(access["bound"])):
						yield field


def by_name(entries) -> dict:
	"""An object's entries keyed by the text of their keys."""
	return {key.text: value for key, value in entries.items()} if isinstance(entries, dict) else {}


def client_queries(strings: list[tuple[int, str]], syntax: str) -> Iterator[tuple[str, dict]]:
	"""Each call that queries a doctype from the client, as the server method it reaches and the
	arguments it passes the method, by name."""
	reader = None
	for call in CLIENT_CALL.finditer(syntax):
		reader = reader or LiteralReader(strings, syntax)
		if not (arguments := reader.arguments(call.end() - 1)):
			continue
		api = "".join(call.group(1).split())
		if api in CLIENT_QUERIES:
			method, names = CLIENT_QUERIES[api]
			passed = dict(zip(names, arguments))
			if api == "frappe.db.get_list" and len(arguments) > 1:
				passed |= by_name(arguments[1])
		elif isinstance(arguments[0], dict):
			options = by_name(arguments[0])
			method, passed = options.get("method"), by_name(options.get("args"))
		else:
			method, passed = arguments[0], by_name(arguments[1] if len(arguments) > 1 else None)
		if isinstance(method, Literal):
			method = method.text
		if method in QUERY_METHODS:
			yield method, passed


def http_requests(strings: list[tuple[int, str]], syntax: str) -> Iterator[tuple[Literal, str]]:
	"""Each request the client sends to a literal server method or URL, with its HTTP method, when that is
	a literal or the API's default."""
	reader = None
	for call in HTTP_CALL.finditer(syntax):
		reader = reader or LiteralReader(strings, syntax)
		if not (arguments := reader.arguments(call.end() - 1)):
			continue
		api = "".join(call.group(1).split())
		options = by_name(arguments[0])
		if api == "frappe.call":
			target, sent = options.get("method"), options.get("type", "POST")
		elif api == "createResource":
			target, sent = options.get("url"), options.get("method", "POST")
		elif api.endswith(".ajax"):
			target, sent = options.get("url"), options.get("type", options.get("method", "GET"))
		elif api == "fetch":
			settings = arguments[1] if len(arguments) > 1 else {}
			target = arguments[0]
			sent = by_name(settings).get("method", "GET") if isinstance(settings, dict) else None
		else:
			target, sent = arguments[0], "GET"
		sent = sent.text if isinstance(sent, Literal) else sent
		if isinstance(target, Literal) and isinstance(sent, str):
			yield target, sent.upper()


def literals(value) -> list[Literal]:
	"""The string literals a value holds: itself, or the elements of an array."""
	elements = value if isinstance(value, list) else [value]
	return [element for element in elements if isinstance(element, Literal)]


def named_fields(doctype: str, keyword: str, value) -> Iterator[tuple[str, str, Literal]]:
	"""The fields an argument of a query method names, as (doctype, fieldname, the literal naming it)."""
	if keyword in FILTER_ARGUMENTS:
		if isinstance(value, dict):
			yield from ((doctype, key.text, key) for key in value)
		for condition in value if isinstance(value, list) else []:
			if isinstance(condition, list):
				names = [element if isinstance(element, Literal) else None for element in condition]
				if len(names) == 4 and names[0] and names[1]:
					yield names[0].text, names[1].text, names[1]
				elif len(names) == 3 and names[0]:
					yield doctype, names[0].text, names[0]
		return
	for literal in [*literals(value), *(value if isinstance(value, dict) else ())]:
		for field in FIELD_SEPARATOR.split(literal.text):
			if reference := FIELD_REFERENCE.fullmatch(field.strip()):
				yield reference.group(1) or doctype, reference.group(2), literal


def doctype_reference(doctype: str) -> re.Pattern:
	"""A doctype named as a literal argument to one of the client APIs, as the value of a
	`doctype` key, or as the key of its list view settings. The match ends with the name."""
	apis = "|".join(re.escape(api).replace(r"\.", r"\s*\.\s*") for api in DOCTYPE_APIS)
	leading = f"(?:{QUOTE}{NOT_QUOTE_OR_LINE_BREAK}{QUOTE},\\s*)?"
	name = f"{QUOTE}{re.escape(doctype)}{QUOTE}"
	return re.compile(
		rf"\b(?:{apis})\(\s*{leading}{name}"
		rf"|\bdoctype{QUOTE}?\s*:\s*{name}"
		rf"|\bfrappe\.listview_settings\[\s*{name}(?=\s*\])"
	)


def regex_allowed(code: list[str], slash: int) -> bool:
	"""Whether the `/` at `slash` opens a regex literal, judged by the code before it."""
	index = slash - 1
	while index >= 0 and code[index].isspace():
		index -= 1
	if index < 0 or code[index] in REGEX_PRECEDERS:
		return True
	word_end = index + 1
	while index >= 0 and (code[index].isalnum() or code[index] in "_$"):
		index -= 1
	return "".join(code[index + 1 : word_end]) in REGEX_KEYWORDS


def lex(source: str, stylesheet: bool = False) -> tuple[str, list[tuple[int, str]], str]:
	"""The source with every comment blanked and its line breaks kept, the text of every string
	literal with the offset it starts at, and the code once more with the text of every string and
	regex literal blanked too, which leaves the brackets and commas a call's arguments are read by. A
	template literal gives one string for each run of text between its substitutions.

	A quoted string ends at the line break it cannot cross, and a `/` read as a regex literal
	that does not close on its line is read as division, so a misread stops at the line."""
	code = list(source)
	strings: list[tuple[int, str]] = []
	regex_bodies: list[tuple[int, int]] = []
	substitution_braces: list[int] = []
	position = 0
	while token := (STYLESHEET_TOKEN if stylesheet else CODE_TOKEN).search(source, position):
		start, position = token.start(), token.end()
		text = token.group()
		if text in COMMENT_CLOSE:
			close = source.find(COMMENT_CLOSE[text], position)
			position = len(source) if close == -1 else close + len(COMMENT_CLOSE[text])
			code[start:position] = NOT_LINE_BREAK.sub(" ", source[start:position])
		elif text == "url(":
			if url := UNQUOTED_URL.match(source, position):
				position = url.end()
		elif text in ("'", '"'):
			body = QUOTED_TEXT[text].match(source, position)
			strings.append((position, body.group()))
			position = body.end() + 1
		elif text == "`" or (text == "}" and substitution_braces and not substitution_braces[-1]):
			if text == "}":
				substitution_braces.pop()
			body = TEMPLATE_TEXT.match(source, position)
			strings.append((position, body.group()))
			position = body.end() + 1
			if source.startswith("${", body.end()):
				substitution_braces.append(0)
				position += 1
		elif text in ("{", "}"):
			if substitution_braces:
				substitution_braces[-1] += 1 if text == "{" else -1
		elif regex_allowed(code, start) and (literal := REGEX_LITERAL.match(source, start)):
			regex_bodies.append((start + 1, literal.end() - 1))
			position = literal.end()
	syntax = code.copy()
	for start, end in [*((offset, offset + len(text)) for offset, text in strings), *regex_bodies]:
		syntax[start:end] = NOT_LINE_BREAK.sub(" ", source[start:end])
	return "".join(code), strings, "".join(syntax)


class JSScanner:
	"""Pattern rules, as one regex each, run over a file's code line by line with its comments blanked,
	doctype rules as one regex each over the whole of that code, string and import path rules matched
	against its string literals, select_field and doctype_field rules matched against the literals its
	client queries pass, and doctype_field rules against the fields its form scripts reach."""

	def __init__(self, rules: list[Rule]):
		self.matchers: list[tuple[re.Pattern, Rule]] = []
		self.string_rules: list[tuple[str, Rule]] = []
		self.import_rules: dict[tuple[str, ...], list[Rule]] = {}
		self.select_field_rules: list[tuple[list[re.Pattern], Rule]] = []
		self.http_rules: dict[str, list[Rule]] = {}
		self.doctype_rules = rules_by_doctype(rules)
		self.field_rules = rules_by_doctype_field(rules)
		self.field_doctypes = {doctype for doctype, _ in self.field_rules}
		self.child_doctypes = frozenset(child_doctypes(rules).values())
		for rule in rules:
			if rule.match.type == "pattern":
				self.matchers += [(re.compile(pattern), rule) for pattern in rule.match.patterns]
			elif rule.match.type == "select_field":
				self.select_field_rules.append(
					([re.compile(pattern) for pattern in rule.match.patterns], rule)
				)
			elif rule.match.type == "string_contains":
				self.string_rules += [(path, rule) for path in rule.match.paths]
			elif rule.match.type == "http_method":
				for path in rule.match.paths:
					self.http_rules.setdefault(path, []).append(rule)
			elif rule.match.type == "import_path":
				for path in rule.match.paths:
					self.import_rules.setdefault(tuple(path.split(".")), []).append(rule)
		self.doctype_matchers = [
			(doctype_reference(doctype), rule) for doctype, rule in self.doctype_rules.items()
		]

	def string_hits(self, text: str) -> list[tuple[int, Rule]]:
		"""The rules a string literal matches, each with the index in `text` it matched at.

		A string that is wholly a dotted path is one frappe resolves, so it is matched against
		the import paths by segment, unless a string rule already reports it."""
		hits = [(text.index(path), rule) for path, rule in self.string_rules if path in text]
		if not hits and DOTTED_PATH.fullmatch(text):
			parts = tuple(text.split("."))
			hits = [
				(0, rule)
				for end in range(1, len(parts) + 1)
				for rule in self.import_rules.get(parts[:end], ())
			]
		return hits + [
			(table.start(), rule)
			for table in TABLE_NAME.finditer(text)
			if (rule := self.doctype_rules.get(table.group(1)))
		]

	def query_hits(self, strings: list[tuple[int, str]], syntax: str) -> Iterator[tuple[int, Rule]]:
		"""The select_field and doctype_field rules the client's queries match, each with the offset of
		the literal it matched."""
		for method, passed in client_queries(strings, syntax):
			if method in SELECTING_METHODS:
				for literal in literals(passed.get("fields") or passed.get("fieldname")):
					for accepted, rule in self.select_field_rules:
						if rejects_select_field(accepted, literal.text):
							yield literal.offset, rule
			if not isinstance(doctype := passed.get("doctype"), Literal):
				continue
			for keyword in FIELD_ARGUMENTS:
				for field_doctype, fieldname, literal in named_fields(
					doctype.text, keyword, passed.get(keyword)
				):
					yield from (
						(literal.offset, rule)
						for rule in self.field_rules.get((field_doctype, fieldname), ())
					)

	def form_script_hits(self, strings: list[tuple[int, str]], syntax: str) -> Iterator[tuple[int, Rule]]:
		"""The doctype_field rules the handlers of its form scripts reach, each with the offset of the
		field reference. A child doctype's handlers get the parent's form, so only their row is its own."""
		reader = None
		for call in FORM_SCRIPT.finditer(syntax):
			reader = reader or FormScriptReader(strings, syntax)
			parts = reader.passed(call.end() - 1)
			if len(parts) != 2 or not isinstance(doctype := reader.value(*parts[0]), Literal):
				continue
			if doctype.text not in self.field_doctypes:
				continue
			for key, parameters, start, end in reader.handlers(*parts[1]):
				fields = [key]
				if doctype.text not in self.child_doctypes:
					if PLAIN_KEY.fullmatch(parameters[0]):
						fields += reader.form_fields(parameters[0], start, end)
				elif len(parameters) > 2 and all(map(PLAIN_KEY.fullmatch, parameters[1:3])):
					fields += reader.row_fields(parameters[1], parameters[2], start, end)
				for field in fields:
					yield from (
						(field.offset, rule) for rule in self.field_rules.get((doctype.text, field.text), ())
					)

	def http_hits(self, strings: list[tuple[int, str]], syntax: str) -> Iterator[tuple[int, Rule]]:
		"""The http_method rules the client's requests match, each with the offset of the literal naming
		the server method."""
		for target, sent in http_requests(strings, syntax):
			called = API_METHOD.search(target.text)
			yield from (
				(target.offset, rule)
				for rule in self.http_rules.get(called.group(1) if called else target.text, ())
				if sent in rule.match.rejected_methods
			)

	def scan(self, source: str, file: str) -> list[Finding]:
		code, strings, syntax = lex(source, stylesheet=file.endswith(".scss"))
		lines = source.split("\n")
		line_starts = [0] + [line_break.end() for line_break in re.finditer("\n", source)]
		findings: dict[tuple[str, int], Finding] = {}

		def report(rule: Rule, line: int):
			snippet = lines[line - 1].strip()[:SNIPPET_LENGTH]
			findings.setdefault((rule.id, line), Finding(rule=rule, file=file, line=line, snippet=snippet))

		for line, text in enumerate(code.split("\n"), start=1):
			for regex, rule in self.matchers:
				if regex.search(text):
					report(rule, line)
		registrations = []
		for regex, rule in self.doctype_matchers:
			for reference in regex.finditer(code):
				line = bisect_right(line_starts, reference.end() - 1)
				if SCRIPT_REGISTRATION.match(reference.group()):
					registrations.append((rule, line))
				else:
					report(rule, line)
		for offset, text in strings:
			for index, rule in self.string_hits(text):
				report(rule, bisect_right(line_starts, offset + index))
		if self.select_field_rules or self.field_rules:
			for offset, rule in self.query_hits(strings, syntax):
				report(rule, bisect_right(line_starts, offset))
		if self.field_rules:
			for offset, rule in self.form_script_hits(strings, syntax):
				report(rule, bisect_right(line_starts, offset))
		if self.http_rules:
			for offset, rule in self.http_hits(strings, syntax):
				report(rule, bisect_right(line_starts, offset))
		# Last, so a call on the same line that does raise keeps the finding at its error.
		for rule, line in registrations:
			report(script_registration_rule(rule), line)
		return list(findings.values())
