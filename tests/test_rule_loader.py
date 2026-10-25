import pytest

from preflight.models import MATCH_TYPES
from preflight.rule_loader import MATCH_TYPE_KEYS, RULES_PATH, RuleError, load_rules, load_ruleset

MAKE_ESC_RULE = (RULES_PATH / "v16" / "v16-deprecated-make-esc.yaml").read_text()
LIST_SIDEBAR_RULE = (RULES_PATH / "v16" / "v16-removed-list-sidebar.yaml").read_text()
BLOG_DOCTYPES_RULE = (RULES_PATH / "v16" / "v16-removed-blog-doctypes.yaml").read_text()
ENQUEUE_JOB_NAME_RULE = (RULES_PATH / "v17" / "v17-deprecated-enqueue-job-name.yaml").read_text()
DEPENDENCY_PINS_RULE = (RULES_PATH / "v16" / "v16-app-dependency-pins.yaml").read_text()
REPOST_TYPES_RULE = (RULES_PATH / "v16" / "v16-erpnext-repost-allowed-types.yaml").read_text()
RULESET = 'released: true\nchecked: "2026-10-25"\nagainst: frappe v16.53.0\n'


def write_rule(tmp_path, content, name="v16-deprecated-make-esc.yaml"):
	ruleset = tmp_path / "v16"
	ruleset.mkdir(exist_ok=True)
	(ruleset / "target.yaml").write_text(RULESET)
	(ruleset / name).write_text(content)


def rule_files(target):
	return [path for path in (RULES_PATH / target).glob("*.yaml") if path.name != "target.yaml"]


def test_v16_rules_load():
	rules = load_rules("v16")
	assert len(rules) == len(rule_files("v16"))
	assert "v16-removed-transaction-log" in {rule.id for rule in rules}
	assert all(rule.message and rule.replacement and rule.references for rule in rules)


def test_v17_rule_still_on_develop_is_a_warning():
	rules = load_rules("v17")
	assert len(rules) == len(rule_files("v17"))
	assert {rule.severity for rule in rules if rule.id.startswith("v17-deprecated-")} == {"warning"}
	assert {rule.severity for rule in rules if rule.id.startswith(("v17-removed-", "v17-moved-"))} == {
		"error"
	}


def test_unknown_target_lists_only_released_targets():
	with pytest.raises(RuleError, match="Available targets: v16$"):
		load_rules("v99")


def test_v17_is_not_released():
	assert load_ruleset("v16").released
	assert not load_ruleset("v17").released


def test_target_without_its_target_file_is_rejected(tmp_path):
	write_rule(tmp_path, MAKE_ESC_RULE)
	(tmp_path / "v16" / "target.yaml").unlink()
	with pytest.raises(RuleError, match="v16: no target.yaml"):
		load_rules("v16", rules_path=tmp_path)


@pytest.mark.parametrize("target", ["", "./v16", "v18"])
def test_target_that_is_not_a_version_with_rules_is_rejected(tmp_path, target):
	write_rule(tmp_path, MAKE_ESC_RULE)
	(tmp_path / "v18").mkdir()
	with pytest.raises(RuleError, match="No rules for target"):
		load_rules(target, rules_path=tmp_path)


def test_every_match_type_has_its_keys():
	assert set(MATCH_TYPE_KEYS) == set(MATCH_TYPES)


def test_valid_rule_loads(tmp_path):
	write_rule(tmp_path, MAKE_ESC_RULE)
	(rule,) = load_rules("v16", rules_path=tmp_path)
	assert rule.match.paths == ("frappe.utils.make_esc",)
	assert rule.replacement == "Escape the characters in your own code."


@pytest.mark.parametrize(
	"original, broken",
	[
		("severity: warning", "severity: fatal"),
		("type: import_path", "type: regex"),
		("id: v16-deprecated-make-esc", "id: v16-make-esc"),
		("paths:\n    - frappe.utils.make_esc", "paths: frappe.utils.make_esc"),
		("replacement: Escape the characters in your own code.", ""),
		("references:\n  -", "references: [\n  -"),
		("fix: before", "fix: later"),
	],
)
def test_invalid_rule_names_the_file(tmp_path, original, broken):
	assert original in MAKE_ESC_RULE
	write_rule(tmp_path, MAKE_ESC_RULE.replace(original, broken))
	with pytest.raises(RuleError, match="v16-deprecated-make-esc.yaml"):
		load_rules("v16", rules_path=tmp_path)


def test_two_rules_on_one_doctype_are_rejected(tmp_path):
	write_rule(tmp_path, BLOG_DOCTYPES_RULE, "v16-removed-blog-doctypes.yaml")
	write_rule(
		tmp_path,
		BLOG_DOCTYPES_RULE.replace("id: v16-removed-blog-doctypes", "id: v16-removed-blog-again"),
		"v16-removed-blog-again.yaml",
	)
	with pytest.raises(RuleError, match="is already matched by"):
		load_rules("v16", rules_path=tmp_path)


@pytest.mark.parametrize(
	"original, broken, message",
	[
		(r"\bfrappe\.views\.ListSidebar\b", r"\bfrappe\.views\.(ListSidebar\b", "not a valid regex"),
		("patterns:", "paths:", "match.paths is not a key of a pattern rule"),
	],
)
def test_invalid_pattern_rule_names_the_problem(tmp_path, original, broken, message):
	assert original in LIST_SIDEBAR_RULE
	write_rule(tmp_path, LIST_SIDEBAR_RULE.replace(original, broken), "v16-removed-list-sidebar.yaml")
	with pytest.raises(RuleError, match=message):
		load_rules("v16", rules_path=tmp_path)


@pytest.mark.parametrize(
	"original, broken, message",
	[
		(
			"with_kwargs:\n    - job_name",
			"with_kwargs: job_name",
			"match.with_kwargs must be a non-empty list",
		),
		("with_kwargs:", "with_kwarg:", "match.with_kwarg is not a key of a call rule"),
		("severity: warning", "severity: warning\nsince: v16", "since is not a key of a rule"),
	],
)
def test_invalid_call_rule_names_the_problem(tmp_path, original, broken, message):
	assert original in ENQUEUE_JOB_NAME_RULE
	write_rule(
		tmp_path, ENQUEUE_JOB_NAME_RULE.replace(original, broken), "v17-deprecated-enqueue-job-name.yaml"
	)
	with pytest.raises(RuleError, match=message):
		load_rules("v16", rules_path=tmp_path)


def test_dependency_that_is_not_a_requirement_is_rejected(tmp_path):
	write_rule(
		tmp_path,
		DEPENDENCY_PINS_RULE.replace("Babel~=2.18.0", "Babel~2.18.0"),
		"v16-app-dependency-pins.yaml",
	)
	with pytest.raises(RuleError, match="'Babel~2.18.0' is not a requirement"):
		load_rules("v16", rules_path=tmp_path)


def test_site_record_filters_load_as_pairs(tmp_path):
	write_rule(tmp_path, REPOST_TYPES_RULE, "v16-erpnext-repost-allowed-types.yaml")
	(rule,) = load_rules("v16", rules_path=tmp_path)
	assert rule.match.filters == (("parenttype", "Repost Accounting Ledger Settings"), ("allowed", 0))
	assert rule in {rule}


@pytest.mark.parametrize(
	"original, broken, message",
	[
		("allowed: 0", "allowed: [0]", "match.filters.allowed must be one value"),
		("allowed: 0", "parent.document_type.allowed: 0", "match.filters key must be a field name"),
		(
			"title_field: document_type",
			"title_field: document type",
			"match.title_field must be a field name",
		),
	],
)
def test_invalid_site_record_rule_names_the_problem(tmp_path, original, broken, message):
	assert original in REPOST_TYPES_RULE
	write_rule(tmp_path, REPOST_TYPES_RULE.replace(original, broken), "v16-erpnext-repost-allowed-types.yaml")
	with pytest.raises(RuleError, match=message):
		load_rules("v16", rules_path=tmp_path)


def test_a_site_record_rule_may_name_the_doctype_of_a_doctype_rule(tmp_path):
	write_rule(tmp_path, BLOG_DOCTYPES_RULE, "v16-removed-blog-doctypes.yaml")
	write_rule(
		tmp_path,
		REPOST_TYPES_RULE.replace("Repost Allowed Types", "Blog Post"),
		"v16-erpnext-repost-allowed-types.yaml",
	)
	assert len(load_rules("v16", rules_path=tmp_path)) == 2
