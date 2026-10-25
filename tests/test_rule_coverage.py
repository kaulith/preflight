from pathlib import Path

import pytest

from preflight.compatibility_scanner import CompatibilityScanner
from preflight.hooks_scanner import HooksScanner
from preflight.js_scanner import JSScanner
from preflight.models import ONLINE_MATCH_TYPES
from preflight.python_scanner import PythonScanner
from preflight.rule_loader import load_rules

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("target", ["v16", "v17"])
def test_every_shipped_rule_has_a_violation_line(target):
	rules = load_rules(target)
	python, js, hooks = PythonScanner(rules), JSScanner(rules), HooksScanner(rules)
	findings = []
	for path in sorted(FIXTURES.glob("violations*.py")):
		findings += python.scan(path.read_text(), path.name)
	for path in sorted([*FIXTURES.glob("violations*.js"), *FIXTURES.glob("violations*.scss")]):
		findings += js.scan(path.read_text(), path.name)
	for path in sorted(FIXTURES.glob("hooks_violations*.py")):
		findings += hooks.scan(path.read_text(), "hooks.py", FIXTURES / "digest")
		findings += hooks.missing_hooks(path.read_text(), "hooks.py", FIXTURES / "digest")
	compatibility = CompatibilityScanner(rules)
	findings += compatibility.scan_environment("3.10.0")
	findings += compatibility.scan_pyproject(
		(FIXTURES / "pyproject_violations.toml").read_text(), "pyproject.toml"
	)
	findings += compatibility.scan_required_apps(
		(FIXTURES / "hooks_violations.py").read_text(), "hooks.py", set()
	)
	fixture_rules = {rule.id for rule in rules if rule.match.type not in (*ONLINE_MATCH_TYPES, "site_record")}
	assert {finding.rule.id for finding in findings} == fixture_rules
