import ast
from pathlib import Path

import pytest

from preflight.hooks_scanner import HooksScanner, can_return_none, hooked_doctypes
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
APP = FIXTURES / "digest"

scanner = HooksScanner(load_rules("v16"))


def lines_by_rule(source):
	lines = {}
	for finding in scanner.scan(source, "digest/hooks.py", APP):
		lines.setdefault(finding.rule.id, []).append(finding.line)
	return {rule_id: sorted(rule_lines) for rule_id, rule_lines in lines.items()}


def test_declared_hooks_are_reported_on_their_lines():
	assert lines_by_rule((FIXTURES / "hooks_violations.py").read_text()) == {
		"v16-has-permission-hook-returns-none": [7],
		"v16-has-permission-hook-unreadable": [8],
		"v16-override-doctype-class-subclass": [11],
		"v16-removed-changelog-feed-hook": [15],
		"v16-removed-leaderboards-hook": [4],
		"v16-removed-newsletter": [19],
		"v16-removed-newsletter-doctypes": [17],
	}


def test_clean_hooks_file_has_no_findings():
	assert scanner.scan((FIXTURES / "hooks_clean.py").read_text(), "digest/hooks.py", APP) == []


def test_app_shipping_a_workspace_without_add_to_apps_screen_is_reported():
	findings = scanner.missing_hooks((FIXTURES / "hooks_violations.py").read_text(), "digest/hooks.py", APP)
	assert [(finding.rule.id, finding.line, finding.snippet) for finding in findings] == [
		(
			"v16-app-workspaces-apps-screen",
			None,
			"digest/deliveries/workspace/deliveries/deliveries.json",
		)
	]


def test_app_declaring_add_to_apps_screen_is_not_reported():
	assert scanner.missing_hooks((FIXTURES / "hooks_clean.py").read_text(), "digest/hooks.py", APP) == []


def test_app_shipping_no_workspace_is_not_reported(tmp_path):
	assert scanner.missing_hooks('app_name = "digest"\n', "digest/hooks.py", tmp_path / "digest") == []


def test_hook_name_bound_inside_a_function_is_not_reported():
	assert lines_by_rule("def setup():\n\tleaderboards = {}\n\treturn leaderboards\n") == {}


def test_annotated_hook_is_reported():
	source = 'leaderboards: str = "digest.startup.leaderboard.get_leaderboards"\n'
	assert lines_by_rule(source) == {"v16-removed-leaderboards-hook": [1]}


def test_dotted_path_in_a_hook_key_is_reported():
	source = (
		'override_whitelisted_methods = {"frappe.website.doctype.blog_post.blog_post.get_blog_list": '
		'"digest.api.get_blog_list"}\n'
	)
	assert lines_by_rule(source) == {"v16-removed-blog": [1]}


def test_dotted_path_inside_a_longer_string_is_not_reported():
	assert lines_by_rule('app_description = "Mails frappe.email.doctype.newsletter digests"\n') == {}


def test_dotted_path_a_string_rule_reports_is_not_reported_again():
	source = (
		'override_whitelisted_methods = {"frappe.utils.weasyprint.download_pdf": "digest.pdf.download"}\n'
	)
	assert HooksScanner(load_rules("v17")).scan(source, "digest/hooks.py", APP) == []


def test_override_inheriting_the_controller_is_not_reported():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.web_page.ReviewedWebPage"}\n'
	assert lines_by_rule(source) == {}


def test_override_inheriting_under_an_alias_is_not_reported():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.review.AliasedWebPage"}\n'
	assert lines_by_rule(source) == {}


def test_override_inheriting_through_another_class_is_not_reported():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.review.ChainedWebPage"}\n'
	assert lines_by_rule(source) == {}


def test_override_inheriting_through_a_relative_import_is_not_reported():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.review.RelativeWebPage"}\n'
	assert lines_by_rule(source) == {}


def test_override_the_app_does_not_hold_is_not_reported():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.missing.GhostWebPage"}\n'
	assert lines_by_rule(source) == {}


def test_override_reported_on_the_entry_not_the_hook():
	source = (
		"override_doctype_class = {\n"
		'\t"Web Page": "digest.overrides.web_page.ReviewedWebPage",\n'
		'\t"Web Form": "digest.overrides.web_page.DigestWebPage",\n'
		"}\n"
	)
	assert lines_by_rule(source) == {"v16-override-doctype-class-subclass": [3]}


def test_override_rules_are_skipped_without_an_app_path():
	source = 'override_doctype_class = {"Web Page": "digest.overrides.web_page.DigestWebPage"}\n'
	assert scanner.scan(source, "digest/hooks.py") == []


def test_permission_rules_are_skipped_without_an_app_path():
	source = 'has_permission = {"Sales Invoice": "digest.permissions.sales_invoice_has_permission"}\n'
	assert scanner.scan(source, "digest/hooks.py") == []


@pytest.mark.parametrize(
	"body",
	[
		"\tif doc.owner == user:\n\t\treturn True\n",
		"\tif doc.owner == user:\n\t\treturn\n\treturn True\n",
		"\tif doc.owner == user:\n\t\treturn None\n\treturn True\n",
		'\tmatch ptype:\n\t\tcase "read":\n\t\t\treturn True\n\t\tcase "write":\n\t\t\treturn doc.owner == user\n',
		"\twhile True:\n\t\tif doc.is_new():\n\t\t\tbreak\n\t\treturn doc.owner == user\n",
	],
)
def test_function_that_can_return_none(body):
	assert can_return_none(ast.parse(f"def has_permission(doc, ptype, user):\n{body}").body[0])


@pytest.mark.parametrize(
	"body",
	[
		"\tif doc.owner == user:\n\t\treturn True\n\telse:\n\t\treturn False\n",
		'\tif doc.owner == user:\n\t\treturn True\n\tfrappe.throw("Not permitted")\n',
		'\tif doc.owner == user:\n\t\treturn True\n\tthrow("Not permitted")\n',
		"\ttry:\n\t\treturn user in doc.get_assignees()\n\texcept frappe.DoesNotExistError:\n\t\treturn False\n",
		"\tdef owner():\n\t\treturn\n\treturn owner() == user\n",
		'\tmatch ptype:\n\t\tcase "read":\n\t\t\treturn True\n\t\tcase _:\n\t\t\treturn doc.owner == user\n',
		(
			"\twhile True:\n\t\tfor row in doc.shared_with:\n\t\t\tif row.user == user:\n\t\t\t\tbreak\n"
			"\t\treturn doc.owner == user\n"
		),
	],
)
def test_function_that_answers_on_every_path(body):
	assert not can_return_none(ast.parse(f"def has_permission(doc, ptype, user):\n{body}").body[0])


def test_function_imported_into_the_hooked_module_is_read_where_it_is_defined():
	source = 'has_permission = {"Delivery Note": "digest.access.delivery_note_has_permission"}\n'
	assert lines_by_rule(source) == {"v16-has-permission-hook-returns-none": [1]}


def test_function_imported_in_a_cycle_is_unreadable():
	source = 'has_permission = {"Journal Entry": "digest.access.journal_entry_has_permission"}\n'
	assert lines_by_rule(source) == {"v16-has-permission-hook-unreadable": [1]}


def test_finding_carries_file_and_snippet():
	source = 'app_name = "digest"\noverride_doctype_class = {"Web Page": "digest.overrides.web_page.DigestWebPage"}\n'
	(finding,) = scanner.scan(source, "digest/hooks.py", APP)
	assert (finding.file, finding.line) == ("digest/hooks.py", 2)
	assert (
		finding.snippet == 'override_doctype_class = {"Web Page": "digest.overrides.web_page.DigestWebPage"}'
	)


def test_function_hooked_for_two_doctypes_is_hooked_to_both(tmp_path):
	(tmp_path / "hooks.py").write_text(
		"doc_events = {\n"
		'\t"Sales Invoice": {"on_submit": ["digest.events.notify_customer"]},\n'
		'\t"Delivery Note": {"on_submit": "digest.events.notify_customer"},\n'
		"}\n",
		encoding="utf-8",
	)
	assert hooked_doctypes(tmp_path) == {
		"digest.events": {"notify_customer": {"Sales Invoice", "Delivery Note"}}
	}


def test_class_overriding_a_doctype_is_hooked_to_it(tmp_path):
	(tmp_path / "hooks.py").write_text(
		'override_doctype_class = {"Payment Entry": "digest.overrides.DigestPaymentEntry"}\n',
		encoding="utf-8",
	)
	assert hooked_doctypes(tmp_path) == {"digest.overrides": {"DigestPaymentEntry": {"Payment Entry"}}}


def test_handler_for_every_doctype_is_hooked_to_none(tmp_path):
	(tmp_path / "hooks.py").write_text(
		'doc_events = {"*": {"on_update": "digest.events.log_change"}}\n', encoding="utf-8"
	)
	assert hooked_doctypes(tmp_path) == {}


def test_hooks_file_that_does_not_parse_hooks_nothing(tmp_path):
	(tmp_path / "hooks.py").write_text("doc_events = {\n", encoding="utf-8")
	assert hooked_doctypes(tmp_path) == {}


def test_invalid_python_raises_syntax_error():
	with pytest.raises(SyntaxError):
		scanner.scan("has_permission = {\n", "digest/hooks.py")
