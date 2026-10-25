# Loop D: coverage against the v16 deprecation dumpster

`PYTHONPATH=testing/bin:. python testing/bin/dumpster_coverage.py`, from the repo root, parses
every `@deprecated(...)` and `@deprecation_warning(...)` decorator in the corpus's
`frappe-v16/frappe/deprecation_dumpster.py` and matches the path each one names against the paths
the shipped rules carry, by full path, by dotted prefix, and by leaf name.

Before: 24 of 36. After three rules: 32 of 36.

## Shipped because of this loop

| rule | paths | why |
|---|---|---|
| v16-deprecated-show-progress | `frappe.desk.doctype.bulk_update.bulk_update.show_progress` | re-exported from the dumpster on v16, removed v17 |
| v16-deprecated-tests-utils-helpers | `frappe.tests.utils.change_settings`, `patch_hooks`, `debug_on`, `timeout`, `get_dependencies` | moved off `frappe.tests.utils`, removed v17 |
| v16-deprecated-tests-system-settings | `frappe.tests.get_system_setting`, `frappe.tests.update_system_settings` | marked for removal in v17 |

## The four left uncovered, and why

- **`User.validate_roles`** is a method on a document, not a path. Nothing in the matcher
  vocabulary can see `user.validate_roles()` without knowing what `user` is.
- **`frappe.deprecations.deprecation_warning`** names a module that exists on neither v15 nor
  v16; `frappe/deprecations.py` is already gone in the v15 tree. An app still importing it is
  broken before the upgrade starts, so it is not a v15 to v16 break.
- **`frappe.model.trace.traced_field_context`** is a debugging context manager. Expressible as
  an `import_path` rule, but no app in the twelve-tree corpus imports it, so it would be a rule
  carried for nobody.
- **`modules.txt`** is a file, and its graduation reads "yet unknown". Not an API.

## Corrections to the dumpster's own labels

- The entry reading `frappe.desk.doctype.bulk_update.bulk_update` decorates `show_progress`, so
  the deprecated symbol is the function, not the module. The module is still in v16 and still
  ships `bulk_update.py`; what changed is that it now imports `show_progress` from the dumpster.
  The rule carries the full path to the function.
- `frappe.tests.upate_system_settings` is the dumpster's label only. `frappe/tests/__init__.py`
  exports the function as `update_system_settings`, so that is the name an app imports and the
  one the rule carries. The script matches labels, so it now counts 31 of 36; the entry is still
  covered.

## What the new rules find in the corpus

- `show_progress`: `frappe/core/doctype/deleted_document/deleted_document.py:8` on both v15 and
  v16. The framework still imports its own deprecated helper.
- `tests.utils` helpers: 48 findings in erpnext, 24 in frappe, 3 in helpdesk, every one in a
  test file and zero with `--skip-tests`. The only non-test hit is
  `deprecation_dumpster.py:636`, which is the dumpster importing what it replaced.
- `tests.get_system_setting`: nothing in any tree. The rule rests on the dumpster entry and its
  fixture line.
