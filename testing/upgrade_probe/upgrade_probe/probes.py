"""One function per v15 API the upgrade might take away.

Imports of modules v16 removed are local to the function that needs them, so each probe fails on
its own instead of taking the module down with it.
"""

import frappe
from frappe.utils import get_gravatar, gzip_compress
from frappe.utils.data import get_number_format_info


def get_leaderboards():
	"""The target of the leaderboards hook, which v16 stopped reading."""
	return {
		"ToDo": {
			"fields": [{"fieldname": "priority", "fieldtype": "Select"}],
			"method": "upgrade_probe.probes.leaderboard_rows",
		}
	}


def leaderboard_rows(date_range, company, field, limit=10):
	return frappe.get_all("ToDo", fields=["name", "priority"], limit=limit)


def compress_digest(payload: str) -> bytes:
	return gzip_compress(payload.encode())


def owner_avatar(user: str) -> str:
	return get_gravatar(user)


def number_separators():
	number_format = frappe.db.get_single_value("System Settings", "number_format")
	return get_number_format_info(number_format)


def blog_titles() -> list[str]:
	return frappe.get_all("Blog Post", pluck="name", limit=5)


def blog_list():
	from frappe.website.doctype.blog_post.blog_post import get_blog_list

	return get_blog_list(None, None, limit_page_length=5)


def energy_points(user: str):
	from frappe.social.doctype.energy_point_log.energy_point_log import get_energy_points

	return get_energy_points(user)


def seed_todo_records():
	from frappe.tests_runner import make_test_records

	make_test_records("ToDo")
	return frappe.get_test_records("ToDo")


def offsite_backup_enabled() -> bool:
	return bool(frappe.db.get_single_value("Dropbox Settings", "enabled"))


def cached_status(name: str):
	"""Reads the value cache by the flat key v15 used."""
	frappe.db.get_value("ToDo", name, "status")
	return frappe.db.value_cache.get(("ToDo", name, "status"))


def missing_column(error) -> bool:
	return frappe.db.is_column_missing(error)


def oldest_todo():
	"""Takes the first row of a default-ordered read, which v16 orders by creation."""
	rows = frappe.get_all("ToDo", fields=["name", "description"], limit=1)
	return rows[0] if rows else None


def transaction_log_rows():
	"""Names a removed doctype in raw SQL, where no matcher can see it."""
	return frappe.db.sql("select name from `tabTransaction Log` limit 1", as_dict=True)
