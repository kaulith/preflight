from dataclasses import dataclass, field

SEVERITIES = ("error", "warning", "info")
MATCH_TYPES = (
	"import_path",
	"call",
	"pattern",
	"string_contains",
	"hook_key",
	"override_subclass",
	"returns_none",
	"unreadable_function",
	"missing_hook",
	"doctype",
	"doctype_field",
	"select_field",
	"undeclared_import",
	"site_record",
	"bench_python",
	"requires_python",
	"frappe_bound",
	"dependency_pins",
	"required_apps",
	"bench_node",
	"target_branch",
	"dependency_wheels",
)
# Match types checked only with --online: they run git and node, or ask PyPI.
ONLINE_MATCH_TYPES = ("bench_node", "target_branch", "dependency_wheels")
# When a rule's Fix can be applied: on the version the site runs now, or only with the upgrade.
FIX_TIMINGS = ("before", "with-upgrade")
# Where a finding was read: a file in an app, a record on the site, or the bench itself.
SOURCES = ("app", "site", "bench")


def meets_severity(severity: str, minimum: str) -> bool:
	"""True when `severity` is at least as severe as `minimum`."""
	return SEVERITIES.index(severity) <= SEVERITIES.index(minimum)


@dataclass(frozen=True)
class Match:
	type: str
	paths: tuple[str, ...] = ()
	patterns: tuple[str, ...] = ()
	keys: tuple[str, ...] = ()
	doctypes: tuple[str, ...] = ()
	fields: tuple[str, ...] = ()
	filters: tuple[tuple[str, str | int | float], ...] = ()
	title_field: str = ""
	with_kwargs: tuple[str, ...] = ()
	with_positional_args: int = 0
	returns: int = 0
	url_host: str = ""
	python: str = ""
	frappe: str = ""
	node: str = ""
	branch: str = ""
	dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
	id: str
	title: str
	severity: str
	match: Match
	message: str
	replacement: str
	references: tuple[str, ...]
	fix: str = ""
	shim: str = ""


@dataclass(frozen=True)
class RuleSet:
	"""What `rules/<target>/target.yaml` says about the rules beside it."""

	target: str
	released: bool
	checked: str
	against: str


@dataclass(frozen=True)
class Finding:
	rule: Rule
	file: str
	line: int | None
	snippet: str
	app: str | None = None
	source: str = "app"
	stops_migrate: bool = False


@dataclass
class Report:
	site: str | None
	target: str
	apps: list[str]
	findings: list[Finding] = field(default_factory=list)
	unparsable_files: list[str] = field(default_factory=list)
	missing_apps: list[str] = field(default_factory=list)
	unreadable_files: list[str] = field(default_factory=list)
	not_checked: list[str] = field(default_factory=list)
	frappe_version: str = ""
	ruleset: RuleSet | None = None
	upstream_apps: dict[str, str] = field(default_factory=dict)
	upstream_findings: list[Finding] = field(default_factory=list)
	ran_patch_findings: list[Finding] = field(default_factory=list)
	suppressed: int = 0
	baselined: int = 0

	def fails(self, fail_on: str) -> bool:
		"""True when a counted finding is at `fail_on` severity or worse."""
		return fail_on != "never" and any(
			meets_severity(finding.rule.severity, fail_on) for finding in self.findings
		)


def rules_by_doctype(rules: list[Rule]) -> dict[str, Rule]:
	return {
		doctype: rule for rule in rules if rule.match.type == "doctype" for doctype in rule.match.doctypes
	}


def rules_by_doctype_field(rules: list[Rule]) -> dict[tuple[str, str], list[Rule]]:
	"""The doctype_field rules, under each (doctype, fieldname) they list."""
	table: dict[tuple[str, str], list[Rule]] = {}
	for rule in rules:
		if rule.match.type == "doctype_field":
			for entry in rule.match.fields:
				doctype, _, fieldname = entry.partition(".")
				table.setdefault((doctype, fieldname), []).append(rule)
	return table
