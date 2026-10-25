"""Call every probe on the site and record what each one does.

Run it from the bench's sites directory with that bench's python, once per version line:

	cd <bench>/sites
	../env/bin/python <repo>/testing/bin/run_probes.py v16

Writes testing/results/upgrade/probes-<label>.json: one entry per probe with the value it returned or
the exception it raised, so the same file can be compared across the upgrade.
"""

import json
import sys
import traceback
from pathlib import Path

import frappe

RESULTS = Path(__file__).resolve().parent.parent / "results" / "upgrade"
SITE = "v15.preflight.test"


def probe_calls(todo_name: str) -> dict:
	from upgrade_probe import probes

	return {
		"get_leaderboards": lambda: probes.get_leaderboards(),
		"leaderboard_rows": lambda: probes.leaderboard_rows(None, None, "priority", 5),
		"compress_digest": lambda: probes.compress_digest("Check the digest"),
		"owner_avatar": lambda: probes.owner_avatar("Administrator"),
		"number_separators": lambda: probes.number_separators(),
		"blog_titles": lambda: probes.blog_titles(),
		"blog_list": lambda: probes.blog_list(),
		"energy_points": lambda: probes.energy_points("Administrator"),
		"seed_todo_records": lambda: probes.seed_todo_records(),
		"offsite_backup_enabled": lambda: probes.offsite_backup_enabled(),
		"cached_status": lambda: probes.cached_status(todo_name),
		"missing_column": lambda: probes.missing_column(Exception("Unknown column 'x' in 'tabToDo'")),
		"oldest_todo": lambda: probes.oldest_todo(),
		"transaction_log_rows": lambda: probes.transaction_log_rows(),
		"override_reaches_controller": lambda: frappe.get_doc("ToDo", todo_name).probe_label(),
		"non_owner_permission": lambda: frappe.has_permission(
			"ToDo", doc=todo_name, user="probe@example.com"
		),
	}


def run(label: str) -> dict:
	frappe.init(site=SITE)
	frappe.connect()
	results = {}
	todo_name = None
	try:
		todo_name = (
			frappe.get_doc(
				doctype="ToDo", description="Check the digest after the upgrade", priority="Medium"
			)
			.insert()
			.name
		)
		results["insert_todo"] = {"returned": todo_name}
	except Exception as e:  # noqa: BLE001
		results["insert_todo"] = {"raised": type(e).__name__, "message": str(e)[:300], "where": []}
		todo_name = frappe.db.get_value("ToDo", {}, "name")
	for name, call in probe_calls(todo_name).items():
		try:
			results[name] = {"returned": repr(call())[:200]}
		except Exception as e:  # noqa: BLE001
			results[name] = {
				"raised": type(e).__name__,
				"message": str(e)[:300],
				"where": traceback.format_exc().strip().splitlines()[-3:],
			}
	frappe.db.rollback()
	return {"label": label, "site": SITE, "probes": results}


if __name__ == "__main__":
	label = sys.argv[1] if len(sys.argv) > 1 else "unlabelled"
	result = run(label)
	RESULTS.mkdir(parents=True, exist_ok=True)
	(RESULTS / f"probes-{label}.json").write_text(json.dumps(result, indent="\t") + "\n")
	for name, outcome in result["probes"].items():
		state = outcome.get("raised", "ok")
		detail = outcome.get("message", outcome.get("returned", ""))
		print(f"{name:<32}{state:<28}{detail[:70]}")
