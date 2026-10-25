"""Grade every rule against the app's own v16 branch.

A finding on the v15 tree earns its place if the file it points at had to change to run on
v16. Both trees are scanned with the same rules, and the two sets of findings are compared per
rule and per file: a rule that still fires on the v16 tree, in the same file, either caught a
leftover the maintainers never cleaned up or is wrong about the code.

	PYTHONPATH=testing/bin:. python testing/bin/differential.py erpnext frappe
"""

import json
import sys
from collections import defaultdict

from harness import CORPUS, TESTING, scan_tree

from preflight.rule_loader import load_rules

RESULTS = TESTING / "results" / "differential"


def files_by_rule(findings) -> dict[str, dict[str, int]]:
	counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
	for finding in findings:
		counts[finding.rule.id][finding.file] += 1
	return counts


def grade(app: str, skip_tests: bool = True) -> dict:
	rules = load_rules("v16")
	old_tree = CORPUS / f"{app}-v15" / app
	new_tree = CORPUS / f"{app}-v16" / app
	old_findings, old_unparsable = scan_tree(rules, old_tree, skip_tests)
	new_findings, new_unparsable = scan_tree(rules, new_tree, skip_tests)
	old = files_by_rule(old_findings)
	new = files_by_rule(new_findings)

	graded = {}
	for rule_id in sorted(set(old) | set(new)):
		survived = sorted(set(old[rule_id]) & set(new[rule_id]))
		graded[rule_id] = {
			"hits_v15": sum(old[rule_id].values()),
			"fixed": [
				{
					"file": file,
					"file_gone": not (new_tree.parent / file).exists(),
					"hits": old[rule_id][file],
				}
				for file in sorted(set(old[rule_id]) - set(new[rule_id]))
			],
			"survived": [{"file": file, "hits": new[rule_id][file]} for file in survived],
			"only_v16": sorted(set(new[rule_id]) - set(old[rule_id])),
		}
	return {
		"app": app,
		"skip_tests": skip_tests,
		"commits": {line: (CORPUS / f"{app}-{line}.commit").read_text().strip() for line in ("v15", "v16")},
		"unparsable": {"v15": old_unparsable, "v16": new_unparsable},
		"rules": graded,
	}


def table(result: dict) -> str:
	unparsable = result["unparsable"]
	lines = [
		f"{result['app']}  v15 {result['commits']['v15'][:10]} → v16 {result['commits']['v16'][:10]}",
		f"unparsable: {len(unparsable['v15'])} on v15, {len(unparsable['v16'])} on v16",
		"",
	]
	lines.append(f"{'rule':<46}{'v15':>5}{'fixed':>7}{'left':>6}{'new':>5}")
	for rule_id, row in result["rules"].items():
		left = sum(entry["hits"] for entry in row["survived"])
		lines.append(
			f"{rule_id:<46}{row['hits_v15']:>5}{len(row['fixed']):>7}{left:>6}{len(row['only_v16']):>5}"
		)
	return "\n".join(lines)


if __name__ == "__main__":
	RESULTS.mkdir(parents=True, exist_ok=True)
	for app in sys.argv[1:]:
		result = grade(app)
		(RESULTS / f"{app}.json").write_text(json.dumps(result, indent="\t") + "\n")
		print(table(result), end="\n\n")
