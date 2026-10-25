import frappe
from erpnext.accounts.doctype.accounts_settings.accounts_settings import (
	set_allow_on_submit_for_dimension_fields,
)
from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import get_invoices
from erpnext.accounts.doctype.tax_withholding_category.tax_withholding_category import TaxWithholdingDetails
from erpnext.accounts.utils import get_balance_on
from erpnext.assets.doctype.asset import depreciation
from erpnext.assets.doctype.asset_repair.asset_repair import get_unallocated_repair_cost
from erpnext.manufacturing.doctype.bom.bom import get_secondary_items_from_sub_assemblies
from erpnext.projects.report.timesheet_billing_summary.timesheet_billing_summary import get_data
from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order
from erpnext.stock.doctype.stock_closing_entry.stock_closing_entry import prepare_closing_stock_balance


def dimension_setup(doctypes):
	set_allow_on_submit_for_dimension_fields(doctypes)


def withholding_details(invoice):
	return TaxWithholdingDetails(
		["TDS - 194C"], None, invoice.posting_date, "Supplier", invoice.supplier, invoice.company
	).get()


def sub_assembly_secondary_items(bom, company, qty):
	return get_secondary_items_from_sub_assemblies(bom, company, qty)


def billing(filters):
	return get_data(filters)


def close_stock(name):
	prepare_closing_stock_balance(name)


def utm_sources():
	return frappe.get_all("UTM Source", pluck="name")


def leads_by_source(source):
	return frappe.get_all("Lead", filters={"utm_source": source}, pluck="name")


def withholding(invoice):
	return frappe.db.get_value("Purchase Invoice", invoice, ["apply_tds", "tax_withholding_group"])


def payment_withholding_category(payment):
	return frappe.db.get_value("Payment Entry", payment, "tax_withholding_category")


def secondary_rows(stock_entry):
	return frappe.get_all(
		"Stock Entry Detail", filters={"parent": stock_entry, "secondary_item_type": "Scrap"}
	)


def company_defaults(company):
	return frappe.db.get_value("Company", company, ["default_wip_warehouse", "accounts_frozen_till_date"])


def asset_value(asset):
	return frappe.db.get_value("Asset", asset, "net_purchase_amount")


def workstation_rate(workstation):
	return frappe.db.get_value("Workstation", workstation, "hour_rate")


def contact_salutation(contact):
	return frappe.db.get_value("Contact", contact, "salutation")


def invoice_customer(invoice):
	return frappe.db.get_value("Sales Invoice", invoice, "customer")


def repost_types():
	return frappe.get_single("Accounts Settings").repost_allowed_types


def party_balance(customer):
	return get_balance_on(party_type="Customer", party=customer)


def closing_invoices(opening_entry, period_end_date):
	return get_invoices(
		opening_entry.period_start_date, period_end_date, opening_entry.pos_profile, opening_entry.user
	)


def depreciation_series():
	return depreciation.get_depr_cost_center_and_series()


def book_depreciation(schedule, posting_date, dimensions):
	depreciation.make_depreciation_entry(schedule, posting_date, accounting_dimensions=dimensions)
	depreciation._make_depreciation_entry(schedule, posting_date, None, None, dimensions)


def repair_cost(purchase_invoice, expense_account):
	return get_unallocated_repair_cost(purchase_invoice, expense_account)


def supplier_orders(sales_order, items):
	return make_purchase_order(sales_order, items)


def opportunities_by_source(company, from_date, to_date):
	return frappe.call(
		"erpnext.selling.page.sales_funnel.sales_funnel.get_opp_by_utm_source",
		from_date=from_date,
		to_date=to_date,
		company=company,
	)
