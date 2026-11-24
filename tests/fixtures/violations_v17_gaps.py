from frappe.utils.nestedset import NestedSet


class Territory(NestedSet):
	def after_insert(self):
		super().after_insert()
