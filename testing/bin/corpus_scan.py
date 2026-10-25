"""Scan every app in the corpus and freeze the result, so a rule change shows a diff.

PYTHONPATH=testing/bin:. python testing/bin/corpus_scan.py          # write testing/expected/<tree>.json
PYTHONPATH=testing/bin:. python testing/bin/corpus_scan.py --check  # compare with it, exit 1 on drift
"""

import json
import sys
from collections import Counter

from harness import CORPUS, TESTING, app_path, scan_tree

from preflight.rule_loader import load_rules

EXPECTED = TESTING / "expected"


def trees() -> list[str]:
	return sorted(path.name for path in CORPUS.iterdir() if path.is_dir())


def profile(tree: str, rules) -> dict:
	findings, unparsable = scan_tree(rules, app_path(tree))
	all_findings, _ = scan_tree(rules, app_path(tree), skip_tests=False)
	commit = CORPUS / f"{tree}.commit"
	return {
		"tree": tree,
		"commit": commit.read_text().strip() if commit.exists() else None,
		"counts": dict(sorted(Counter(finding.rule.id for finding in findings).items())),
		"counts_with_tests": dict(sorted(Counter(finding.rule.id for finding in all_findings).items())),
		"unparsable": unparsable,
		"findings": sorted(
			([finding.rule.id, finding.file, finding.line, finding.snippet] for finding in findings),
			key=lambda finding: (finding[0], finding[1], finding[2] or 0, finding[3]),
		),
	}


def table(profiles: list[dict]) -> str:
	rule_ids = sorted({rule_id for p in profiles for rule_id in p["counts_with_tests"]})
	header = f"{'rule':<46}" + "".join(f"{p['tree'][:11]:>12}" for p in profiles)
	lines = [header]
	for rule_id in rule_ids:
		row = f"{rule_id:<46}"
		for p in profiles:
			skipped = p["counts"].get(rule_id, 0)
			total = p["counts_with_tests"].get(rule_id, 0)
			row += f"{(f'{skipped}/{total}' if total else '-'):>12}"
		lines.append(row)
	lines.append(f"{'unparsable':<46}" + "".join(f"{len(p['unparsable']):>12}" for p in profiles))
	return "\n".join(lines)


def check(profiles: list[dict]) -> int:
	drift = 0
	for new in profiles:
		path = EXPECTED / f"{new['tree']}.json"
		if not path.exists():
			print(f"{new['tree']}: nothing frozen yet")
			drift = 1
			continue
		old = json.loads(path.read_text())
		gone = [f for f in old["findings"] if f not in new["findings"]]
		added = [f for f in new["findings"] if f not in old["findings"]]
		if old["commit"] != new["commit"]:
			print(f"{new['tree']}: frozen at {old['commit']}, corpus is at {new['commit']}")
			drift = 1
		for finding in gone:
			print(f"{new['tree']}: gone    {finding[0]}  {finding[1]}:{finding[2]}")
		for finding in added:
			print(f"{new['tree']}: added   {finding[0]}  {finding[1]}:{finding[2]}")
		drift = drift or bool(gone or added)
	return drift


if __name__ == "__main__":
	rules = load_rules("v16")
	profiles = [profile(tree, rules) for tree in trees()]
	print(table(profiles))
	if "--check" in sys.argv:
		sys.exit(check(profiles))
	EXPECTED.mkdir(parents=True, exist_ok=True)
	for p in profiles:
		(EXPECTED / f"{p['tree']}.json").write_text(json.dumps(p, indent="\t") + "\n")
	print(f"\nfrozen in {EXPECTED}")
