frappe.ui.form.on("POS Closing Entry", {
	async pos_profile(frm) {
		const { message } = await frappe.db.get_value("POS Profile", frm.doc.pos_profile, "set_grand_total_to_default_mop");
		const post_change = await frappe.db.get_single_value("POS Settings", "post_change_gl_entries");
		frm.set_value("remarks", `${message.set_grand_total_to_default_mop} ${post_change}`);
	},
});

frappe.ui.form.on("Purchase Order", {
	async cost_center(frm) {
		const budgets = await frappe.db.get_list("Budget", {
			fields: ["name", "account"],
			filters: { cost_center: frm.doc.cost_center, from_fiscal_year: frm.doc.fiscal_year },
		});
		frm.set_intro(budgets.length);
	},
});

frappe.ui.form.on("Payment Entry", {
	async party(frm) {
		const { message } = await frappe.call({
			method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_party_details",
			args: { company: frm.doc.company, party_type: frm.doc.party_type, party: frm.doc.party, date: frm.doc.posting_date },
		});
		frm.set_value("remarks", message.party_name);
	},
});

frappe.ui.form.on("Supplier", {
	add_bank_account(frm) {
		frappe.new_doc("Bank Account", { party_type: frm.doc.doctype, party: frm.doc.name });
	},
});

frappe.ui.form.on("Customer", {
	add_pricing_rule(frm) {
		frappe.new_doc("Pricing Rule", { applicable_for: "Customer", customer: frm.doc.name, selling: 1 });
	},
	add_bank_account(frm) {
		erpnext.utils.make_bank_account(frm.doc.doctype, frm.doc.name);
	},
});

frappe.ui.form.on("Material Request", {
	async preferred_supplier(frm) {
		const { message } = await frappe.call({
			method: "erpnext.stock.doctype.material_request.material_request.get_item_default_suppliers",
			args: { source_name: frm.doc.name },
		});
		frm.set_intro(message.length);
	},
});
