import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_and_account_balance
from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import get_pos_invoices
from erpnext.accounts.doctype.repost_accounting_ledger_settings.repost_accounting_ledger_settings import (
	set_allow_on_submit_for_dimension_fields,
)
from erpnext.accounts.doctype.tax_withholding_category.tax_withholding_category import (
	get_party_tax_withholding_details,
)
from erpnext.assets.doctype.asset import depreciation
from erpnext.assets.doctype.asset_repair.asset_repair import get_repair_cost_for_purchase_invoice
from erpnext.manufacturing.doctype.bom.bom import get_scrap_items_from_sub_assemblies
from erpnext.portal.doctype.homepage.homepage import Homepage
from erpnext.projects.report.billing_summary import get_data as get_billing_data
from erpnext.selling.doctype.sales_order.sales_order import make_purchase_order_for_default_supplier
from erpnext.stock.doctype.closing_stock_balance.closing_stock_balance import prepare_closing_stock_balance


class SupplierHomepage(Homepage):
	pass


def dimension_setup(doctypes):
	set_allow_on_submit_for_dimension_fields(doctypes)


def withholding_details(invoice):
	return get_party_tax_withholding_details(invoice)


def sub_assembly_scrap(bom, company, qty):
	return get_scrap_items_from_sub_assemblies(bom, company, qty)


def billing(filters):
	return get_billing_data(filters)


def close_stock(name):
	prepare_closing_stock_balance(name)


def lead_sources():
	return frappe.get_all("Lead Source", pluck="name")


def home_sections():
	return frappe.get_all("Homepage Section", fields=["name", "section_order"])


def last_closing_balance(company):
	return frappe.get_last_doc("Closing Stock Balance", filters={"company": company})


def withheld_vouchers(invoice):
	return frappe.get_all("Tax Withheld Vouchers", filters={"parent": invoice}, fields=["voucher_name"])


def bom_scrap(bom):
	return frappe.get_all("BOM Scrap Item", filters={"parent": bom}, fields=["item_code", "stock_qty"])


def allow_reposting(doctype):
	settings = frappe.get_single("Repost Accounting Ledger Settings")
	settings.append("allowed_types", {"document_type": doctype, "allowed": 1})
	settings.save()


def leads_by_source(source):
	return frappe.get_all("Lead", filters={"source": source}, pluck="name")


def withholding_category(invoice):
	return frappe.db.get_value("Purchase Invoice", invoice, "tax_withholding_category")


def scrap_rows(stock_entry):
	return frappe.get_all(
		"Stock Entry Detail", filters={"parent": stock_entry, "is_scrap_item": 1}, pluck="name"
	)


def item_taxes(invoice):
	return frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": invoice},
		fields=["account_head", "item_wise_tax_detail"],
	)


def frozen_till():
	return frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")


def asset_value(asset):
	return frappe.db.get_value("Asset", asset, "gross_purchase_amount")


def labour_rate(workstation):
	return frappe.db.get_value("Workstation", workstation, "hour_rate_labour")


def subcontracted(order):
	return frappe.get_all("Purchase Order Item", filters={"parent": order}, fields=["subcontracted_quantity"])


def creation_document(serial_no):
	return frappe.db.get_value("Serial No", serial_no, "purchase_document_no")


def customer_salutation(customer):
	return frappe.db.get_value("Customer", customer, "salutation")


def party_balance(company, posting_date, customer):
	return get_party_and_account_balance(company, posting_date, ptype="Customer", pty=customer)


def closing_invoices(opening_entry, period_end_date):
	return get_pos_invoices(
		opening_entry.period_start_date, period_end_date, opening_entry.pos_profile, opening_entry.user
	)


def depreciation_series():
	return depreciation.get_depreciation_cost_center_and_depreciation_series_for_company()


def book_depreciation(schedule, posting_date, accounts, cost_center_and_series, dimensions):
	depreciation.make_depreciation_entry(asset_depr_schedule_name=schedule, date=posting_date)
	depreciation.make_depreciation_entry(schedule, posting_date, credit_and_debit_accounts=accounts)
	depreciation._make_depreciation_entry(
		schedule, posting_date, None, None, accounts, cost_center_and_series, dimensions
	)


def repair_cost(purchase_invoice):
	return get_repair_cost_for_purchase_invoice(purchase_invoice)


def supplier_orders(sales_order, items):
	return make_purchase_order_for_default_supplier(sales_order, items)


def opportunities_by_source(company, from_date, to_date):
	return frappe.call(
		"erpnext.selling.page.sales_funnel.sales_funnel.get_opp_by_lead_source",
		from_date=from_date,
		to_date=to_date,
		company=company,
	)
