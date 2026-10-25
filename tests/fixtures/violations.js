frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		frm.sidebar = new frappe.views.ListSidebar({ doctype: frm.doctype });
		frm.review = new frappe.ui.form.Review({ frm: frm, parent: frm.sidebar });
		frm.dashboard.add_comment(frappe.energy_points.get_points(frm.doc.points));
		frappe.call({
			method: "frappe.client.get_js",
			args: { items: ["/assets/digest/js/digest.js"] },
		});
	},
});

frappe.pages["digest"].on_page_load = function (wrapper) {
	const feed = frappe.boot.changelog_feed || [];
	frappe.xcall("frappe.desk.desktop.get_workspace_sidebar_items").then((sidebar) => {
		$(wrapper).append(`<i class="octicon octicon-megaphone"></i> ${feed.length} ${sidebar.pages.length}`);
	});
};

frappe.listview_settings["Newsletter"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Subscribe"), () => {
			frappe.call({ method: "frappe.email.doctype.newsletter.newsletter.subscribe" });
		});
	},
};

const posts = createListResource({
	doctype: "Blog Post",
	orderBy: "`tabBlog Post`.published_on desc",
});
