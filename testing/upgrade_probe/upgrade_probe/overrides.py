from frappe.model.document import Document


class ProbeToDo(Document):
	"""Replaces the ToDo controller without subclassing it, which v15 accepted.

	v16 refuses it with "must be a subclass of", and every read and write of ToDo fails with it,
	so a loop C run has to make this inherit ToDo before the rest of the suite can say anything.
	"""

	def probe_label(self):
		return f"{self.doctype} {self.name}"
