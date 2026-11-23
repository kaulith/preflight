import json

import pytest

from preflight.app_scan import build_path_report
from preflight.compatibility_scanner import CompatibilityScanner
from preflight.rule_loader import load_rules

RULES = {rule.id: rule for rule in load_rules("v17")}
USE_MYSQLCLIENT = RULES["v17-use-mysqlclient-config"]
scanner = CompatibilityScanner([USE_MYSQLCLIENT])


@pytest.fixture
def bench(tmp_path):
	"""A sites directory holding one site."""
	(tmp_path / "northwind.localhost").mkdir()
	return tmp_path


def write_config(bench, site=None, common=None):
	if site is not None:
		(bench / "northwind.localhost" / "site_config.json").write_text(json.dumps(site))
	if common is not None:
		(bench / "common_site_config.json").write_text(json.dumps(common))


def scan_config(bench, db_type="mariadb"):
	return scanner.scan_site_config(bench / "northwind.localhost", bench, db_type)


@pytest.mark.parametrize("value", [0, False, "", None])
def test_a_falsy_key_is_reported_without_its_value(bench, value):
	write_config(bench, site={"use_mysqlclient": value, "db_password": "s3cret"})
	(finding,), unread = scan_config(bench)
	assert (finding.file, finding.line, finding.snippet, finding.source) == (
		"site_config.json",
		None,
		"use_mysqlclient: falsy",
		"site",
	)
	assert unread == []


@pytest.mark.parametrize("config", [{}, {"use_mysqlclient": 1}, {"use_mysqlclient": "0"}])
def test_an_absent_or_truthy_key_is_not_reported(bench, config):
	write_config(bench, site=config, common={})
	assert scan_config(bench) == ([], [])


def test_the_site_config_wins_over_the_common_config(bench):
	write_config(bench, site={"use_mysqlclient": 1}, common={"use_mysqlclient": 0})
	assert scan_config(bench) == ([], [])


def test_the_common_config_is_read_when_the_site_has_no_key(bench):
	write_config(bench, site={}, common={"use_mysqlclient": 0})
	(finding,), _ = scan_config(bench)
	assert finding.file == "common_site_config.json"


def test_a_site_on_another_database_is_not_reported(bench):
	write_config(bench, site={"use_mysqlclient": 0})
	assert scan_config(bench, db_type="postgres") == ([], [])


@pytest.mark.parametrize("content", ['{"use_mysqlclient": 0', "[]", b"\xff\xfe"])
def test_a_malformed_site_config_is_named_and_leaves_the_key_unjudged(bench, content):
	path = bench / "northwind.localhost" / "site_config.json"
	path.write_bytes(content if isinstance(content, bytes) else content.encode())
	write_config(bench, common={"use_mysqlclient": 0})
	assert scan_config(bench) == ([], ["site_config.json: could not be read, its config keys not checked"])


def test_a_key_in_the_site_config_is_reported_past_a_malformed_common_config(bench):
	write_config(bench, site={"use_mysqlclient": 0})
	(bench / "common_site_config.json").write_text("{")
	(finding,), unread = scan_config(bench)
	assert finding.file == "site_config.json"
	assert unread == []


def test_path_mode_says_the_config_was_not_checked(tmp_path):
	app = tmp_path / "northwind"
	app.mkdir()
	(app / "hooks.py").touch()
	report = build_path_report([USE_MYSQLCLIENT], "v17", [app])
	assert "site config: --path reads no site, its config keys not checked" in report.not_checked
	assert report.findings == []


NOTIFICATION = {"channel": "Email", "is_standard": 0, "subject": None, "email_template": None}
SITE_RECORDS = [
	(
		"v17-server-script-guest-rate-limit",
		{"script_type": "API", "allow_guest": 1, "enable_rate_limit": 0, "disabled": 0},
		{"enable_rate_limit": 1},
	),
	("v17-notification-email-subject", NOTIFICATION, {"subject": "Invoice due"}),
	("v17-notification-slack-subject", {**NOTIFICATION, "channel": "Slack"}, {"subject": "Invoice due"}),
	(
		"v17-notification-system-subject",
		{**NOTIFICATION, "channel": "System Notification"},
		{"channel": "SMS"},
	),
	(
		"v17-web-form-allow-delete",
		{"is_standard": 0, "allow_delete": 1, "allow_multiple": 0},
		{"allow_multiple": 1},
	),
	("v17-auto-email-report-run-as", {"user": "Administrator"}, {"user": "priya.nair@example.com"}),
]


@pytest.mark.parametrize("rule_id, breaking, near_miss", SITE_RECORDS)
def test_a_site_record_rule_selects_only_the_records_that_break(monkeypatch, rule_id, breaking, near_miss):
	frappe = pytest.importorskip("frappe")
	from preflight import scan

	rows = [
		frappe._dict(name="Breaking", **breaking),
		frappe._dict({"name": "Near Miss", **breaking, **near_miss}),
	]

	def get_all(doctype, filters, fields, order_by):
		return [
			row
			for row in rows
			if all(
				(row[field] or "") == value if value == "" else row[field] == value
				for field, value in filters.items()
			)
		]

	monkeypatch.setattr(scan, "record_filters", lambda doctype, filters, title_field: dict(filters))
	monkeypatch.setattr(frappe, "get_all", get_all)
	(finding,) = scan.site_records([RULES[rule_id]])
	assert finding.file.endswith(": Breaking")
	assert finding.source == "site"
