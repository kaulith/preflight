import os

import pytest


@pytest.fixture(scope="session")
def site():
	"""The site named by PREFLIGHT_SITE, connected. Skips when there is none."""
	name = os.environ.get("PREFLIGHT_SITE")
	if not name:
		pytest.skip("needs a site: run from the bench directory with PREFLIGHT_SITE set")

	frappe = pytest.importorskip("frappe")
	frappe.init(site=name)
	frappe.connect()
	yield name
	frappe.destroy()


@pytest.fixture
def require_doctypes(site):
	"""Skip when the site no longer has a doctype a seed needs, which is how a site past the upgrade reads."""
	frappe = pytest.importorskip("frappe")

	def require(*doctypes: str):
		missing = [name for name in doctypes if not frappe.db.exists("DocType", name)]
		if missing:
			pytest.skip(f"{site} no longer has {', '.join(missing)}")

	return require
