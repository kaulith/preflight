from digest.overrides.web_page import ReviewedWebPage
from frappe.website.doctype.web_page.web_page import WebPage as BasePage

from .web_page import ReviewedWebPage as LocalReviewed


class AliasedWebPage(BasePage):
	"""Inherits the controller under an alias, which the resolver reads off the import."""


class ChainedWebPage(ReviewedWebPage):
	"""Inherits the controller one class removed, which the resolver follows."""


class RelativeWebPage(LocalReviewed):
	"""Inherits the controller through a relative import, resolved against this file."""
