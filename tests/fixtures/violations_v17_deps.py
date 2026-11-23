import pdfkit
import psycopg2
from erpnext.projects.doctype.task.task import make_timesheet
from frappe.database.mariadb.mysqlclient import MariaDBDatabase
from frappe.desk.doctype.event.event import delete_communication
from frappe.desk.page.setup_wizard.install_fixtures import add_unsubscribe
from frappe.desk.query_report import build_xlsx_data
from frappe.utils.error import get_default_args, raise_error_on_no_output
from frappe.utils.safe_exec import RENDER_EXEC_CONFIG_KEY, is_render_exec_enabled

build_xlsx_data(report_data, [0, 1], 1)
build_xlsx_data(report_data, visible_idx=[0, 1])
build_xlsx_data(report_data, ignore_visible_idx=True)
make_timesheet("TASK-2026-00001", ignore_permissions=True)
make_timesheet("TASK-2026-00001", None, True)
# ruff: noqa: F401, F821
