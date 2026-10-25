# Loop C score: the real upgrade

Site `v15.preflight.test`, frappe 15.121.3 and erpnext 15.121.6 plus the `upgrade_probe` app and
five seeded customisations, upgraded to frappe 16.36.1 and erpnext 16.37.0.

- `before.json`: 310 findings, 16 error, 293 warning, 1 info.
- `after.json`: 29 findings. erpnext's 285 are gone because erpnext is now v16 code; every finding
  against the probe app and the site records is still there, because nothing in them changed.
- `probes-v16.json`, `tests-v16.log` (every test erroring in setUp), and
  `tests-v16-override-fixed.log` (the same suite with the override made a subclass).

## Predicted and it broke

| what broke | how | rule, severity |
|---|---|---|
| every ToDo read and write | `ValidationError: ProbeToDo must be a subclass of ToDo` | v16-override-doctype-class-subclass, warning |
| `frappe.get_all("Blog Post")` | `DoesNotExistError: DocType Blog Post not found` | v16-removed-blog-doctypes, error |
| `from frappe.website.doctype.blog_post.blog_post import get_blog_list` | `ModuleNotFoundError` | v16-removed-blog, error |
| `from frappe.social...energy_point_log import get_energy_points` | `ModuleNotFoundError: frappe.social` | v16-removed-energy-points, error |
| `from frappe.tests_runner import make_test_records` | `ModuleNotFoundError` | v16-removed-tests-runner, error |
| `frappe.db.get_single_value("Dropbox Settings", ...)` | `DoesNotExistError` | v16-removed-backup-doctypes, error |
| a non-owner System Manager loses access to ToDo | hook returns None, v16 reads that as deny | v16-has-permission-hook-returns-true, warning |
| `frappe.db.value_cache[(dt, name, field)]` reads None | silent: `None != 'Open'` | v16-value-cache-nested, warning |
| `get_gravatar` returns an identicon data URI | silent: `'gravatar.com' not found in 'data:image/png;base64,...'` | v16-deprecated-gravatar-helpers, warning |

The two silent ones are the whole argument for the deprecation rules. Nothing raises, nothing
logs, and a test that asserted the old value is the only thing that notices.

The override break is total: every `frappe.get_doc("ToDo")` fails, so all 13 probe tests errored
in `setUp` until the class was made a subclass. A warning is the wrong weight for that, and it is
the second time this rule has come up; loop B found all ten override classes in the corpus
already subclass, so narrowing it to the apps that do not would make it a precise error.

## Predicted, ran fine

- `gzip_compress`, `get_number_format_info` and `frappe.db.is_column_missing` all still work and
  log a deprecation warning, `V16FrappeDeprecationWarning` for the second. Correct and latent:
  they go at v17.
- The five seeded customisations survive the migration untouched: the Custom Field on Newsletter,
  the link field on Contact, the Property Setter on Energy Point Log, the Server Script and the
  Client Script are all still there, and migrate only reports the doctypes as orphaned. It names
  all 25, including Newsletter, Blog Post, Energy Point Log, Transaction Log, Dropbox Settings,
  and it deletes the leaderboard page, which is the `leaderboards` hook rule coming true.
- `leaderboards` stopped being read, with nothing raised, exactly as the rule says.

## Missed: no rule covers these, and two of them stopped the upgrade

1. **python 3.12 is not enough of a detail to leave out.** frappe v16 uses `type X = ...`
   statements, so the bench env had to be rebuilt on 3.14. On 3.11 `bench setup requirements`
   fails with a bare `SyntaxError`.
2. **Stale bytecode directories kill `bench migrate`.** After `git checkout version-16`, every
   removed module is still a directory holding `__pycache__`, so `frappe.social`,
   `frappe.website.doctype.blog_post` and the rest import as namespace packages with
   `__file__ = None`, and `frappe/model/sync.py` dies with
   `TypeError: expected str, bytes or os.PathLike object, not NoneType`. Deleting the
   `__pycache__` directories and then the empty directories fixes it.
   (`migrate-fail-stale-pycache.log` holds the failure.)
3. **`bench migrate` rewrites `sites/apps.txt`** from the apps installed on the site, which drops
   any app that is deliberately not installed: preflight itself disappeared and
   `bench preflight` became "No such command". Both 1 and 3 are now in the README.
4. **`frappe.tests.utils.change_settings` on System Settings** fails with
   `MandatoryError: [System Settings]: language, time_zone`. The new
   `v16-deprecated-tests-utils-helpers` rule names the API, so it is reported, but for the wrong
   reason: the helper moved, and separately System Settings gained mandatory fields.
5. **Orphan tables keep answering SQL.** `select name from tabTransaction Log` still returns rows
   after the upgrade, and the single doctypes keep 17 or 18 rows each in `tabSingles`. The ORM
   raises and raw SQL does not, so the planted raw-SQL probe did not break. The five doctype rule
   messages now say this.

## Inconclusive

- The default sort order change could not be measured: the only ToDo row was created by the probe
  run, so `oldest_todo()` has nothing to order.
- No v15 baseline run of the probes exists, because the branch switch started before the probes
  were written. Every v16 failure names its own cause in the exception, and the two silent changes
  were pinned by assertions written against v15 values, so the gap costs the score little. Next
  time the probe run comes before the switch.
