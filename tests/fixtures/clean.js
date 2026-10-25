// frappe.views.ListSidebar and frappe.energy_points went away in v16
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		frm.sidebar = new frappe.ui.Sidebar({ wrapper: frm.page.sidebar });
		frappe.call({
			method: "frappe.client.get_list",
			args: { doctype: "Sales Invoice", filters: { status: "Overdue" } },
		});
		frappe.require("/assets/digest/js/digest.js");
		frm.set_value("subject", __("Newsletter for {0}", [frm.doc.customer]));
	},
});

frappe.pages["digest"].on_page_load = function (wrapper) {
	const pages = frappe.boot.workspaces.pages;
	$(wrapper).append(`${frappe.utils.icon("megaphone", "sm")} ${pages.length}`);
};

frappe.listview_settings["Email Group"] = {
	onload(listview) {
		/*
		frappe.energy_points.get_points(listview.data.length);
		*/
		listview.page.add_inner_button(__("Add Subscribers"), () => {
			frappe.call({ method: "frappe.email.doctype.email_group.email_group.add_subscribers" });
		}); // the sidebar was frappe.views.ListSidebar
	},
};

const comments = createListResource({
	doctype: "Comment",
	filters: { reference_doctype: "Newsletter" },
	orderBy: "`tabComment`.creation desc",
});
