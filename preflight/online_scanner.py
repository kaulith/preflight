import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.tags import Tag, compatible_tags, cpython_tags
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
from packaging.version import InvalidVersion, Version

try:
	import tomllib
except ModuleNotFoundError:  # python 3.10, which frappe v15 still runs on
	import tomli as tomllib

from preflight.compatibility_scanner import (
	PYTHON_RELEASES,
	checked_out_branch,
	is_frappe_branch,
	quoted_line,
	toml_line,
)
from preflight.models import Finding, Report, Rule

TIMEOUT = 30
PYPI_PROJECT = "https://pypi.org/pypi/{}/json"


def run(*command: str) -> subprocess.CompletedProcess:
	"""In a session of its own with prompts off, so neither git nor ssh can stop the scan to ask for a
	password. Raises OSError when the program is missing and TimeoutExpired when it hangs."""
	return subprocess.run(
		command,
		check=False,
		capture_output=True,
		text=True,
		timeout=TIMEOUT,
		stdin=subprocess.DEVNULL,
		start_new_session=True,
		env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
	)


def missing_upstream_branch(app_root: Path, branch: str) -> str | None:
	"""Why bench switch-to-branch cannot read `branch` off the app's remote named upstream, which bench
	get-app names the remote it clones and the switch reads by that name, or None when it can. Raises
	CalledProcessError when git fails, OSError when it is missing and TimeoutExpired when it hangs."""
	upstream = run("git", "-C", str(app_root), "config", "--get", "remote.upstream.url")
	if upstream.returncode == 1:
		return "it has no upstream remote, so bench switch-to-branch cannot switch it"
	upstream.check_returncode()
	heads = run(
		"git", "-C", str(app_root), "ls-remote", "--exit-code", "--heads", "upstream", f"refs/heads/{branch}"
	)
	if heads.returncode == 2:
		return f"upstream has no branch {branch}"
	heads.check_returncode()
	return None


def pypi_releases(name: str) -> dict[str, list[dict]] | None:
	"""Each release of the project with its files, or None when PyPI has no such project. Raises OSError
	or ValueError when PyPI cannot be reached or answers with something other than its JSON."""
	try:
		with urllib.request.urlopen(PYPI_PROJECT.format(name), timeout=TIMEOUT) as response:
			return json.load(response)["releases"]
	except urllib.error.HTTPError as error:
		if error.code == 404:
			return None
		raise


def allows(requires_python: str | None, python: Version) -> bool:
	"""pip keeps a file whose Requires-Python does not parse, so it is read as allowing every Python."""
	try:
		return not requires_python or SpecifierSet(requires_python).contains(python)
	except InvalidSpecifier:
		return True


def final_releases(releases: dict[str, list[dict]], specifier: SpecifierSet) -> dict[Version, list[dict]]:
	"""Each final release `specifier` takes, with its files that are not yanked; pip passes over a release
	whose files are all yanked."""
	matching = {}
	for number, files in releases.items():
		try:
			version = Version(number)
		except InvalidVersion:
			continue
		files = [file for file in files if not file.get("yanked")]
		if files and not version.is_prerelease and specifier.contains(version):
			matching[version] = files
	return matching


def newest_release(releases: dict[Version, list[dict]], python: Version) -> tuple[Version, list[dict]] | None:
	"""The release pip picks on `python`, with the files it can pick from: the newest holding a file whose
	Requires-Python takes `python`."""
	candidates = {}
	for version, files in releases.items():
		if takes_python := [file for file in files if allows(file.get("requires_python"), python)]:
			candidates[version] = takes_python
	return max(candidates.items(), default=None)


def wheel_tags(files: list[dict]) -> set[Tag]:
	"""The tags of every wheel among `files`; an sdist is not a wheel and has none."""
	tags = set()
	for file in files:
		try:
			tags |= parse_wheel_filename(file["filename"])[3]
		except InvalidWheelFilename:
			continue
	return tags


class OnlineScanner:
	"""Rules that need the network or a program the bench runs: node's version, whether each app's remote
	holds the target branch, and whether PyPI has wheels of each dependency for the target's Python."""

	def __init__(self, rules: list[Rule]):
		self.rules_by_type: dict[str, list[Rule]] = {}
		for rule in rules:
			self.rules_by_type.setdefault(rule.match.type, []).append(rule)

	def scan_node(self, report: Report):
		rules = self.rules_by_type.get("bench_node", ())
		if not rules:
			return
		try:
			printed = run("node", "--version").stdout.strip()
			version = Version(printed.removeprefix("v"))
		except (OSError, subprocess.SubprocessError, InvalidVersion) as error:
			report.not_checked.append(f"node: {error}, the node version not checked")
			return
		report.findings += [
			Finding(rule=rule, file="node", line=None, snippet=f"node {printed}", source="bench")
			for rule in rules
			if not SpecifierSet(rule.match.node).contains(version, prereleases=True)
		]

	def scan_target_branches(self, report: Report, app_roots: dict[str, Path], frappe_major: int):
		"""Only an app on the bench's frappe version branch is switched to the target's."""
		rules = self.rules_by_type.get("target_branch", ())
		for app, root in app_roots.items():
			branch = checked_out_branch(root)
			if not branch or not is_frappe_branch(branch, frappe_major):
				continue
			for rule in rules:
				target = rule.match.branch
				try:
					problem = missing_upstream_branch(root, target)
				except subprocess.CalledProcessError as error:
					reason = (error.stderr.strip().splitlines() or [f"exit code {error.returncode}"])[-1]
					report.not_checked.append(
						f"{app}: git {error.cmd[3]} failed, {reason}; whether upstream has {target} not checked"
					)
					continue
				except (OSError, subprocess.SubprocessError) as error:
					report.not_checked.append(f"{app}: {error}, whether upstream has {target} not checked")
					continue
				if problem:
					report.findings.append(
						Finding(
							rule=rule,
							file=f"upstream/{target}",
							line=None,
							snippet=f"{app} is on {branch}; {problem}",
							app=app,
						)
					)

	def scan_dependency_wheels(self, report: Report, app_roots: dict[str, Path], frappe_major: int | None):
		"""Reads the pyproject.toml of the apps scan.scan_bench reads it for, those the upgrade leaves on
		their branch, and of every app when there is no bench to switch them."""
		rules = self.rules_by_type.get("dependency_wheels", ())
		if not rules:
			return
		dependencies: list[tuple[str, list[str], str, Requirement]] = []
		unread: dict[str, list[str]] = {}
		for app, root in app_roots.items():
			pyproject = root / "pyproject.toml"
			if not pyproject.is_file():
				continue
			if frappe_major is not None:
				branch = checked_out_branch(root)
				if not branch:
					reason = "no branch checked out" if (root / ".git").exists() else "not a git checkout"
					unread.setdefault(reason, []).append(app)
					continue
				if is_frappe_branch(branch, frappe_major):
					continue
			try:
				source = pyproject.read_text(encoding="utf-8")
				dependencies += [
					(app, source.splitlines(), dependency, Requirement(dependency))
					for dependency in tomllib.loads(source).get("project", {}).get("dependencies", ())
				]
			except (OSError, ValueError) as error:
				report.not_checked.append(f"{app}/pyproject.toml: {error}, dependency wheels not checked")
		for reason, apps in unread.items():
			report.not_checked.append(
				f"pyproject.toml of {', '.join(apps)}: {reason}, dependency wheels not checked"
			)

		names = sorted(
			{canonicalize_name(requirement.name) for *_, requirement in dependencies if not requirement.url}
		)
		try:
			with ThreadPoolExecutor(max_workers=8) as pool:
				releases = dict(zip(names, pool.map(pypi_releases, names)))
		except (OSError, ValueError) as error:
			report.not_checked.append(f"pypi.org: {error}, dependency wheels not checked")
			return

		for rule in rules:
			python = next(
				release for release in PYTHON_RELEASES if SpecifierSet(rule.match.python).contains(release)
			)
			installable = {
				(tag.interpreter, tag.abi)
				for tag in (
					*cpython_tags((3, python.minor), abis=[f"cp3{python.minor}"], platforms=["any"]),
					*compatible_tags((3, python.minor), f"cp3{python.minor}", ["any"]),
				)
			}
			environment = {"python_version": f"3.{python.minor}", "python_full_version": str(python)}
			for app, lines, dependency, requirement in dependencies:
				if requirement.url or (requirement.marker and not requirement.marker.evaluate(environment)):
					continue
				project = releases[canonicalize_name(requirement.name)]
				if project is None:
					report.not_checked.append(
						f"{app}/pyproject.toml: {requirement.name} is not on pypi.org, its wheels not checked"
					)
					continue
				matching = final_releases(project, requirement.specifier)
				if release := newest_release(matching, python):
					version, files = release
					tags = wheel_tags(files)
					built_for = sorted(
						{tag.interpreter for tag in tags if tag.interpreter.startswith("cp3")},
						key=lambda interpreter: (len(interpreter), interpreter),
					)
					if not built_for or any((tag.interpreter, tag.abi) in installable for tag in tags):
						continue
					snippet = (
						f"{dependency}: {requirement.name} {version} has {', '.join(built_for)} wheels,"
						f" none for Python 3.{python.minor}"
					)
				elif matching:
					newest = max(matching)
					snippet = (
						f"{dependency}: pip finds no release for Python 3.{python.minor}; the newest,"
						f" {requirement.name} {newest}, requires Python {matching[newest][0]['requires_python']}"
					)
				else:
					continue
				report.findings.append(
					Finding(
						rule=rule,
						file="pyproject.toml",
						line=quoted_line(lines, toml_line(lines, "project", "dependencies") or 1, dependency),
						snippet=snippet,
						app=app,
					)
				)


def scan_online(
	report: Report, scanner: OnlineScanner, app_roots: dict[str, Path], frappe_major: int | None
) -> None:
	"""Append findings and not_checked lines to the report. A check that cannot reach git, node or PyPI
	says so in not_checked rather than passing. With no bench, `frappe_major` None, there is no node to
	ask and no branch to switch."""
	if frappe_major is not None:
		scanner.scan_node(report)
		scanner.scan_target_branches(report, app_roots, frappe_major)
	scanner.scan_dependency_wheels(report, app_roots, frappe_major)
