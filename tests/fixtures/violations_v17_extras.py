import frappe
from frappe.utils import html_utils
from frappe.utils.html_utils import acceptable_elements

acceptable_elements.add("marquee")
html_utils.svg_attributes.discard("onload")
frappe.get_doc("Letter Head", "Company Letterhead - Grey")
