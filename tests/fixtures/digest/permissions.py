def sales_invoice_has_permission(doc, ptype, user):
	"""Lets the owner through and says nothing about anyone else, which is the v15 contract."""
	if doc.owner == user:
		return True


def purchase_invoice_has_permission(doc, ptype, user):
	"""Answers on every path, which is what v16 requires."""
	return doc.owner == user
