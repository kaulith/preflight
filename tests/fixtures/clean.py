import gzip

import frappe
from frappe.geo.country_info import get_translated_countries
from frappe.permissions import has_permission
from frappe.utils import cint, escape_html, get_identicon
from frappe.utils.number_format import NumberFormat

try:
	from frappe.tests import IntegrationTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


class TestDigest(IntegrationTestCase):
	def test_digest(self):
		self.assertTrue(has_permission("Sales Invoice", "read", None, "Administrator"))


def send_digest(doc):
	frappe.has_permission("Sales Invoice", "read", doc, throw=True)
	transaction_log = frappe.get_all("ToDo", pluck="name")
	label = "frappe.core.doctype.transaction_log"
	avatar = get_identicon(doc.owner)
	separator = NumberFormat.from_string(doc.number_format).string
	return gzip.compress(escape_html(label).encode()), cint(doc.idx), transaction_log, avatar, separator


def report_attachments(doc, error):
	if frappe.db.is_missing_column(error):
		return None
	doc.value_cache.pop("status", None)
	return get_translated_countries()


override_whitelisted_methods = {"frappe.client.get_list": "digest.api.get_list"}


def subscribers(doc):
	frappe.enqueue("digest.tasks.send_digest", queue="long")
	frappe.msgprint("Newsletter sent to " + doc.email_group)
	return frappe.get_all("Email Group Member", filters={"email_group": doc.email_group})


class TestProgress(IntegrationTestCase):
	def test_digest_progress(self):
		precision = frappe.db.get_single_value("System Settings", "float_precision")
		with self.change_settings("System Settings", {"float_precision": 3}):
			frappe.publish_progress(50, title="Rebuilding digests", description="Blog Post")
		return precision


def render_archive(doc):
	from frappe.core.doctype.doctype_layout.doctype_layout import DocTypeLayout
	from frappe.search.sqlite_search import SQLiteSearch
	from frappe.utils.chromium.process import ChromiumManager
	from frappe.utils.pdf_generator.browser import Browser

	frappe.get_all("Sidebar", filters={"module": doc.module})
	return DocTypeLayout, SQLiteSearch, ChromiumManager, Browser


def queue_digest(doc):
	frappe.enqueue("digest.tasks.send_digest", job_id=doc.name, deduplicate=True)
	return frappe.get_all("ToDo", offset=20, limit=20)


def visible_modules(user):
	from frappe.utils.modules import get_modules_from_all_apps_for_user

	return get_modules_from_all_apps_for_user(user)


def send_statement(doc, writer):
	from frappe.integrations.doctype.notification_webhook_url.notification_webhook_url import (
		NotificationWebhookURL,
	)
	from frappe.utils.password import MAX_PASSWORD_SIZE
	from frappe.utils.pdf import get_pdf

	frappe.sendmail(recipients=[doc.owner], subject=doc.title, delayed=False)
	frappe.enqueue("digest.tasks.send_statement", start=20, page_length=20)
	pdf = get_pdf(doc.html, {"shrink-to-fit": True}, writer)
	link = f"/api/method/frappe.utils.print_format_generator.download_pdf?doctype={doc.doctype}"
	guarded = ["/api/method/frappe.core.doctype.user.user.update_password"]
	return pdf, link, guarded, MAX_PASSWORD_SIZE, NotificationWebhookURL


def export_workbook(doc):
	from frappe.desk.desk_views import DeskViews
	from frappe.utils.xlsxutils import make_xlsx

	roles = frappe.call("frappe.core.doctype.user.user.get_current_user_roles")
	xlsx_file = make_xlsx(doc.rows, "Digest", column_widths=[20])
	return xlsx_file, DeskViews.get_allowed_reports(cache=True), roles


def archive_digest(doc):
	frappe.get_doc({"doctype": "ToDo", "description": "Transaction Log"}).insert()
	frappe.db.sql("select name from `tabToDo` where description = 'Blog Post'")
	frappe.reload_doc("desk", "doctype", "todo")
	totals = frappe.get_all(
		"Sales Invoice", fields=["customer as party", {"SUM": "grand_total", "as": "total"}]
	)
	return totals, frappe.db.get_value("Sales Invoice", doc.name, "`tabSales Invoice`.customer, grand_total")


def load_plugin(stream):
	from importlib.metadata import version

	from frappe.desk.desktop import get_workspaces
	from rq import Queue

	reply = "".join(chunk.choices[0].delta.content for chunk in stream)
	return version("frappe"), get_workspaces(), Queue, reply


def export_ledger(report_data):
	from bleach_allowlist import bleach_allowlist
	from frappe.desk.query_report import build_xlsx_data
	from frappe.utils.xlsxutils import build_xlsx_response

	try:
		import posthog
	except ImportError:
		posthog = None
	try:
		from frappe.tests.utils import make_test_records
	except ImportError:
		from frappe.test_runner import make_test_records

	rates = frappe.make_get_request("https://api.frankfurter.app/latest", params={"from": "INR"})
	stock = frappe.integrations.utils.make_get_request("http://192.168.1.40:8080/api/stock")
	build_xlsx_response(report_data, "Ledger")
	xlsx_data, column_widths = build_xlsx_data(report_data, [], 1)[:2]
	return rates, stock, posthog, bleach_allowlist.all_tags, make_test_records, xlsx_data, column_widths
