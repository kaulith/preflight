from pathlib import Path

import pytest

from preflight.compatibility_scanner import (
	CompatibilityScanner,
	checked_out_branch,
	declared_dependencies,
	is_frappe_branch,
	parse_required_app_name,
	toml_line,
)
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"
PYPROJECT = (FIXTURES / "pyproject_violations.toml").read_text()

scanner = CompatibilityScanner(load_rules("v16"))


def test_bench_on_a_python_the_target_cannot_install_on_is_reported():
	assert [finding.snippet for finding in scanner.scan_environment("3.11.9")] == ["Python 3.11.9"]
	assert scanner.scan_environment("3.14.3") == []


def test_pins_that_leave_out_the_target_are_reported_on_their_lines():
	findings = scanner.scan_pyproject(PYPROJECT, "pyproject.toml")
	assert {finding.rule.id: finding.line for finding in findings} == {
		"v16-app-requires-python": 3,
		"v16-app-dependency-pins": 5,
		"v16-app-frappe-bound": 9,
	}


def test_dependency_pin_finding_names_the_pin_frappe_holds():
	findings = scanner.scan_pyproject(PYPROJECT, "pyproject.toml")
	assert "pytz==2024.1 (frappe pins pytz==2025.2)" in [finding.snippet for finding in findings]


def test_pins_that_take_in_the_target_are_not_reported():
	source = (
		'[project]\nrequires-python = ">=3.14.2"\ndependencies = ["babel>2.18.0", "PyPika>=0.48"]\n\n'
		'[tool.bench.frappe-dependencies]\nfrappe = ">=15.0.0,<17.0.0"\n'
	)
	assert scanner.scan_pyproject(source, "pyproject.toml") == []


@pytest.mark.parametrize("branch", ["version-15-hotfix", "mergify/bp/version-15-hotfix/pr-1"])
def test_the_bench_frappe_version_branch_and_one_cut_from_it_are_frappe_branches(branch):
	assert is_frappe_branch(branch, 15)


def test_an_app_own_version_branch_is_not_a_frappe_branch():
	assert not is_frappe_branch("version-3", 15)


def test_a_worktree_is_on_the_branch_its_git_dir_holds(tmp_path):
	git_dir = tmp_path / "digest-main" / ".git" / "worktrees" / "digest"
	git_dir.mkdir(parents=True)
	(git_dir / "HEAD").write_text("ref: refs/heads/develop\n", encoding="utf-8")
	(tmp_path / "digest").mkdir()
	(tmp_path / "digest" / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
	assert checked_out_branch(tmp_path / "digest") == "develop"


def test_a_detached_head_is_on_no_branch(tmp_path):
	(tmp_path / ".git").mkdir()
	(tmp_path / ".git" / "HEAD").write_text("c4e97234b4a9556dbebe7db76cbcfd48bfac8355\n", encoding="utf-8")
	assert checked_out_branch(tmp_path) is None


def test_an_app_without_a_git_checkout_is_on_no_branch(tmp_path):
	assert checked_out_branch(tmp_path) is None


def test_dependencies_are_read_from_pyproject_and_requirements_by_canonical_name(tmp_path):
	(tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["Bleach~=6.0"]\n', encoding="utf-8")
	(tmp_path / "requirements.txt").write_text("boto3==1.34.0  # backups\n-r dev.txt\n", encoding="utf-8")
	assert declared_dependencies(tmp_path) == {"bleach", "boto3"}


def test_toml_line_reads_the_key_in_its_own_table():
	lines = ["[tool.flit.module]", 'name = "digest"', "", "[project]", 'name = "digest"']
	assert toml_line(lines, "project", "name") == 5


@pytest.mark.parametrize(
	"requirement",
	[
		"erpnext",
		"frappe/erpnext",
		"frappe/erpnext@version-15",
		"https://github.com/frappe/erpnext.git",
		"https://github.com/frappe/erpnext.git#develop",
		"git@github.com:frappe/erpnext.git",
		"/home/frappe/frappe-bench/apps/erpnext/",
	],
)
def test_every_spelling_of_a_required_app_resolves_to_the_app(requirement):
	assert parse_required_app_name(requirement) == "erpnext"


def test_required_app_missing_from_the_bench_is_reported():
	source = 'required_apps = ["frappe/payments", "erpnext"]\n'
	findings = scanner.scan_required_apps(source, "digest/hooks.py", {"frappe", "erpnext"})
	assert [(finding.rule.id, finding.line) for finding in findings] == [("v16-app-required-apps", 1)]
