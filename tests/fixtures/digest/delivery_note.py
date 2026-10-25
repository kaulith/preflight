def delivery_note_has_permission(doc, ptype, user):
	"""Lets the owner through and says nothing about anyone else, two imports away from the hook."""
	if doc.owner == user:
		return True
