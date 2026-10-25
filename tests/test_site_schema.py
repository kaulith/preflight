import pytest

frappe = pytest.importorskip("frappe")

from preflight.rule_loader import load_rules
from preflight.scan import site_schema
from preflight.schema_scanner import SchemaScanner

RULES = load_rules("v16")


@pytest.fixture
def seeded_customisations(site, require_doctypes):
	require_doctypes("Newsletter", "Blog Post", "Energy Point Log")
	try:
		# The flag keeps the insert off the schema: create_custom_fields sets it too, and
		# calls updatedb once at the end. A DDL statement would commit the transaction.
		frappe.flags.in_create_custom_fields = True
		try:
			custom_field = frappe.get_doc(
				doctype="Custom Field",
				dt="Newsletter",
				fieldname="digest_id",
				fieldtype="Data",
				label="Digest ID",
			).insert()
			link_field = frappe.get_doc(
				doctype="Custom Field",
				dt="Contact",
				fieldname="blog_post",
				fieldtype="Link",
				options="Blog Post",
				label="Blog Post",
			).insert()
		finally:
			frappe.flags.in_create_custom_fields = False
		property_setter = frappe.get_doc(
			doctype="Property Setter",
			doctype_or_field="DocType",
			doc_type="Energy Point Log",
			property="max_attachments",
			value="3",
		).insert()
		yield custom_field.name, link_field.name, property_setter.name
	finally:
		frappe.db.rollback()


def test_customisations_on_removed_doctypes_are_reported(site, seeded_customisations):
	custom_field, link_field, property_setter = seeded_customisations
	found = {(finding.rule.id, finding.file) for finding in SchemaScanner(RULES).scan(site_schema())}
	assert ("v16-removed-newsletter-doctypes", f"Custom Field: {custom_field}") in found
	assert ("v16-removed-blog-doctypes", f"Custom Field: {link_field}") in found
	assert ("v16-removed-energy-point-doctypes", f"Property Setter: {property_setter}") in found


def schema_of(monkeypatch, doctype: str, row: dict) -> list[tuple[str, str, str]]:
	"""The field records site_schema reads off a site whose only customisation is `row`."""
	rows = {doctype: [frappe._dict(row)]}
	monkeypatch.setattr(frappe, "get_all", lambda doctype, fields, order_by: rows.get(doctype, []))
	return [(record.label, record.doctype, record.fieldname) for record in site_schema() if record.fieldname]


def test_a_custom_field_names_the_field_it_is_inserted_after(monkeypatch):
	row = {
		"name": "Sales Invoice-digest_id",
		"dt": "Sales Invoice",
		"fieldname": "digest_id",
		"fieldtype": "Data",
		"options": None,
		"insert_after": "due_date",
	}
	assert schema_of(monkeypatch, "Custom Field", row) == [
		("Custom Field: Sales Invoice-digest_id", "Sales Invoice", "due_date")
	]


def test_a_property_setter_on_a_field_names_the_field(monkeypatch):
	row = {"name": "Sales Invoice-due_date-reqd", "doc_type": "Sales Invoice", "field_name": "due_date"}
	assert schema_of(monkeypatch, "Property Setter", row) == [
		("Property Setter: Sales Invoice-due_date-reqd", "Sales Invoice", "due_date")
	]


def test_reading_the_schema_issues_no_writes(site, seeded_customisations):
	writes = frappe.db.transaction_writes
	SchemaScanner(RULES).scan(site_schema())
	assert frappe.db.transaction_writes == writes
