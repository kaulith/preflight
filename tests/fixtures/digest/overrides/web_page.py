from frappe.model.document import Document
from frappe.website.doctype.web_page.web_page import WebPage


class DigestWebPage(Document):
	"""Replaces the controller without inheriting it, which is what v15 accepted."""

	def digest_title(self):
		return f"{self.title} ({self.route})"


class ReviewedWebPage(WebPage):
	"""Inherits the controller it replaces, which is what v16 requires."""

	def digest_title(self):
		return f"{self.title} ({self.route})"
