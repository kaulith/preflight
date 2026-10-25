app_name = "digest"
app_title = "Digest"

leaderboards = "digest.startup.leaderboard.get_leaderboards"

has_permission = {
	"Sales Invoice": "digest.permissions.sales_invoice_has_permission",
	"Sales Order": "erpnext.selling.permissions.sales_order_has_permission",
}

override_doctype_class = {"Web Page": "digest.overrides.web_page.DigestWebPage"}

required_apps = ["frappe/payments"]

get_changelog_feed = "digest.changelog.get_feed"

doctype_js = {"Newsletter": "public/js/newsletter.js"}

scheduler_events = {"daily": ["frappe.email.doctype.newsletter.newsletter.send_scheduled_email"]}
