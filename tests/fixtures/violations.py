import frappe
import frappe.core.doctype.transaction_log.transaction_log
import frappe.test_runner
from frappe.email.doctype.email_queue.email_queue import send_mail
from frappe.email.doctype.newsletter import newsletter as newsletter_controller
from frappe.geo.country_info import get_translated_dict
from frappe.integrations.doctype.google_drive.google_drive import take_backup
from frappe.permissions import has_permission
from frappe.social.doctype.energy_point_log import energy_point_log
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_gravatar, gzip_compress, make_esc
from frappe.utils.data import get_number_format_info
from frappe.utils.print_format import read_multi_pdf
from frappe.website.doctype.blog_post.blog_post import get_blog_list


class TestDigest(FrappeTestCase):
	def test_digest(self):
		frappe.get_test_records("Blog Post")
		frappe.test_runner.make_test_records("Blog Post")


def send_digest(doc):
	newsletter_controller.send_newsletter(doc.name)
	frappe.permissions.has_permission("Sales Invoice", "read", doc, frappe.session.user, False)
	has_permission("Sales Invoice", raise_exception=False)
	escape = frappe.utils.make_esc("$")
	body = frappe.utils.sanitize_html(doc.description)
	avatar = get_gravatar(doc.owner)
	separator = get_number_format_info(doc.number_format)
	frappe.db.value_cache.pop(("Sales Invoice", doc.name, "status"), None)
	return gzip_compress(escape(body).encode()), avatar, separator, make_esc


def report_attachments(doc, error):
	if frappe.db.is_column_missing(error):
		return None
	take_backup()
	send_mail(doc.queue_name)
	return read_multi_pdf(doc.output), get_blog_list(), get_translated_dict(), energy_point_log


override_whitelisted_methods = {"frappe.client.get_js": "digest.api.get_js"}


def cleanup(doc):
	frappe.delete_doc("Newsletter", doc.newsletter)
	frappe.db.exists("Blog Post", doc.blog_post)
	frappe.get_all("Energy Point Log", filters={"user": doc.owner})
	frappe.db.get_value("Dropbox Settings", None, "enabled")
	frappe.get_doc("Transaction Log", doc.transaction_log)


def queue_backup(doc):
	frappe.enqueue("frappe.integrations.doctype.s3_backup_settings.s3_backup_settings.take_backup")
	return frappe.get_attr("frappe.utils.gzip_decompress")(doc.payload)


class TestProgress(FrappeTestCase):
	def test_digest_progress(self):
		precision = frappe.tests.get_system_setting("float_precision")
		with frappe.tests.utils.change_settings("System Settings", {"float_precision": 3}):
			frappe.desk.doctype.bulk_update.bulk_update.show_progress(
				self.blog_posts, "Rebuilding digests", 1, "Blog Post"
			)
		return precision


def render_archive(doc):
	from frappe.custom.doctype.doctype_layout.doctype_layout import DocTypeLayout
	from frappe.desk.page.setup_wizard.install_fixtures import _
	from frappe.search.website_search import WebsiteSearch
	from frappe.tests import update_system_settings
	from frappe.utils.pdf_generator.chrome_pdf_generator import ChromePDFGenerator
	from frappe.utils.weasyprint import get_html

	frappe.get_all("Sidebar Item Group", filters={"parent": doc.sidebar})
	return DocTypeLayout, WebsiteSearch, ChromePDFGenerator, get_html, update_system_settings, _


def queue_digest(doc):
	frappe.enqueue("digest.tasks.send_digest", job_name=doc.name)
	return frappe.get_all("ToDo", limit_start=20, limit_page_length=20)


def visible_modules(user):
	from frappe.config import get_modules_from_all_apps_for_user

	return get_modules_from_all_apps_for_user(user)


def send_statement(doc, writer):
	from frappe.auth import MAX_PASSWORD_SIZE
	from frappe.integrations.doctype.slack_webhook_url.slack_webhook_url import send_slack_message
	from frappe.utils.pdf import get_file_data_from_writer, get_pdf

	frappe.sendmail(recipients=[doc.owner], subject=doc.title, retry=3)
	pdf = get_pdf(doc.html, smart_shrinking=True)
	link = f"/api/method/frappe.utils.weasyprint.download_pdf?doctype={doc.doctype}&name={doc.name}"
	rows = frappe.get_list("ToDo", start=20, page_length=20)
	guarded = ["/api/method/frappe.core.doctype.user.user.verify_password"]
	return get_file_data_from_writer(writer), pdf, link, rows, guarded, MAX_PASSWORD_SIZE, send_slack_message


def export_workbook(doc, wb):
	from frappe.boot import get_allowed_reports
	from frappe.desk.doctype.changelog_feed.changelog_feed import get_feed
	from frappe.utils.xlsxutils import get_excel_date_format, make_xlsx

	frappe.get_all("Changelog Feed", pluck="title")
	roles = frappe.call("frappe.core.doctype.user.user.get_roles", uid=doc.owner)
	make_xlsx(doc.rows, "Digest", wb=wb)
	return get_allowed_reports(), get_feed, get_excel_date_format(), roles


def archive_digest(doc):
	frappe.get_doc({"doctype": "Transaction Log", "data": doc.data}).insert()
	frappe.get_all(doctype="Blog Post", pluck="name")
	frappe.db.set_single_value("Energy Point Settings", "enabled", 0)
	frappe.db.sql("delete from `tabNewsletter` where name = %s", doc.newsletter)
	frappe.reload_doc("integrations", "doctype", "dropbox_settings")
	return frappe.get_all("Sales Invoice", fields=["customer", "sum(grand_total) as total"])


def load_plugin(doc, path):
	import imp
	from distutils.version import LooseVersion

	import pkg_resources
	from frappe.core.doctype.user.user import get_roles
	from frappe.desk.desktop import get_workspace_sidebar_items
	from rq import Connection

	plugin = imp.load_source(doc.name, path)
	return plugin, LooseVersion, pkg_resources, get_roles, get_workspace_sidebar_items, Connection


def export_statement(report_data, item_code):
	import bleach
	import boto3
	import cairocffi
	import posthog
	from dropbox import Dropbox
	from frappe.desk.query_report import build_xlsx_data
	from frappe.test_runner import run_tests_for_doctype
	from geolite2 import geolite2

	xlsx_data, column_widths = build_xlsx_data(report_data, [], 1, ignore_visible_idx=True)
	filter_rows, _ = build_xlsx_data(report_data, [], 0, include_filters=True)
	stock = frappe.make_get_request("http://192.168.1.40:8080/api/stock", params={"item_code": item_code})
	clients = bleach, boto3, cairocffi, posthog, Dropbox, geolite2, run_tests_for_doctype
	return xlsx_data, column_widths, filter_rows, stock, clients


def archive_attachment(file_url, ip_address):
	import maxminddb
	from botocore.exceptions import ClientError
	from s3transfer.manager import TransferManager

	with maxminddb.open_database("/usr/share/GeoIP/GeoLite2-Country.mmdb") as reader:
		country = reader.get(ip_address)
	return file_url, country, ClientError, TransferManager
