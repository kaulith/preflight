# What the v16 upgrade tickets say

Support tickets from the v15 to v16 upgrade window, 2026-05-01 to 2026-08-31, read on
2026-10-06. Counts only; no ticket text, customer or site is recorded here.

1,572 tickets matched on subject (v16, upgrade, deploy, build, migrate, update failed) or on the
type `Deploy issues`. 360 of them mention v16 or carry the type `Version Upgrade`, and the full
thread was read for those. The counts are keyword and regex matches over ticket text, not a
per-ticket diagnosis, and they overlap.

Only 53 of the 360 threads hold a traceback or an error line. The rest describe the failure in
prose, so the error itself is in a screenshot or the deploy log.

## Themes in the 360 v16 threads

| theme | threads | covered today |
|---|---|---|
| a custom app is involved | 53 | scanned for API use only |
| `payments` app missing or incompatible | 37 | missing from the bench only |
| `insights` app | 32 | no |
| Python version | 30 | yes, bench and app `requires-python` |
| workspace, sidebar, desk UI | 30 | no |
| dependency or `pyproject.toml` bounds | 17 | frappe bound only |
| a patch failed during migrate | 13 | no |
| Server Script | 13 | yes |
| the app has no v16 branch | 10 | no |
| `has_permission` | 9 | yes |

## Shipped because of this

| rule | why |
|---|---|
| v16-moved-frappe-config-helpers | `cannot import name 'get_modules_from_all_apps_for_user' from 'frappe.config'`; the module was emptied in v16 and the helpers moved to `frappe.utils.modules` |
| v16-removed-pkg-resources | `pkg_resources`, 32 tickets in the wider set; v16 needs Python 3.14, so a bench on 3.10 to 3.13 builds a new environment, which gets no setuptools or setuptools 82 or later, and 82 dropped `pkg_resources` |

## Checked and not shipped

- `frappe.desk.form.assign_to._add`: still present on version-16, so the ticket was not an
  upgrade break.
- `frappe.core.doctype.workspace_settings`: never in v15 and gone from version-16, so no v15 site
  can depend on it.

## Parked

- **Compatibility check.** Shipped 2026-10-25 as the `bench_python`, `requires_python`,
  `frappe_bound` and `required_apps` match types (see `preflight/rules/README.md`). Still out:
  whether an app has a branch for the target, which needs a network call, and conflicts between
  an app's pinned dependencies and frappe's, which need frappe's dependency list per target.
- **`pkg_resources`.** Shipped 2026-10-25 as `v16-removed-pkg-resources`, an upgrade rule after
  all. It was first dropped as missing from the v15 bench environment too, but that environment is
  a fresh Python 3.14 one, where ERPNext's `pycountry~=22.3.5` pulled in setuptools 82.0.1, and
  setuptools 82.0.0 (2026-02-08) removed `pkg_resources`. Neither frappe v15 nor v16 declares
  setuptools: the v16 bench environment (frappe, erpnext, hrms) has none, and the frappe-dev-bench
  one still has 80.9.0 with `pkg_resources`. A v15 bench keeps the setuptools its environment was
  built with until the move to 3.14 rebuilds it.
- **Deploy logs as the source.** Ticket text carries the error in 53 of 360 threads. The deploy
  log carries it every time, and is what a "would have caught X of N" figure needs.
- **`Changelog Feed`.** Shipped 2026-10-25: the removal (frappe/frappe#40472) is in v16.50.0, and
  v16 has `v16-removed-changelog-feed` (module), `-doctypes` (doctype), `-hook`
  (`get_changelog_feed`) and `-js` (boot data and the Marketplace search helper).
- **`start` and `page_length`** on `get_all` and `get_list`: deprecated alongside `limit_start`
  and `limit_page_length`, which have v17 rules. `with_kwargs` matches all of its keywords at
  once, so each needs its own file, or the matcher needs an any-of form.
- **Patch failures and desk UI changes** are out of reach of a static scan.

The frozen corpus results in `testing/expected/` predate v16-moved-frappe-config-helpers and the
fix to v16-deprecated-tests-system-settings, and have not been rerun.
