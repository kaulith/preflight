frappe.ui.form.on("POS Closing Entry", {
	async pos_profile(frm) {
		const { message } = await frappe.db.get_value("POS Profile", frm.doc.pos_profile, "disable_grand_total_to_default_mop");
		frm.set_value("remarks", message.disable_grand_total_to_default_mop);
	},
});

frappe.ui.form.on("Purchase Order", {
	async cost_center(frm) {
		const budgets = await frappe.db.get_list("Budget", {
			fields: ["name", "budget_against"],
			filters: { cost_center: frm.doc.cost_center, fiscal_year: frm.doc.fiscal_year },
		});
		frm.set_intro(budgets.length);
	},
});

frappe.ui.form.on("Payment Entry", {
	async party(frm) {
		const { message } = await frappe.call({
			method: "erpnext.accounts.doctype.payment_entry.payment_entry.get_party_and_account_balance",
			args: { company: frm.doc.company, date: frm.doc.posting_date, ptype: frm.doc.party_type, pty: frm.doc.party },
		});
		frm.set_value("remarks", message.party_balance);
	},
});

frappe.ui.form.on("Supplier", {
	add_bank_account(frm) {
		frappe.call({
			method: "erpnext.accounts.doctype.bank_account.bank_account.make_bank_account",
			args: { doctype: frm.doc.doctype, docname: frm.doc.name },
			callback: (r) => frappe.set_route("Form", "Bank Account", frappe.model.sync(r.message)[0].name),
		});
	},
});

frappe.ui.form.on("Customer", {
	add_pricing_rule(frm) {
		erpnext.utils.make_pricing_rule(frm.doc.doctype, frm.doc.name);
	},
});

frappe.ui.form.on("Material Request", {
	setup(frm) {
		frm.set_query("preferred_supplier", () => ({
			query: "erpnext.stock.doctype.material_request.material_request.get_default_supplier_query",
			filters: { doc: frm.doc.name },
		}));
	},
});
