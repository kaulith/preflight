import re
from bisect import bisect_right
from collections.abc import Iterator
from typing import NamedTuple

from preflight.models import Finding, Rule, rules_by_doctype, rules_by_doctype_field
from preflight.python_scanner import FIELD_REFERENCE, FIELD_SEPARATOR, rejects_select_field

QUOTE = "[\"'`]"
NOT_QUOTE_OR_LINE_BREAK = "[^\"'`\\n]*"
SNIPPET_LENGTH = 200

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
	against its string literals, and select_field and doctype_field rules matched against the literals
	its client queries pass."""

	def __init__(self, rules: list[Rule]):
		self.matchers: list[tuple[re.Pattern, Rule]] = []
		self.string_rules: list[tuple[str, Rule]] = []
		self.import_rules: dict[tuple[str, ...], list[Rule]] = {}
		self.select_field_rules: list[tuple[list[re.Pattern], Rule]] = []
		self.doctype_rules = rules_by_doctype(rules)
		self.field_rules = rules_by_doctype_field(rules)
		for rule in rules:
			if rule.match.type == "pattern":
				self.matchers += [(re.compile(pattern), rule) for pattern in rule.match.patterns]
			elif rule.match.type == "select_field":
				self.select_field_rules.append(
					([re.compile(pattern) for pattern in rule.match.patterns], rule)
				)
			elif rule.match.type == "string_contains":
				self.string_rules += [(path, rule) for path in rule.match.paths]
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
		for regex, rule in self.doctype_matchers:
			for reference in regex.finditer(code):
				report(rule, bisect_right(line_starts, reference.end() - 1))
		for offset, text in strings:
			for index, rule in self.string_hits(text):
				report(rule, bisect_right(line_starts, offset + index))
		if self.select_field_rules or self.field_rules:
			for offset, rule in self.query_hits(strings, syntax):
				report(rule, bisect_right(line_starts, offset))
		return list(findings.values())
