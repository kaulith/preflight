import pytest

frappe = pytest.importorskip("frappe")

from preflight.rule_loader import load_rules
from preflight.scan import site_records

RULES = load_rules("v16")


@pytest.fixture
def repost_types(site, require_doctypes):
	require_doctypes("Repost Accounting Ledger Settings")
	try:
		settings = frappe.get_doc("Repost Accounting Ledger Settings")
		not_allowed = settings.append("allowed_types", {"document_type": "Payment Entry", "allowed": 0})
		allowed = settings.append("allowed_types", {"document_type": "Sales Invoice", "allowed": 1})
		settings.save()
		yield not_allowed.name, allowed.name
	finally:
		frappe.db.rollback()


def test_a_repost_type_not_allowed_under_the_v15_settings_is_reported(site, repost_types):
	not_allowed, allowed = repost_types
	found = {
		finding.file: finding.snippet
		for finding in site_records(RULES)
		if finding.rule.id == "v16-erpnext-repost-allowed-types"
	}
	assert found[f"Repost Allowed Types: {not_allowed}"] == (
		"Payment Entry, parenttype = 'Repost Accounting Ledger Settings', allowed = 0"
	)
	assert f"Repost Allowed Types: {allowed}" not in found


@pytest.fixture
def workspaces(site):
	if frappe.get_meta("Workspace").get_field("module").reqd:
		pytest.skip(f"{site} gives every workspace a module")
	try:
		public = frappe.get_doc(
			doctype="Workspace",
			label="Northwind Operations",
			title="Northwind Operations",
			public=1,
			content="[]",
		).insert()
		private = frappe.get_doc(
			doctype="Workspace",
			label="Northwind Planning-Administrator",
			title="Northwind Planning",
			for_user="Administrator",
			content="[]",
		).insert()
		yield public.name, private.name
	finally:
		frappe.db.rollback()


def test_a_public_workspace_with_no_module_is_reported(site, workspaces):
	public, private = workspaces
	found = {
		finding.file
		for finding in site_records(RULES)
		if finding.rule.id == "v16-custom-workspace-navigation"
	}
	assert f"Workspace: {public}" in found
	assert f"Workspace: {private}" not in found


def test_a_private_workspace_is_reported_under_its_owner(site, workspaces):
	public, private = workspaces
	found = {
		finding.file: finding.snippet
		for finding in site_records(RULES)
		if finding.rule.id == "v16-private-workspace-my-space"
	}
	assert found[f"Workspace: {private}"] == "Administrator, public = 0"
	assert f"Workspace: {public}" not in found


@pytest.fixture
def custom_module_workspaces(site):
	"""Written as v15 leaves the rows, past the hooks that would export a public workspace with a module."""
	try:
		frappe.get_doc(
			doctype="Module Def", module_name="Fleet Management", app_name="frappe", custom=1
		).db_insert()
		for title, module in (("Fleet Dispatch", "Fleet Management"), ("Northwind Operations", "Core")):
			frappe.get_doc(
				doctype="Workspace",
				name=title,
				label=title,
				title=title,
				module=module,
				public=1,
				content="[]",
			).db_insert()
		yield
	finally:
		frappe.db.rollback()


def test_a_public_workspace_in_a_custom_module_is_reported(site, custom_module_workspaces):
	found = {
		finding.file: finding.snippet
		for finding in site_records(RULES)
		if finding.rule.id == "v16-custom-module-workspace-dock"
	}
	assert found["Workspace: Fleet Dispatch"] == "Fleet Management, public = 1, module.custom = 1"
	assert "Workspace: Northwind Operations" not in found
