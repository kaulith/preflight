import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_outstanding_reference_documents
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.utils import get_company_default
from erpnext.erpnext_integrations.doctype.plaid_settings.plaid_settings import get_link_token_for_update

payment_account = get_bank_cash_account("Cash", "Northwind Traders").get("account")
cost_center = get_company_default("Northwind Traders", "cost_center")
references = get_outstanding_reference_documents({"company": "Northwind Traders"})
link_token = get_link_token_for_update("access-sandbox-northwind")
tax_item = frappe.db.get_value("Tax Rule", "Domestic Sales", "item")
tax_item_group = frappe.get_doc("Tax Rule", "Domestic Sales").item_group
show_pay_button = frappe.db.get_single_value("Buying Settings", "show_pay_button")
