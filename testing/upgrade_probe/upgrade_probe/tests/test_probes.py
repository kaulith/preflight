"""A test per probe, so "did the upgrade break it" is a test result and not an opinion."""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from upgrade_probe import probes


class TestProbes(FrappeTestCase):
	def setUp(self):
		self.todo = frappe.get_doc(
			doctype="ToDo", description="Check the digest before the upgrade", priority="Medium"
		).insert()

	def test_compress_digest(self):
		self.assertEqual(len(probes.compress_digest("Check the digest")) > 0, True)

	def test_owner_avatar(self):
		self.assertIn("gravatar.com", probes.owner_avatar("Administrator"))

	@change_settings("System Settings", {"number_format": "#,###.##"})
	def test_number_separators(self):
		self.assertEqual(probes.number_separators()[0], ",")

	def test_blog_titles(self):
		self.assertEqual(probes.blog_titles(), [])

	def test_blog_list(self):
		self.assertEqual(probes.blog_list(), [])

	def test_energy_points(self):
		self.assertEqual(probes.energy_points("Administrator"), 0)

	def test_seed_todo_records(self):
		self.assertTrue(probes.seed_todo_records())

	def test_offsite_backup_enabled(self):
		self.assertFalse(probes.offsite_backup_enabled())

	def test_cached_status(self):
		self.assertEqual(probes.cached_status(self.todo.name), "Open")

	def test_oldest_todo(self):
		self.assertEqual(probes.oldest_todo().name, self.todo.name)

	def test_transaction_log_rows(self):
		self.assertEqual(probes.transaction_log_rows(), [])

	def test_override_is_used(self):
		self.assertEqual(frappe.get_doc("ToDo", self.todo.name).probe_label(), f"ToDo {self.todo.name}")

	def test_owner_keeps_permission(self):
		self.assertTrue(frappe.has_permission("ToDo", doc=self.todo.name, user="Administrator"))
