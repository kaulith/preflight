# Loop B triage

`PYTHONPATH=testing/bin:. python testing/bin/corpus_scan.py` from the repo root, python 3.14 with
pyyaml, packaging and semantic-version (a v16 bench's `env/bin/python` has all three), twelve
trees: the four version pairs from loop A plus crm, helpdesk, hrms, wiki, print_designer,
telephony, caffeine and bwh_hive, each at a recorded commit. The table prints
`with --skip-tests / total`, and `--check` exits 1 on any drift against the frozen files in
`testing/expected/`.

Nothing is unparsable in any tree.

## The corpus

It is not repo content. The harness reads it from `~/preflight-corpus`, or from
`$PREFLIGHT_CORPUS` when that is set. Each tree is a clone at the `commit` its
`testing/expected/<tree>.json` records, with that hash in `<tree>.commit` beside it. The repos:
frappe/frappe for frappe-v15 and frappe-v16, frappe/erpnext for erpnext-v15 and erpnext-v16,
bwhtech/hive for bwh_hive, and frappe/<tree> for the rest. One tree, rebuilt:

	corpus=${PREFLIGHT_CORPUS:-~/preflight-corpus}
	git init -q $corpus/erpnext-v15
	git -C $corpus/erpnext-v15 fetch --depth 1 https://github.com/frappe/erpnext.git <commit>
	git -C $corpus/erpnext-v15 checkout FETCH_HEAD
	echo <commit> > $corpus/erpnext-v15.commit

## The bulk is test-only, and already handled

| rule | worst tree | with tests | with --skip-tests |
|---|---|---|---|
| v16-deprecated-frappe-test-case | frappe-v15 | 263 | 0 |
| v16-deprecated-get-test-records | erpnext-v15 | 60 | 0 |

Both live entirely in `test_*` files and `tests/` directories across every app that has tests:
erpnext 163 and 60, helpdesk 18, wiki 9, crm 7. `--skip-tests` takes each to zero, which is the
flag earning its place a second time. They stay `warning`: the test suite breaks on v16, and
the README already says to run once without the flag.

## Every other rule is small

No rule outside those two exceeds 13 findings in any tree, and 7 of the 12 trees report fewer
than 3 findings in total. There is no readability problem left to solve in the report itself.

Since the 2026-10-25 refreeze that holds for every tree but two. frappe v15 reports its own
moved-out modules naming each other (`v16-removed-blog-doctypes` 38, `v16-removed-energy-point-doctypes`
33, `v16-removed-backup-doctypes` 23). erpnext v15 reports 84 `v16-sql-function-string-fields` with
`--skip-tests` (64 before the second 2026-10-25 pass taught it variables and f-strings), all true
and all already rewritten on erpnext's version-16 branch. frappe's own vendored Octicons
stylesheets give ~390 `v16-removed-octicons` in each frappe tree since SCSS is scanned; a real scan
never reads frappe itself.

## Two rules fire on correct code across the corpus

**`v16-override-doctype-class-subclass`** fires on 6 trees: caffeine, crm, helpdesk, hrms,
print_designer, erpnext. All 10 override classes named by those hooks already subclass the
controller they replace: `WarehouseOverride(Warehouse)`, `CustomContact(Contact)`,
`CustomEmailTemplate(EmailTemplate)`, `CustomEmailAccount(EmailAccount)`,
`HelpdeskAssignmentRule(AssignmentRule)`, `HelpdeskUserInvitation(UserInvitation)`,
`EmployeeMaster(Employee)`, `EmployeeTimesheet(Timesheet)`, `PDPrintFormat(PrintFormat)`.

Not demoted. An app that does not subclass is dead on v16: `get_controller` throws and every
read or save of that doctype fails, so hiding it under `info` trades a loud false positive for
a silent site-down. The narrowing is cheap and sound here, and is the one improvement this loop
asks for: the hook value is a dotted path to a class, so follow it into the app's own source,
read the `class X(Base)` line, and report only when no base name matches the doctype with its
spaces removed. That turns a warning on six correct apps into an error on the one that is
broken.

**`v16-has-permission-hook-returns-true`** fires on 5 trees: bwh_hive, crm, helpdesk, wiki,
frappe. All of them are safe on v16. crm looked like the exception, because
`has_lead_permission` holds no `return True` at all, but it delegates to `_has_permission`,
which returns `True` on four branches and `bool(...)` at the end.

Not demoted, and not narrowed. A hook that falls off the end returns None, which v16 reads as
deny, so the failure is every user locked out of that doctype; `info` is the wrong severity for
that. The obvious narrowing, "the hooked function never says `return True`", is exactly the
check that crm would have failed, so reading the hook target one level deep is not sound. Doing
it properly means following delegation, which is more than a matcher.

Narrowed later, on the opposite question. The rule is now `v16-has-permission-hook-returns-none`,
an `error` from the `returns_none` match type: it reads each hooked function and reports the entry
when a path falls off the end, returns bare, or returns None. That is the exact change in
`has_controller_permissions`, `if controller_permission is not None` in v15 and
`if not controller_permission` in v16. Asking whether a path can return None, rather than whether
one says `return True`, is what keeps crm clean: `return _has_permission(...)` is a value whatever
it evaluates to. On the corpus it is silent on bwh_hive, crm, helpdesk, wiki and frappe v16, and
reports two entries in frappe v15, `User` and `Communication`, whose functions fall off the end;
v16 added `return True` to both. An entry whose function is not in the app's own source gets
`v16-has-permission-hook-unreadable`, the old `warning`; no corpus entry does. What it cannot see
is a helper behind `return helper(...)` that returns None.

## Incidental

caffeine's only `frappe.db.value_cache` use is `frappe.db.value_cache.clear()` in a
microbenchmark, which works the same on both versions. It is the one use of that API in any
real app in the corpus, and it is the form the rule cannot tell apart from the flat-key form.

## Postscript

The narrowing this loop asked for was built in Phase 14, as the `override_subclass`
match type. Re-running the corpus afterwards dropped exactly six findings,
one per app named above, and added none.

Later correction, Phase 16. That re-run proved less than it looked. `scan_tree` in
`testing/bin/harness.py` called the hooks scanner without an app path, and an `override_subclass` rule
reports nothing without one, so the six went away because the check was off, not because the
resolver had read the classes. The harness passes the app path now. The frozen counts stand: all
ten override classes are read by hand above and every one subclasses its controller, which is the
answer the resolver gives as well. `testing/bin/differential.py` held a second copy of `scan_tree` with
the same omission; it imports the harness one now.
