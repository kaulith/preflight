import json

from preflight.models import Match, Rule
from preflight.rule_loader import load_rules
from preflight.schema_scanner import SchemaRecord, SchemaScanner, app_doctype_fields

scanner = SchemaScanner(load_rules("v16"))

DOCTYPE_JSON = {
	"doctype": "DocType",
	"name": "Digest Subscription",
	"fields": [
		{"fieldname": "newsletter", "fieldtype": "Link", "options": "Newsletter"},
		{"fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
		{"fieldname": "subject", "fieldtype": "Data"},
	],
}


def test_a_record_on_a_removed_doctype_is_reported():
	records = [
		SchemaRecord("Custom Field: Newsletter-digest_id", "Newsletter", "custom field digest_id"),
		SchemaRecord("Custom Field: Contact-digest_id", "Contact", "custom field digest_id"),
	]
	(finding,) = scanner.scan(records)
	assert finding.rule.id == "v16-removed-newsletter-doctypes"
	assert finding.file == "Custom Field: Newsletter-digest_id"
	assert finding.snippet == "custom field digest_id"
	assert finding.line is None


def test_a_record_on_a_listed_field_of_its_doctype_is_reported():
	rule = Rule(
		id="digest-rule",
		title="Digest rule",
		severity="error",
		match=Match(type="doctype_field", fields=("Sales Invoice.due_date",)),
		message="Digest rule.",
		replacement="None.",
		references=(),
	)
	records = [
		SchemaRecord(
			"Property Setter: Sales Invoice-due_date-reqd", "Sales Invoice", "property setter", "due_date"
		),
		SchemaRecord(
			"Property Setter: Purchase Invoice-due_date-reqd",
			"Purchase Invoice",
			"property setter",
			"due_date",
		),
	]
	(finding,) = SchemaScanner([rule]).scan(records)
	assert finding.file == "Property Setter: Sales Invoice-due_date-reqd"


def test_link_fields_in_an_app_doctype_are_matched(tmp_path):
	path = tmp_path / "digest" / "doctype" / "digest_subscription"
	path.mkdir(parents=True)
	(path / "digest_subscription.json").write_text(json.dumps(DOCTYPE_JSON))
	(finding,) = scanner.scan(app_doctype_fields(tmp_path))
	assert finding.rule.id == "v16-removed-newsletter-doctypes"
	assert finding.file.endswith("digest/doctype/digest_subscription/digest_subscription.json")
	assert finding.snippet == "link field newsletter"


def test_json_outside_a_doctype_folder_is_not_read(tmp_path):
	path = tmp_path / "digest" / "fixtures"
	path.mkdir(parents=True)
	(path / "custom_field.json").write_text(json.dumps([DOCTYPE_JSON]))
	assert app_doctype_fields(tmp_path) == []
