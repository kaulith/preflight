# v17: not covered by a rule

Checked against frappe develop [`2746cacf9115bec32a06a894d9f69c92457667c0`](https://github.com/frappe/frappe/commit/2746cacf9115bec32a06a894d9f69c92457667c0) and erpnext develop [`feefe15ca5b57c2601d57a673720f4196bd9ec2e`](https://github.com/frappe/erpnext/commit/feefe15ca5b57c2601d57a673720f4196bd9ec2e), compared with frappe v16.60.2 and erpnext v16.60.0.

Each entry is a real v16 to v17 change that no Preflight match can pin to the code it breaks, so a scan stays silent on it and an app owner has to check it by hand. Every entry was read from both trees. None was run on a v17 site, and the two Postgres entries were not run on a Postgres server. v17 is not released, so recheck this list against 17.0.0.

## Endpoints and API calls

### PDF and file endpoints gained rate limits

`authenticated-file-endpoints-rate-limited`

- **What changes:** `download_pdf` allows 30 calls a minute, `download_file` 120 and `upload_file` 300, per user, or per IP for Guest. Administrator is not exempt, and a call over the limit raises `RateLimitExceededError` (HTTP 429).
- **Who it affects:** An integration that exports or uploads in a loop on one API key, or a method that calls `download_pdf` repeatedly inside one request, since those calls share the counter. Background jobs are not limited.
- **Why no match:** The break depends on how many calls run in a minute, and a match only sees that a call exists.
- **Check by hand:** Find loops that fetch PDFs or files over HTTP. Throttle them, batch PDFs with `download_multi_pdf`, or move the work to a background job.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/utils/print_format.py#L401-L403), [develop `download_pdf`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/utils/print_format.py#L424-L427), [develop `upload_file`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/handler.py#L131-L133), [develop `download_file`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/handler.py#L296-L298)

### Login, portal and search endpoints gained rate limits

`guest-endpoints-rate-limited`

- **What changes:** Per IP and per minute, the OAuth login callbacks allow 60 calls, `login_via_token` 10, LDAP login 10 for each `usr`, `web_search` 30, a web form's `get_form_data` 30, `make_view_log` 120 and `accept_invitation` 10. `update_password` allows 10 calls in 10 minutes per user, or per IP for Guest.
- **Who it affects:** Many users behind one NAT, or a proxy that does not forward the client IP so everyone counts as one address. SSO at shift start and busy portal forms can get HTTP 429.
- **Why no match:** The break depends on traffic and on the proxy in front of the site, and neither is in an app's code.
- **Check by hand:** Confirm the proxy sets `X-Forwarded-For` to the real client IP, since frappe reads its first address. No site setting changes these limits.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/integrations/oauth2_logins.py#L11-L12), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/integrations/oauth2_logins.py#L12-L14), [develop client IP](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/auth.py#L81-L82)

### Assignment endpoints refuse Website Users and disabled users

`assign-to-endpoint-rejects-website-users`

- **What changes:** Over HTTP, `frappe.desk.form.assign_to.add` and `add_multiple` throw "is not an enabled System User" for a disabled user or a Website User. `add_multiple` also refuses a caller whose `bulk_actions` is off.
- **Who it affects:** Client code or an integration that assigns documents to portal users or deactivated users, or runs bulk assignment as a user without bulk actions.
- **Why no match:** The assignee and the caller's settings are data at run time, and most calls to these endpoints name a valid user.
- **Check by hand:** Review the screens that call these endpoints and confirm each assignee is an enabled desk user. A Python call to `assign_to.add` outside the endpoint is not checked.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/desk/form/assign_to.py#L88-L89), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/desk/form/assign_to.py#L93-L98), [develop `add_multiple`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/desk/form/assign_to.py#L173-L175)

### Attach Image fields refuse other file types on upload

`attach-image-upload-rejects-non-images`

- **What changes:** When `upload_file` receives a doctype and fieldname for an Attach Image field and the file name maps to a type that is not an image, it raises `FileTypeNotAllowed`.
- **Who it affects:** An integration or client that stores a PDF or other document in an Attach Image field through the API.
- **Why no match:** The file type is known only when the request arrives.
- **Check by hand:** Look for uploads that target Attach Image fields with other file types, and use an Attach field for those.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/handler.py#L131-L132), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/handler.py#L231-L237)

### Password reset finds the user by email only

`reset-password-matches-email-only`

- **What changes:** `reset_password` now resolves its argument as an email, where v16 loaded the User by ID. An ID that is not also the user's email gets the usual success message and no email is sent.
- **Who it affects:** A caller passing `User.name` for a user whose ID and email differ. A normal save keeps the two equal, so such a row comes from a direct database write.
- **Why no match:** The scan cannot tell whether the value passed is an ID or an email, or which User rows differ.
- **Check by hand:** List User rows where `name` differs from `email`, leaving out Administrator and Guest. For those users, pass the email.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/core/doctype/user/user.py#L1335), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/core/doctype/user/user.py#L1482-L1483)

## Scripts

### Reading installed apps no longer logs in as Administrator

`get-installed-apps-no-longer-sets-administrator`

- **What changes:** With no database connection open, `get_installed_apps` used to connect as Administrator. It now connects as the current user, which is Guest after `frappe.init`.
- **Who it affects:** A script that calls `frappe.init(site)`, then something that reads installed apps, such as `frappe.get_installed_apps` or `frappe.get_hooks` on an empty cache, then writes without calling `frappe.connect()`. The write now raises `PermissionError`.
- **Why no match:** The break is an order of calls that can span helpers and modules, and no match type follows it.
- **Check by hand:** Review scripts that call `frappe.init`, and call `frappe.connect()` right after it.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/__init__.py#L939-L940), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/apps.py#L187-L188)

## Server validation

### Standard Number Cards cannot be saved outside developer mode

`standard-number-card-save-blocked`

- **What changes:** `NumberCard.validate` throws "Cannot edit Standard Number Cards" when `is_standard` is set and `developer_mode` is off. Report cards must also set `report_function`, aggregate fields must be numeric, and Single doctypes are refused.
- **Who it affects:** A patch, fixture or script that inserts or saves a standard card. Module JSON sync skips `validate`, so cards shipped that way keep working.
- **Why no match:** `is_standard` is a value on the record, and code that names Number Card mostly does not save a standard one.
- **Check by hand:** Review patches and fixtures that touch standard cards. Ship them through the module JSON, or use `frappe.db.set_value` in a patch.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/desk/doctype/number_card/number_card.py#L60-L61), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/desk/doctype/number_card/number_card.py#L63-L65)

### Rules the form enforced now run on the server

`form-only-validations-now-on-server`

- **What changes:** The server now refuses values once stopped only in the form, on Assignment Rule, Calendar View, Connected App, Dashboard Chart, Email Account, Email Template, Form Tour, Geolocation Settings, Google Settings, Kanban Board, LDAP Settings, Navbar Settings, Onboarding Step, Portal Settings, Print Format, User Type, Workflow, Workflow Transition Tasks and Workspace. Empty comments, Discussion Replies and contact page messages are refused too.
- **Who it affects:** Code that inserts these records, existing records on their next save, and fixtures, where one failure aborts `bench migrate`. Module JSON sync skips `validate`.
- **Why no match:** Each check depends on the values a record holds when it is saved.
- **Check by hand:** Save each such record, fixture and patch on a v17 test site, and fill in what the error names.
- **Reference:** [v16 Workflow](https://github.com/frappe/frappe/blob/v16.60.2/frappe/workflow/doctype/workflow/workflow.py#L36-L37), [develop Workflow](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/workflow/doctype/workflow/workflow.py#L61-L62), [develop import flags](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/modules/import_file.py#L246-L249)

### Tree doctypes refuse a parent that is not a group

`nestedset-rejects-leaf-parent`

- **What changes:** On a doctype with `is_group`, inserting a node or moving it under a node with `is_group = 0` throws "must be a group node". Merging a node into its own descendant raises `NestedSetInvalidMergeError`.
- **Who it affects:** Code that builds or moves trees without checking the parent, such as imports and syncs from another system. The check also runs during fixture and module imports.
- **Why no match:** The parent's `is_group` is a value in the database.
- **Check by hand:** Review code that sets a tree's parent field. Save the parent with `is_group` set first, or pick a group parent.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/utils/nestedset.py#L278-L281), [develop `_validate`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/utils/nestedset.py#L291-L293), [develop check](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/utils/nestedset.py#L314-L318)

### An explicit name that collides on a hash doctype now raises

`hash-doctype-explicit-name-collision-raises`

- **What changes:** On a doctype with `autoname = hash`, a collision is retried only when frappe generated the name. A name set by code now raises `DuplicateEntryError`, or inserts nothing with `ignore_if_duplicate=True`, where v16 picked a new random name and inserted the row.
- **Who it affects:** Code that sets `doc.name` itself on a hash doctype, such as an import reusing IDs from another system, when the name already exists.
- **Why no match:** A collision happens only at run time, against the rows already on the site.
- **Check by hand:** Find code that sets `name` before inserting on hash doctypes. Leave it unset for a generated name, or handle `frappe.DuplicateEntryError`.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/model/document.py#L2820-L2822), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/model/document.py#L3396-L3398), [develop naming](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/model/naming.py#L198-L200)

## Permissions

### List queries check child table fields against the parent

`query-enforces-child-field-permissions`

- **What changes:** `frappe.get_list` now checks a child table field named in backticks against the parent's permissions in functions, filters, `order_by` and `group_by`, as in ``SUM(`tabSales Invoice Item`.`amount`)``. A user with only select access on the parent, or without the field's permlevel, gets `PermissionError` where v16 skipped the check.
- **Who it affects:** Reports, dashboards and list methods that use `frappe.get_list` this way for restricted users. `frappe.get_all` is not affected.
- **Why no match:** The break depends on the roles of the user running the query.
- **Check by hand:** Run these queries as a restricted user. Grant read and the permlevel, or use `frappe.get_all` after an explicit access check.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/database/query.py#L1031-L1033), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/database/query.py#L1140-L1145)

### Reportview drops `ignore_user_permissions` from the request

`reportview-drops-ignore-user-permissions`

- **What changes:** `frappe.desk.reportview` now deletes `ignore_user_permissions` from a request, with no error. A client that sent it to list past the user's User Permissions now gets only the rows those permissions allow.
- **Who it affects:** Client code that passes this argument to `frappe.desk.reportview.get`, `get_list` or `get_count`.
- **Why no match:** The same name is a DocField property and a link search argument, and `pattern` reads one line at a time, so it cannot tell a reportview argument from those.
- **Check by hand:** Search client code for `ignore_user_permissions` in reportview calls. Move that query to a whitelisted server method that checks access itself and calls `frappe.get_list`.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/desk/reportview.py#L24), [v16 query argument](https://github.com/frappe/frappe/blob/v16.60.2/frappe/model/qb_query.py#L59), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/desk/reportview.py#L26-L35)

### ERPNext Employee link search keeps owner and query conditions

`erpnext-employee-query-role-check`

- **What changes:** On a link field with `ignore_user_permissions`, v16 dropped every match condition for a user with Employee read or select. Develop drops only User Permissions, so `if_owner` and `permission_query_conditions` now apply, including a new ERPNext hook that limits a user with only the Employee role to their own record and reportees.
- **Who it affects:** Users picking an Employee in such a field, including HRMS forms, who now see fewer options with no error.
- **Why no match:** The result depends on each user's roles and on the hooks installed, and the query name says nothing about either.
- **Check by hand:** As a user with only the Employee role, open each form that uses `employee_query` and confirm the options it needs. Grant a role with Employee read where it needs more.
- **Reference:** [v16](https://github.com/frappe/erpnext/blob/v16.60.0/erpnext/controllers/queries.py#L44-L51), [develop](https://github.com/frappe/erpnext/blob/feefe15ca5b57c2601d57a673720f4196bd9ec2e/erpnext/controllers/queries.py#L51-L67), [develop hook](https://github.com/frappe/erpnext/blob/feefe15ca5b57c2601d57a673720f4196bd9ec2e/erpnext/setup/doctype/employee/employee.py#L548-L561)

## Desk forms

### Form refresh and `depends_on` wait for the next animation frame

`form-refresh-deferred-to-animation-frame`

- **What changes:** `frm.refresh_fields()` now schedules its redraw, and `frm.refresh_field()` and value changes schedule `depends_on` and section visibility, through `requestAnimationFrame`. Code that reads the DOM or a control's state right after these calls sees the old state.
- **Who it affects:** Form scripts that read visibility or change the DOM straight after a refresh. The DOM change can be overwritten when the frame runs, and frames do not fire in a background tab.
- **Why no match:** These calls are everywhere and mostly harmless. What breaks is the code that runs next and relies on the redraw.
- **Check by hand:** Review handlers that touch the DOM after a refresh. Do that work in a `requestAnimationFrame` callback, or set it through docfield properties.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/public/js/frappe/form/form.js#L784-L794), [develop `refresh_fields`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/public/js/frappe/form/form.js#L905-L911), [develop `depends_on`](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/public/js/frappe/form/layout.js#L428-L435)

### Toggle helpers skip the redraw when nothing changed

`form-toggle-helpers-skip-unchanged-refresh`

- **What changes:** `frm.toggle_display`, `frm.toggle_enable` and `frm.toggle_reqd` now refresh the field only when the call changed a docfield property.
- **Who it affects:** Code that writes `frm.doc.x` directly and relies on a following toggle to redraw. The field keeps showing the old value, with no error.
- **Why no match:** Whether a toggle changes a property depends on the form's state when it runs.
- **Check by hand:** Look for direct writes to `frm.doc` followed by a toggle. Use `frm.set_value`, or call `frm.refresh_field("x")`.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/public/js/frappe/form/form.js#L1960-L1963), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/public/js/frappe/form/form.js#L2110-L2116)

### User link columns no longer read the row's `full_name`

`user-link-formatter-ignores-row-full-name`

- **What changes:** The User link formatter used `doc.full_name` for any User link in a row. It now reads only `<fieldname>_full_name`.
- **Who it affects:** A report or list that selects `full_name` beside a User link. That column now shows the user ID, with no error.
- **Why no match:** The query that returns the row and the formatter that draws it are in different places, and no match connects them.
- **Check by hand:** Look at report and list columns that link to User, and return the name as `<fieldname>_full_name`, such as `owner_full_name`. This also works on v16.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/public/js/frappe/form/formatters.js#L480-L483), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/public/js/frappe/form/formatters.js#L482-L485)

## Build

### `bench build` uses pnpm when an app has a pnpm lockfile

`build-uses-pnpm-when-lockfile-present`

- **What changes:** An app with `scripts.build` in `package.json` and `pnpm-lock.yaml` at its root now runs `pnpm install --frozen-lockfile` and `pnpm build` in place of yarn.
- **Who it affects:** A bench without pnpm, where the build fails, and an app that keeps a stale pnpm lockfile beside `yarn.lock`, where the frozen install fails.
- **Why no match:** No match type reads a lockfile at the app's root. The file globs of `missing_hook` start inside the package folder that holds `hooks.py`.
- **Check by hand:** Look for `pnpm-lock.yaml` in each app's root. Install pnpm on the bench and keep the lockfile current, or delete it from a yarn app.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/esbuild/esbuild.js#L554-L558), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/esbuild/esbuild.js#L739-L748)

## Postgres only

### Every transaction now runs at REPEATABLE READ

`postgres-every-transaction-repeatable-read`

- **What changes:** On v16 the driver's isolation setting covers a connection's first transaction, and frappe's later `START TRANSACTION` takes the server default, normally READ COMMITTED. Develop sets REPEATABLE READ as the session default, so every transaction uses it.
- **Who it affects:** Postgres sites. After the first commit, a re-read inside a transaction no longer sees other connections' commits, and updating a row changed since the snapshot fails with a serialization error that frappe treats as a deadlock.
- **Why no match:** The break depends on what other connections do at the same moment.
- **Check by hand:** Review long jobs that re-read shared rows or update contended ones. Commit before re-reading, lock with `for_update`, and make the write safe to retry.
- **Reference:** [v16 connection](https://github.com/frappe/frappe/blob/v16.60.2/frappe/database/postgres/database.py#L196), [v16 commit](https://github.com/frappe/frappe/blob/v16.60.2/frappe/database/database.py#L1243-L1244), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/database/postgres/database.py#L384-L388)

### `frappe.db.escape` returns a different literal for backslashes

`postgres-escape-output-changed`

- **What changes:** On Postgres, a string with a backslash now comes back as `` E'...'`` with a leading space and an `E` prefix. The stored value keeps one backslash, where v16 stored two.
- **Who it affects:** Postgres code that slices the result, such as `frappe.db.escape(x)[1:-1]`, which now gets a wrong string. Data written with the old doubling stays doubled.
- **Why no match:** Only values holding a backslash differ, and no match type reports a slice of a call's result.
- **Check by hand:** Search for slices of `frappe.db.escape`, and pass values as query parameters instead. Review stored values that contain doubled backslashes.
- **Reference:** [v16](https://github.com/frappe/frappe/blob/v16.60.2/frappe/database/postgres/database.py#L235), [develop](https://github.com/frappe/frappe/blob/2746cacf9115bec32a06a894d9f69c92457667c0/frappe/database/postgres/database.py#L439)
