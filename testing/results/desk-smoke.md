# Loop C desk pass: the real upgrade, clicked

Site `smoke.localhost` on a throwaway bench in `~/preflight-test/bench`, company Northwind Traders:
frappe v15.124.0 and erpnext v15.124.1 on Python 3.11, built with assets, upgraded to frappe
v16.53.0 and erpnext v16.52.1 on Python 3.14.3 and node 24.15.0. Every page below was opened as
Administrator in a browser on v15 first, where all of them loaded and every planted script did its
job, then again on v16.

- `before.json` (v15): 33 findings, 23 error, 10 warning; erpnext's 674 listed as upstream.
- `after.json` (v16): 44 findings. `v16-bench-python` is gone with the new env; the other 32 are
  unchanged, because the probe app and the site records did not change; 12 more are erpnext's own
  v16 code, counted now that the bench runs the target.

## Planted on v15

The five loop C customisations, `upgrade_probe` unchanged, and ten more aimed at the desk: Client
Scripts using an octicon, `user.get_roles`, Accounts Settings `acc_frozen_upto`, a `sum(...)` field
string, `frappe.views.ListSidebar`, `frappe.energy_points` and Repost Accounting Ledger Settings;
two Custom HTML Blocks on a workspace reading `frappe.boot.changelog_feed` and calling
`get_workspace_sidebar_items`; a Custom Field after Payment Entry's `party_balance`; and two Repost
Allowed Types rows, Sales Invoice allowed and Payment Entry not.

## Predicted and it broke

| page | on v16 | rule |
|---|---|---|
| Sales Invoice list, form, Report view, Accounts Settings, Accounts Receivable | `TypeError: Cannot read properties of undefined (reading 'prototype')` from the list script, on every page that loads Sales Invoice | v16-removed-list-sidebar |
| workspace with the two HTML blocks | "Failed to get method for command frappe.desk.desktop.get_workspace_sidebar_items" (417); `TypeError` reading `slice` | v16-removed-workspace-sidebar-items, v16-removed-changelog-feed-js |
| Sales Invoice form | "Failed to get method for command frappe.core.doctype.user.user.get_roles" (417); the octicon renders as nothing | v16-removed-user-get-roles, v16-removed-octicons |
| Assign To, ToDo form | "Invalid Override ToDo: upgrade_probe.overrides.ProbeToDo must be a subclass of ... ToDo" (417) | v16-override-doctype-class-subclass |
| Payment Entry form | "Field acc_frozen_upto does not exist on Accounts Settings" (417) | v16-erpnext-moved-settings |
| Payment Entry, the Custom Field | moves from after `party_balance` (21 of 94) to the end of the form (93 of 94) | v16-erpnext-removed-fields |
| Customer form | "SQL functions are not allowed as strings in SELECT: sum(grand_total) as total_billed" (417) | v16-sql-function-string-fields |
| Contact, the Blog Post link | renders; typing gets a 404 and "No results found" | v16-removed-blog-doctypes |
| Task form | `TypeError` reading `get_points` | v16-removed-energy-points-js |
| Repost Accounting Ledger, new | "No module named 'frappe.core.doctype.repost_accounting_ledger_settings'" (500) | v16-erpnext-repost-settings-doctype |
| Newsletter, Energy Point Log, Repost Accounting Ledger Settings, Leaderboard | "Page ... not found"; migrate deleted the leaderboard page | the removed doctype and hook rules |
| Server Script API call | `BlockedRequest: Requests to internal network addresses are not permitted` | v16-server-script-private-request |

## Missed

- Repost Allowed Types: Payment Entry, unchecked on v15, can be reposted on v16, with Purchase
  Invoice, Journal Entry and Purchase Receipt, which v15 never listed.
  `get_allowed_types_from_settings()` went from `['Sales Invoice']` to all five. The patch
  `merge_repost_settings_to_accounts_settings` fills Accounts Settings from erpnext's
  `repost_allowed_doctypes` hook and never reads the v15 rows, and both readers
  (`repost_accounting_ledger.py:442-456`, `:517-535`) read every row whatever its parent and
  `allowed`, so the v15 rows still count. An erpnext bug; nothing raises.
- A custom public workspace no longer shows in v16's navigation. It still opens by URL and from
  search.

## Changed because of the run

- The removed-doctype rules said every read raises `DoesNotExistError`. A query does; `frappe.get_doc`
  falls back to module Core for a doctype the migration deleted and raises `ImportError` ("Module
  import failed"), which the desk shows as a 500. The twelve messages now say both.
- The field rules now say that a Custom Field placed after a removed field moves to the end of the
  form.

## Workspaces, checked after the run

Seeded on the upgraded site as v15 leaves each row, then the v16 patch that reads them run over
them: a private page Priya Nair made in the desk (no module, label
`Month End Close-priya.nair@example.com`) and a custom module Fleet Management (`app_name` erpnext,
which v15's Module Def requires) holding a public page Fleet Dispatch, through
`backfill_workspace_module`; a public workspace Route Planning shipped by `upgrade_probe` as a v15
app ships one, synced by migrate, through `set_standard_flag`.

| workspace | on v16 | what brings it back |
|---|---|---|
| private, Month End Close | moved to `Private`, listed only under My Space, which the user menu shows when the user's Show My Space is on; it is off by default | the user ticks Show My Space in Settings, Preferences |
| public in a custom module, Fleet Dispatch | placed in ERPNext and on no rail, which lists only the Dock record ERPNext ships; Manage Dock says "1 of this app's modules are on no tier at all" | Manage Dock, Add, Module Fleet Management, saved For everyone |
| shipped by an app, Route Planning | no tile, since the Apps screen shows only apps declaring `add_to_apps_screen`, and no rail, since the app ships no Dock | `add_to_apps_screen` with a `route` gives a tile that opens it; a shipped Dock (`<app>/dock/<app>/<app>.json`) gives the app a rail |

All three still open from search and by URL. A Dock without the hook gives a rail on the page but
no tile leads there; the hook without a Dock opens the route's workspace with its module's sidebar
and no rail. A custom module left with `app_name` frappe, which is what the v15 form fills in, is
placed in Framework: Field Service, holding a public page Service Visits, was on no rail until
Manage Dock there added it For everyone.

Each break is now a rule: `v16-private-workspace-my-space`, `v16-custom-module-workspace-dock` and
`v16-app-workspaces-apps-screen`. Run against this site with the probe app back to no hook, they
reported Month End Close, Fleet Dispatch and Service Visits, and `upgrade_probe/hooks.py`, and
nothing else.

## Upgrade notes

- `bench setup requirements` on the 3.11 env: `SyntaxError` at `type ConfType = ...`, as
  `v16-bench-python` says; `bench setup env --python` over an existing env reinstalls into it, so
  the old env was moved aside first, as the upgrade checklist says.
- node 20: `The engine "node" is incompatible with this module. Expected version ">=24"`.
- Migrate ran first time. Loop C's stale bytecode failure did not come back with 21 such directories
  left in frappe and 12 in erpnext; migrate removed 26 orphaned doctypes.
