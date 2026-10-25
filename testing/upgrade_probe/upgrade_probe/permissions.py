def todo_has_permission(doc, ptype, user):
	"""Lets the owner through and says nothing about anyone else, which is the v15 contract."""
	if doc.owner == user:
		return True
