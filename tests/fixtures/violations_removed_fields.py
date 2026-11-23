import frappe

scrap_rows = frappe.get_doc("BOM", "BOM-0001").scrap_items
budget_rows = frappe.get_doc("Budget", "BUDGET-0001").accounts
vouchers = frappe.get_doc("Purchase Invoice", "PINV-0001").tax_withheld_vouchers
show_balance = frappe.db.get_single_value("Accounts Settings", "show_party_balance")
icons = frappe.get_all("Desktop Icon", filters={"module_name": "Accounts"})
title = frappe.db.get_value("Notification", "Order Approved", "notification_title")
condition = frappe.db.get_value("Inventory Dimension", "Shelf", "mandatory_depends_on")
warehouse = frappe.get_doc("BOM Creator", "BOM-CRE-0001").items[0].source_warehouse
