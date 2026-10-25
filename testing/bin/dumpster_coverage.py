"""Every entry in v16's deprecation dumpster, against the shipped rules.

The dumpster is the framework's own list of what it deprecated and when it goes, so it is the
one inventory worth measuring coverage against. It names the path the symbol used to have,
which is not always the path code imports it from, so the leaf name is matched as well as the
full path.

	PYTHONPATH=testing/bin:. python testing/bin/dumpster_coverage.py
"""

import ast

from harness import CORPUS

from preflight.rule_loader import load_rules

DUMPSTER = CORPUS / "frappe-v16" / "frappe" / "deprecation_dumpster.py"


def entries() -> list[tuple[str, str, str]]:
	"""(deprecated path, graduation, the name it is defined as) for every dumpster entry."""
	found = []
	tree = ast.parse(DUMPSTER.read_text(), filename=str(DUMPSTER))
	for node in ast.walk(tree):
		if not isinstance(node, ast.FunctionDef):
			continue
		for decorator in node.decorator_list:
			if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name):
				continue
			if decorator.func.id not in ("deprecated", "deprecation_warning"):
				continue
			args = [arg.value for arg in decorator.args if isinstance(arg, ast.Constant)]
			if not args:
				continue
			if decorator.func.id == "deprecated":
				path, graduation = args[0], args[2] if len(args) > 2 else "?"
			else:
				path, graduation = node.name, args[1] if len(args) > 1 else "?"
			found.append((path, graduation, node.name))
	return sorted(set(found))


def rule_paths() -> dict[str, list[str]]:
	paths = {}
	for rule in load_rules("v16"):
		for path in rule.match.paths:
			paths.setdefault(path, []).append(rule.id)
		for key in rule.match.keys:
			paths.setdefault(key, []).append(rule.id)
	return paths


def covering(path: str, paths: dict[str, list[str]]) -> tuple[str, str]:
	"""The rule covering this dumpster path, and how it matched."""
	for rule_path, rule_ids in paths.items():
		if path == rule_path:
			return rule_ids[0], "path"
		if path.startswith(f"{rule_path}.") or rule_path.startswith(f"{path}."):
			return rule_ids[0], "prefix"
	leaf = path.rsplit(".", 1)[-1]
	for rule_path, rule_ids in paths.items():
		if rule_path.rsplit(".", 1)[-1] == leaf:
			return rule_ids[0], "leaf"
	return "", ""


if __name__ == "__main__":
	paths = rule_paths()
	rows = [(path, graduation, *covering(path, paths)) for path, graduation, _ in entries()]
	print(f"{'dumpster entry':<56}{'goes':<8}{'match':<8}rule")
	for path, graduation, rule_id, how in sorted(rows, key=lambda row: (not row[2], row[0])):
		print(f"{path:<56}{graduation:<8}{how:<8}{rule_id or '-'}")
	covered = sum(1 for row in rows if row[2])
	print(f"\n{covered}/{len(rows)} dumpster entries covered by a rule")
