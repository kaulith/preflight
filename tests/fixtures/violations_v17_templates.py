import frappe
from frappe.database.postgres.database import modify_values

frappe.db._conn.get_transaction_status()
frappe.db._conn.set_isolation_level(1)
frappe.db._cursor.copy_expert('COPY "tabToDo" TO STDOUT', modify_values)
