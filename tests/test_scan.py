from types import SimpleNamespace

import pytest

frappe = pytest.importorskip("frappe")

from preflight import scan
from preflight.compatibility_scanner import CompatibilityScanner
from preflight.models import Finding, Match, Report, Rule
from preflight.rule_loader import load_rules

RULES = load_rules("v16")
BLOG = next(rule for rule in RULES if rule.id == "v16-removed-blog-doctypes")
REPOST_TYPES = next(rule for rule in RULES if rule.id == "v16-erpnext-repost-allowed-types")
TARGET_BRANCH = Rule(
	id="v16-target-branch",
	title="No version-16 branch to switch to",
	severity="error",
	match=Match(type="target_branch", branch="version-16"),
	message="The app's remote has no version-16 branch.",
	replacement="Ask the app's maintainers for one.",
	references=(),
)
PATCHES = """[pre_model_sync]
digest.patches.v1_0.rename_digest_fields #2024-03-01
execute:frappe.db.set_value("Blog Settings", None, "show_cta_in_blog", 1)
finally:digest.patches.v1_0.reindex_digests
"""


def missing_dependency(app):
	raise ModuleNotFoundError("No module named 'requests_oauthlib'", name="requests_oauthlib")


def blog_finding(file: str, line: int) -> Finding:
	return Finding(rule=BLOG, file=file, line=line, snippet='frappe.get_doc("Blog Settings")', app="digest")


@pytest.fixture
def empty_site(monkeypatch):
	"""A site with no scripts, no customisations, no records a rule names and no patches run."""
	monkeypatch.setattr(scan, "site_scripts", list)
	monkeypatch.setattr(scan, "site_schema", list)
	monkeypatch.setattr(scan, "site_records", lambda rules: [])
	monkeypatch.setattr(frappe, "get_all", lambda doctype, **kwargs: [])


@pytest.fixture
def bench_app(tmp_path, monkeypatch):
	"""The checkout of `digest`, the one app on the bench besides frappe."""
	app_path = tmp_path / "digest" / "digest"
	app_path.mkdir(parents=True)
	(app_path / "__init__.py").touch()
	monkeypatch.setattr(frappe, "get_app_path", lambda app: str(app_path))
	monkeypatch.setattr(frappe, "get_all_apps", lambda with_internal_apps: ["frappe", "digest"])
	return app_path.parent


def on_branch(app_root, branch: str):
	(app_root / ".git").mkdir()
	(app_root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")


def test_an_app_whose_code_is_not_on_the_bench_has_no_path(monkeypatch):
	def missing(app):
		raise ModuleNotFoundError(f"No module named '{app}'", name=app)

	monkeypatch.setattr(frappe, "get_app_path", missing)
	assert scan.app_package_path("digest") is None


def test_an_app_that_imports_as_a_namespace_package_has_no_path(monkeypatch, tmp_path):
	monkeypatch.setattr(frappe, "get_app_path", lambda app: str(tmp_path))
	assert scan.app_package_path("digest") is None


def test_an_app_that_fails_to_import_is_named_as_unreadable_with_the_reason(monkeypatch, empty_site):
	monkeypatch.setattr(frappe, "get_app_path", missing_dependency)
	monkeypatch.setattr(frappe, "get_all_apps", lambda with_internal_apps: ["frappe", "digest"])
	report = scan.build_report(RULES, "test.localhost", "v16", ("digest",))
	assert report.unreadable_files == ["digest: ModuleNotFoundError: No module named 'requests_oauthlib'"]
	assert report.missing_apps == []


def test_an_app_on_the_bench_that_fails_to_import_is_named_as_not_checked(monkeypatch, empty_site):
	monkeypatch.setattr(frappe, "get_installed_apps", lambda: ["frappe"])
	monkeypatch.setattr(frappe, "get_all_apps", lambda with_internal_apps: ["frappe", "digest"])
	monkeypatch.setattr(frappe, "get_app_path", missing_dependency)
	report = scan.build_report(RULES, "test.localhost", "v16")
	assert report.not_checked == [
		(
			"digest: ModuleNotFoundError: No module named 'requests_oauthlib', its pyproject.toml and"
			" required_apps not checked"
		)
	]


def test_a_pyproject_that_does_not_parse_is_named_as_unparsable(bench_app):
	on_branch(bench_app, "main")
	(bench_app / "pyproject.toml").write_text("[project\n", encoding="utf-8")
	report = Report(site="test.localhost", target="v16", apps=["digest"])
	scan.scan_bench(report, CompatibilityScanner(RULES), {"digest": bench_app / "digest"}, 15)
	assert report.unparsable_files == ["digest/pyproject.toml"]


def test_a_pyproject_outside_a_git_checkout_is_named_as_not_checked(bench_app):
	(bench_app / "pyproject.toml").write_text('[project]\nname = "digest"\n', encoding="utf-8")
	report = Report(site="test.localhost", target="v16", apps=["digest"])
	scan.scan_bench(report, CompatibilityScanner(RULES), {"digest": bench_app / "digest"}, 15)
	assert report.not_checked == [
		"pyproject.toml of digest: not a git checkout, requires-python, frappe bound and dependency pins not checked"
	]


def test_findings_of_an_app_on_the_frappe_version_branch_are_upstream(bench_app):
	on_branch(bench_app, "version-15-hotfix")
	finding = blog_finding("digest/api.py", 3)
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	scan.move_upstream_findings(report, {"digest": bench_app / "digest"}, 15, ())
	assert (report.upstream_apps, report.upstream_findings, report.findings) == (
		{"digest": "version-15-hotfix"},
		[finding],
		[],
	)


def test_findings_of_an_app_with_no_branch_are_counted_and_said_to_be(bench_app):
	report = Report(
		site="test.localhost", target="v16", apps=["digest"], findings=[blog_finding("digest/api.py", 3)]
	)
	scan.move_upstream_findings(report, {"digest": bench_app / "digest"}, 15, ())
	(line,) = report.not_checked
	assert line.startswith("digest: no branch checked out")


def test_findings_of_an_app_named_with_app_stay_counted(bench_app):
	on_branch(bench_app, "version-15-hotfix")
	report = Report(
		site="test.localhost", target="v16", apps=["digest"], findings=[blog_finding("digest/api.py", 3)]
	)
	scan.move_upstream_findings(report, {"digest": bench_app / "digest"}, 15, ("digest",))
	assert report.upstream_apps == {}


def test_findings_of_an_app_with_no_target_branch_stay_counted(bench_app):
	on_branch(bench_app, "version-15-hotfix")
	stuck = Finding(rule=TARGET_BRANCH, file="digest", line=None, snippet="version-15-hotfix", app="digest")
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[stuck])
	scan.move_upstream_findings(report, {"digest": bench_app / "digest"}, 15, ())
	assert report.upstream_apps == {}


@pytest.fixture
def patch_log(monkeypatch, bench_app):
	"""digest's patches.txt, with the module patch and the finally patch logged and the execute line not."""
	(bench_app / "digest" / "patches.txt").write_text(PATCHES, encoding="utf-8")
	executed = ["digest.patches.v1_0.rename_digest_fields #2024-03-01", "digest.patches.v1_0.reindex_digests"]
	monkeypatch.setattr(frappe, "get_all", lambda doctype, filters, pluck: executed)
	return {"digest": bench_app / "digest"}


@pytest.mark.parametrize("module", ["rename_digest_fields", "reindex_digests"])
def test_a_finding_in_a_patch_the_site_ran_is_set_aside(patch_log, module):
	finding = blog_finding(f"digest/patches/v1_0/{module}.py", 3)
	report = Report(site="test.localhost", target="v16", apps=["digest"], findings=[finding])
	scan.move_ran_patch_findings(report, patch_log)
	assert (report.ran_patch_findings, report.findings) == ([finding], [])


def test_a_finding_in_a_patch_still_to_run_stops_migrate(patch_log):
	report = Report(
		site="test.localhost", target="v16", apps=["digest"], findings=[blog_finding("digest/patches.txt", 3)]
	)
	scan.move_ran_patch_findings(report, patch_log)
	assert [finding.stops_migrate for finding in report.findings] == [True]


def test_a_site_record_rule_does_not_query_a_table_without_its_filter_column(monkeypatch):
	columns = ["name", "document_type", "parent", "parentfield", "parenttype"]
	monkeypatch.setattr(frappe, "db", SimpleNamespace(get_db_table_columns=lambda table: columns))
	monkeypatch.setattr(frappe, "get_all", lambda doctype, **kwargs: pytest.fail(f"queried {doctype}"))
	assert scan.site_records([REPOST_TYPES]) == []
