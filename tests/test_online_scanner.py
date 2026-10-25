import io
import json
import subprocess
import urllib.error
import urllib.request

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from preflight.models import Report
from preflight.online_scanner import OnlineScanner, final_releases, newest_release, scan_online
from preflight.rule_loader import load_rules

scanner = OnlineScanner(load_rules("v16"))
WHEEL_314 = "rapidfuzz-3.14.1-cp314-cp314-manylinux_2_17_x86_64.whl"
WHEEL_313 = "rapidfuzz-3.12.2-cp313-cp313-manylinux_2_17_x86_64.whl"
UPSTREAM = "https://github.com/frappe/erpnext.git\n"


@pytest.fixture
def report():
	return Report(site="digest.localhost", target="v16", apps=[])


def answer(monkeypatch, **answers: subprocess.CompletedProcess) -> list[tuple[str, ...]]:
	"""Answer `node`, or git's `config` and `ls-remote`, and keep each command that ran."""
	commands = []

	def run(command, **kwargs):
		commands.append(command)
		given = answers[command[0] if command[0] == "node" else command[3]]
		return subprocess.CompletedProcess(command, given.returncode, given.stdout, given.stderr)

	monkeypatch.setattr(subprocess, "run", run)
	return commands


def printed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
	return subprocess.CompletedProcess((), returncode, stdout, stderr)


def app_on(tmp_path, branch: str):
	root = tmp_path / "erpnext"
	(root / ".git").mkdir(parents=True)
	(root / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
	return {"erpnext": root}


def app_requiring(tmp_path, *dependencies: str):
	root = tmp_path / "digest"
	root.mkdir()
	listed = "".join(f'    "{dependency}",\n' for dependency in dependencies)
	(root / "pyproject.toml").write_text(f"[project]\ndependencies = [\n{listed}]\n")
	return {"digest": root}


def pypi(monkeypatch, releases: dict[str, list[str]], requires_python: str | None = None):
	"""PyPI answering every project with `releases`, each version listing its file names."""
	project = {
		"releases": {
			version: [{"filename": name, "requires_python": requires_python} for name in files]
			for version, files in releases.items()
		}
	}
	monkeypatch.setattr(
		urllib.request, "urlopen", lambda url, timeout: io.BytesIO(json.dumps(project).encode())
	)


def test_node_older_than_the_target_needs_is_reported(monkeypatch, report):
	answer(monkeypatch, node=printed("v20.11.1\n"))
	scanner.scan_node(report)
	assert [
		(finding.rule.id, finding.file, finding.line, finding.snippet, finding.source)
		for finding in report.findings
	] == [("v16-bench-node", "node", None, "node v20.11.1", "bench")]


def test_node_the_target_takes_is_not_reported(monkeypatch, report):
	answer(monkeypatch, node=printed("v24.15.0\n"))
	scanner.scan_node(report)
	assert report.findings == []


def test_node_missing_from_the_path_is_listed_as_not_checked(monkeypatch, report):
	def missing(command, **kwargs):
		raise FileNotFoundError(2, "No such file or directory", "node")

	monkeypatch.setattr(subprocess, "run", missing)
	scanner.scan_node(report)
	assert report.not_checked == [
		"node: [Errno 2] No such file or directory: 'node', the node version not checked"
	]


def test_app_whose_remote_has_no_target_branch_is_reported(monkeypatch, report, tmp_path):
	answer(monkeypatch, config=printed(UPSTREAM), **{"ls-remote": printed(returncode=2)})
	scanner.scan_target_branches(report, app_on(tmp_path, "version-15-hotfix"), 15)
	assert [(finding.app, finding.file, finding.snippet) for finding in report.findings] == [
		(
			"erpnext",
			"upstream/version-16",
			"erpnext is on version-15-hotfix; upstream has no branch version-16",
		)
	]


def test_app_whose_remote_has_the_target_branch_is_not_reported(monkeypatch, report, tmp_path):
	answer(
		monkeypatch,
		config=printed(UPSTREAM),
		**{"ls-remote": printed("4f51c84\trefs/heads/version-16\n")},
	)
	scanner.scan_target_branches(report, app_on(tmp_path, "version-15-hotfix"), 15)
	assert report.findings == []


def test_remote_that_cannot_be_read_is_listed_as_not_checked_for_the_app(monkeypatch, report, tmp_path):
	failed = printed(returncode=128, stderr="remote: Repository not found.\nfatal: Authentication failed\n")
	answer(monkeypatch, config=printed(UPSTREAM), **{"ls-remote": failed})
	scanner.scan_target_branches(report, app_on(tmp_path, "version-15-hotfix"), 15)
	assert report.not_checked == [
		"erpnext: git ls-remote failed, fatal: Authentication failed; whether upstream has version-16 not checked"
	]


def test_app_with_no_upstream_remote_is_reported(monkeypatch, report, tmp_path):
	answer(monkeypatch, config=printed(returncode=1))
	scanner.scan_target_branches(report, app_on(tmp_path, "version-15-hotfix"), 15)
	assert [(finding.app, finding.file, finding.snippet) for finding in report.findings] == [
		(
			"erpnext",
			"upstream/version-16",
			"erpnext is on version-15-hotfix; it has no upstream remote, so bench switch-to-branch cannot switch it",
		)
	]


def test_app_on_its_own_branch_is_not_asked_about(monkeypatch, report, tmp_path):
	commands = answer(monkeypatch)
	scanner.scan_target_branches(report, app_on(tmp_path, "main"), 15)
	assert commands == []


def test_with_no_bench_neither_node_nor_git_runs(monkeypatch, report, tmp_path):
	commands = answer(monkeypatch)
	scan_online(report, scanner, app_on(tmp_path, "version-15-hotfix"), None)
	assert commands == []


def test_dependency_with_wheels_for_older_pythons_only_is_reported(monkeypatch, report, tmp_path):
	pypi(
		monkeypatch,
		{"3.12.2": [WHEEL_313, "rapidfuzz-3.12.2-cp312-cp312-win_amd64.whl", "rapidfuzz-3.12.2.tar.gz"]},
	)
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "rapidfuzz~=3.12.2"), None)
	assert [(finding.app, finding.file, finding.line, finding.snippet) for finding in report.findings] == [
		(
			"digest",
			"pyproject.toml",
			3,
			"rapidfuzz~=3.12.2: rapidfuzz 3.12.2 has cp312, cp313 wheels, none for Python 3.14",
		)
	]


@pytest.mark.parametrize(
	"wheel",
	[
		"rapidfuzz-3.12.2-cp314-cp314-manylinux_2_17_x86_64.whl",
		"rapidfuzz-3.12.2-cp38-abi3-manylinux_2_17_x86_64.whl",
		"rapidfuzz-3.12.2-py3-none-any.whl",
	],
)
def test_dependency_with_a_wheel_the_target_python_takes_is_not_reported(
	monkeypatch, report, tmp_path, wheel
):
	pypi(monkeypatch, {"3.12.2": [WHEEL_313, wheel]})
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "rapidfuzz~=3.12.2"), None)
	assert report.findings == []


def test_dependency_with_no_wheels_is_not_reported(monkeypatch, report, tmp_path):
	pypi(monkeypatch, {"0.5.0": ["barcodenumber-0.5.0.tar.gz"]})
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "barcodenumber~=0.5.0"), None)
	assert report.findings == []


def test_dependency_with_no_release_for_the_target_python_is_reported(monkeypatch, report, tmp_path):
	pypi(monkeypatch, {"1.3.8": ["Unidecode-1.3.8-py3-none-any.whl"]}, requires_python=">=3.5,<3.14")
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "Unidecode~=1.3.6"), None)
	assert [finding.snippet for finding in report.findings] == [
		(
			"Unidecode~=1.3.6: pip finds no release for Python 3.14; the newest, Unidecode 1.3.8, requires"
			" Python >=3.5,<3.14"
		)
	]


def test_dependency_whose_marker_leaves_out_the_target_python_is_not_reported(monkeypatch, report, tmp_path):
	pypi(monkeypatch, {"3.12.2": [WHEEL_313]})
	roots = app_requiring(tmp_path, "rapidfuzz~=3.12.2; python_version < '3.14'")
	scanner.scan_dependency_wheels(report, roots, None)
	assert report.findings == []


def test_pypi_out_of_reach_is_one_not_checked_line(monkeypatch, report, tmp_path):
	def unreachable(url, timeout):
		raise urllib.error.URLError("timed out")

	monkeypatch.setattr(urllib.request, "urlopen", unreachable)
	scanner.scan_dependency_wheels(
		report, app_requiring(tmp_path, "rapidfuzz~=3.12.2", "Unidecode~=1.3.6"), None
	)
	assert report.not_checked == ["pypi.org: <urlopen error timed out>, dependency wheels not checked"]


def test_dependency_missing_from_pypi_is_listed_as_not_checked(monkeypatch, report, tmp_path):
	def not_found(url, timeout):
		raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

	monkeypatch.setattr(urllib.request, "urlopen", not_found)
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "digest-sync"), None)
	assert report.not_checked == [
		"digest/pyproject.toml: digest-sync is not on pypi.org, its wheels not checked"
	]


def test_app_on_the_bench_frappe_version_branch_is_not_looked_up(monkeypatch, report, tmp_path):
	roots = app_on(tmp_path, "version-15-hotfix")
	(roots["erpnext"] / "pyproject.toml").write_text('[project]\ndependencies = ["rapidfuzz~=3.12.2"]\n')
	pypi(monkeypatch, {"3.12.2": [WHEEL_313]})
	scanner.scan_dependency_wheels(report, roots, 15)
	assert report.findings == []


def test_app_on_no_branch_is_listed_as_not_checked(report, tmp_path):
	scanner.scan_dependency_wheels(report, app_requiring(tmp_path, "rapidfuzz~=3.12.2"), 15)
	assert report.not_checked == [
		"pyproject.toml of digest: not a git checkout, dependency wheels not checked"
	]


def test_final_releases_leave_out_yanked_files_and_prereleases():
	releases = {
		"3.12.2": [{"filename": WHEEL_313}],
		"3.14.1": [{"filename": WHEEL_314, "yanked": True}],
		"3.15.0rc1": [{"filename": "rapidfuzz-3.15.0rc1-cp314-cp314-manylinux_2_17_x86_64.whl"}],
	}
	assert list(final_releases(releases, SpecifierSet(">=3.12"))) == [Version("3.12.2")]


def test_newest_release_skips_one_whose_requires_python_leaves_out_the_target():
	releases = {
		Version("3.12.2"): [{"filename": WHEEL_313, "requires_python": ">=3.9"}],
		Version("3.14.1"): [{"filename": WHEEL_314, "requires_python": ">=3.15"}],
	}
	assert newest_release(releases, Version("3.14.0"))[0] == Version("3.12.2")
