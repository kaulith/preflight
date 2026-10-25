app_name = "digest"
app_title = "Digest"

add_to_apps_screen = [{"name": app_name, "title": app_title, "route": "/app/deliveries"}]

extend_doctype_class = {"Web Page": ["digest.overrides.web_page.DigestWebPage"]}

has_website_permission = {
	"Sales Invoice": "digest.permissions.sales_invoice_has_website_permission",
}

permission_query_conditions = {
	"Sales Invoice": "digest.permissions.sales_invoice_query_conditions",
}

has_permission = {
	"Purchase Invoice": "digest.permissions.purchase_invoice_has_permission",
}

app_include_js = ["digest.bundle.js", "/assets/digest/js/leaderboards.js"]

doctype_js = {"Email Group": "public/js/email_group.js"}

scheduler_events = {"daily": ["frappe.email.doctype.email_account.email_account.notify_unreplied"]}


def get_leaderboards():
	leaderboards = {"Customer": "digest.startup.leaderboard.customers"}
	return leaderboards


override_doctype_class = {"Web Page": "digest.overrides.web_page.ReviewedWebPage"}
