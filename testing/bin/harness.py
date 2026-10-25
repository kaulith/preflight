"""Scan an app source tree off disk, the way `preflight --path` reads one.

The corpus lives outside the repo, in ~/preflight-corpus unless PREFLIGHT_CORPUS names another directory.
"""

import os
from pathlib import Path

from preflight.app_scan import Scanners, scan_app
from preflight.models import Report

CORPUS = Path(os.environ.get("PREFLIGHT_CORPUS", Path.home() / "preflight-corpus"))
TESTING = Path(__file__).resolve().parent.parent


def scan_tree(rules, app_path: Path, skip_tests: bool = True):
	"""Findings, and the files that could not be parsed or read.

	Run this on the newest python on the machine: a file the parser cannot read is a file
	scanned as clean, which is how the first loop A run lost three findings.
	"""
	report = Report(site=None, target="", apps=[app_path.name])
	scan_app(report, Scanners(rules), app_path.name, app_path, skip_tests)
	return report.findings, report.unparsable_files + report.unreadable_files


def app_path(tree: str) -> Path:
	"""The package directory inside a corpus tree: corpus/hrms/hrms, corpus/erpnext-v15/erpnext."""
	return CORPUS / tree / tree.rsplit("-", 1)[0]
