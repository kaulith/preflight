# Rules

A rule is one YAML file that describes one breaking change. `--target` picks the set of rules to run.

| Target | For | Rules |
|---|---|---|
| `v16` | A v15 site going to v16 | 152: 88 for frappe and the bench, 64 for ERPNext |

Every v16 rule was checked against v16 source code or a merged pull request, or, for a change that comes with the new Python or a package v16 installs, against that project's source or release notes. They were last checked on 22 November 2026, against frappe v16.60.2 and ERPNext v16.60.0, and the report header says so. Each rule links to its proof.

Each rule also says when its fix can go in: before the upgrade, because the replacement already works on v15, or with the upgrade, because it only exists on v16. Some add a shim that runs on both. See [The fix](reading-a-report.md#the-fix).

## v16: moved out of the framework

Newsletter, Blog, Energy points and Offsite backups are separate apps now. Transaction Log and Changelog Feed are gone. Code that imports them fails, and so does anything that reads their doctypes.

- Newsletter (error):
  - `v16-removed-newsletter`
  - `v16-removed-newsletter-doctypes`
- Blog (error):
  - `v16-removed-blog`
  - `v16-removed-blog-doctypes`
- Energy points (error):
  - `v16-removed-energy-points`
  - `v16-removed-energy-point-doctypes`
  - `v16-removed-energy-points-js`
- Offsite backups (error):
  - `v16-removed-backup-integrations`
  - `v16-removed-backup-doctypes`
- Transaction Log (error):
  - `v16-removed-transaction-log`
  - `v16-removed-transaction-log-doctypes`
- Changelog Feed, with the What's New panel (v16.50.0) (error):
  - `v16-removed-changelog-feed`
  - `v16-removed-changelog-feed-doctypes`
  - `v16-removed-changelog-feed-hook`
  - `v16-removed-changelog-feed-js`

The data stays on the site. The tables survive the upgrade, so raw SQL still works, but reading through the ORM raises: a query raises `DoesNotExistError`, and `frappe.get_doc` raises `ImportError` ("Module import failed").

The Changelog Feed hook rule reports the `get_changelog_feed` hook, which nothing reads any more. The JS rule reports `frappe.boot.changelog_feed`, `frappe.boot.marketplace_apps` and `frappe.search.utils.get_marketplace_apps`, which went with the What's New panel and the Marketplace results in the awesome bar.

## v16: removed

- `v16-removed-test-runner-helpers` (error): The functions that ran a suite from `frappe.test_runner`, such as `run_all_tests` and `run_tests_for_doctype`. Run the tests with `bench run-tests`
- `v16-removed-list-sidebar` (error): `frappe.views.ListSidebar`
- `v16-removed-leaderboards-hook` (error): The `leaderboards` hook
- `v16-removed-marketing-campaign` (error): The Marketing Campaign doctype, replaced by UTM Campaign. The upgrade leaves its records in the old table and UTM Campaign empty
- `v16-removed-filter-methods` (error): Eight methods of `frappe.ui.Filter` and `frappe.ui.FilterGroup`, such as `init_filter_popover`
- `v16-removed-query-report-print-methods` (error): The report's `get_custom_format`, `get_print_template` and `add_portrait_warning`
- `v16-removed-grid-setup-download` (error): The child table grid's `setup_download`
- `v16-web-form-progress-dots` (error): A Web Form's `render_progress_dots`, replaced by a stepper
- `v16-unlock-document-args` (error): The `args` parameter of `unlock_document`
- `v16-moved-frappe-config-helpers` (error): The helpers in `frappe.config`. They moved to `frappe.utils.modules`
- `v16-moved-desk-permission-helpers` (error): `get_allowed_pages`, `get_allowed_reports`, `get_allowed_report_names` and `get_user_pages_or_reports` in `frappe.boot`. They moved to `DeskViews` in `frappe.desk.desk_views`
- `v16-removed-workspace-sidebar-items` (error): The `frappe.desk.desktop.get_workspace_sidebar_items` endpoint. Read `frappe.boot.workspaces` in the browser instead
- `v16-removed-workspace-sidebar-items-import` (error): `get_workspace_sidebar_items` in `frappe.desk.desktop`. It is `get_workspaces` now
- `v16-removed-user-get-roles` (error): The `frappe.core.doctype.user.user.get_roles` endpoint
- `v16-removed-user-get-roles-import` (error): `get_roles` in the User controller. Use `frappe.get_roles(user)`
- `v16-removed-get-excel-date-format` (error): `frappe.utils.xlsxutils.get_excel_date_format`
- `v16-make-xlsx-workbook` (error): An openpyxl workbook passed to `make_xlsx`. It takes an xlsxwriter workbook now
- `v16-build-xlsx-data-returns-three` (error): `build_xlsx_data` returning two values. It returns three from v16.0.0, so unpacking the result into two names raises `ValueError`. Take the first two with `[:2]`
- `v16-sql-function-string-fields` (error): A SQL function or expression written as a string in the fields of a query, such as `"sum(qty) as qty"` in `frappe.get_all`. Pass `{"SUM": "qty", "as": "qty"}`, or build the query with `frappe.qb`
- `v16-has-permission-raise-exception` (error): The `raise_exception` argument of `has_permission`
- `v16-override-doctype-class-subclass` (error): An `override_doctype_class` class that does not subclass the original controller
- `v16-server-script-private-request` (error): Server Script requests to a private address. From v16.50.0 `frappe.make_get_request` and the other `make_*_request` helpers refuse loopback, private-range and link-local hosts. Only a literal `localhost` or IP address in the URL is judged
- `v16-removed-octicons-import` (error): frappe's Octicons stylesheet in `frappe/public/css/octicons/`. v16.50.0 deleted it, so a stylesheet that imports it fails `bench build`
- `v16-removed-python-stdlib` (error): Standard library modules and names that Python 3.12 to 3.14 removed, such as `distutils`, `imp`, `cgi` and `ast.Str`. v16 needs Python 3.14
- `v16-removed-pkg-resources` (error): `pkg_resources`. A new Python 3.14 environment has no setuptools, or one too new to ship it
- `v16-desktop-icon-fields` (warning): Eleven fields of the v15 Desktop Icon, such as `module_name` and `blocked`. The upgrade empties the table
- `v16-notification-title-message` (warning): Notification's `notification_title` and `notification_message`. The in-app alert takes its title from the Subject
- `v16-removed-rq-connection-helpers` (error): rq's `Connection` and the connection helpers next to it. v16 installs rq 2

## v16: packages frappe no longer installs

frappe v15 installs these packages itself, so an app can import them without declaring them. v16 dropped them. A new v16 environment, like the one Frappe Cloud builds or the one bench builds on Python 3.14, does not have them, and the import raises `ModuleNotFoundError`. An environment upgraded in place keeps them until it is rebuilt.

Each rule covers one import, and reports it only when the app declares none of the packages that install it, in its `pyproject.toml` or `requirements.txt`. Declaring `boto3` covers `import botocore` too, since boto3 requires it; declaring only `botocore` leaves `import boto3` reported. The fix is to declare it, in a range that takes in the version v15 pins, so the app installs on both.

The three boto packages are warnings: since v16.60.0 they are back in a new environment only because `litellm`, which frappe now pins, requires `boto3>=1.43.1,<2`. The import works until a later litellm drops it, and a declared range has to reach that version too, such as `boto3>=1.34.143,<2`.

- `v16-removed-bleach` (error): `bleach`
- `v16-removed-boto3` (warning): `boto3`
- `v16-removed-botocore` (warning): `botocore`, which `boto3` also installs
- `v16-removed-s3transfer` (warning): `s3transfer`, which `boto3` also installs
- `v16-removed-dropbox` (error): `dropbox`, the Dropbox SDK
- `v16-removed-geolite2` (error): `maxminddb-geolite2`, imported as `geolite2`
- `v16-removed-maxminddb` (error): `maxminddb`, which `maxminddb-geolite2` also installs
- `v16-removed-cairocffi` (error): `cairocffi`
- `v16-removed-posthog` (error): `posthog`

## v16: behaves differently

Nothing raises here. The code runs and gives a different result.

- `v16-has-permission-hook-returns-none` (error): The function a `has_permission` hook names can return None. v15 read None as no opinion; v16 reads it as deny
- `v16-has-permission-hook-unreadable` (warning): The function a `has_permission` hook names is not in the app's own source, so Preflight can't tell whether it returns None. Check it by hand
- `v16-value-cache-nested` (warning): `frappe.db.value_cache` is nested. The old flat key reads nothing
- `v16-delete-session-stored-id` (warning): `delete_session` with a positional sid. A stored id gets hashed again, so the session is not deleted and the user stays logged in
- `v16-session-id-stored-hashed` (warning): SQL reading `sid` on `tabSessions`. The column now holds a hash, so comparing it with `frappe.session.sid` matches no row
- `v16-filter-hidden-argument` (warning): The fifth argument of `add_filter`. The filter still applies but no longer hides its tag
- `v16-deprecated-gravatar-helpers` (warning): The gravatar helpers return an identicon or an empty string. v15.112.0 already does the same, so only a site on an older v15 sees the change
- `v16-removed-octicons` (warning): The Octicons icon font is gone. An `octicon` class still renders, with a blank icon
- `v16-build-xlsx-data-applied-filters` (warning): With `include_filters`, `build_xlsx_data` reads the filter rows from `data.applied_filters` (v16.17.0). Code that fills only `data.filters` gets a sheet without them
- `v16-sanitize-html-strips-tags` (info): Forbidden tags are removed instead of escaped
- `v16-custom-workspace-navigation` (warning): A public workspace made in the v15 desk has no module. v16 moves it into a module no app holds, so no page of the desk's navigation lists it; it still opens by its URL and from search. Read from the site's records
- `v16-private-workspace-my-space` (warning): v16 lists a user's private workspaces only under My Space in the user menu, and the Show My Space setting that shows it is off for every user. Read from the site's records
- `v16-custom-module-workspace-dock` (warning): A public workspace in a custom module is on no app's rail, since a rail lists only the Dock record its app ships; Manage Dock adds the module. Read from the site's records
- `v16-app-workspaces-apps-screen` (warning): An app that ships workspaces but declares no `add_to_apps_screen` gets no tile on the Apps screen, so no page of the desk's navigation reaches them

## v16: deprecated

These still work on v16 and are marked for removal in v17.

- `v16-deprecated-client-get-js` (warning): `frappe.client.get_js`
- `v16-deprecated-country-info-get-translated-dict` (warning): `country_info.get_translated_dict`
- `v16-deprecated-email-queue-send-mail` (warning): `email_queue.send_mail`
- `v16-deprecated-get-number-format-info` (warning): `get_number_format_info`
- `v16-deprecated-gzip-helpers` (warning): The gzip helpers in `frappe.utils`
- `v16-deprecated-make-esc` (warning): `frappe.utils.make_esc`
- `v16-deprecated-read-multi-pdf` (warning): `read_multi_pdf`
- `v16-deprecated-show-progress` (warning): `show_progress` in bulk update
- `v16-renamed-is-column-missing` (warning): `frappe.db.is_column_missing`
- `v16-deprecated-frappe-test-case` (warning): `FrappeTestCase`
- `v16-deprecated-get-test-records` (warning): `frappe.get_test_records`
- `v16-deprecated-test-runner` (warning): The helpers `frappe.test_runner` still re-exports, such as `make_test_records`. Import them from `frappe.tests.utils`
- `v16-deprecated-tests-utils-helpers` (warning): The helpers on `frappe.tests.utils`
- `v16-deprecated-tests-system-settings` (warning): The system settings test helpers

The last five show up almost only in test files. `--skip-tests` hides them.

## v16: ERPNext

ERPNext v16 removed or renamed doctypes, fields, modules, methods and a hook that apps built on it use. These rules report that code, and the customisations on the site that point at them.

- `v16-erpnext-advance-payment-doctypes-hook` (error): The `advance_payment_doctypes` hook. ERPNext reads `advance_payment_receivable_doctypes` and `advance_payment_payable_doctypes` instead. Nothing raises: the doctypes stop taking advance payments
- Closing Stock Balance, replaced by Stock Closing Entry (error):
  - `v16-erpnext-closing-stock-balance`
  - `v16-erpnext-closing-stock-balance-doctype`
- The Homepage settings, their sections and the `/home` page template. Build the home page as a Web Page (error):
  - `v16-erpnext-homepage`
  - `v16-erpnext-homepage-doctypes`
- `v16-erpnext-lead-source-doctype` (error): Lead Source, copied into the framework's UTM Source
- Repost Accounting Ledger Settings, merged into Accounts Settings (error):
  - `v16-erpnext-repost-settings`
  - `v16-erpnext-repost-settings-doctype`
- BOM Scrap Item and Job Card Scrap Item, now secondary items, and `get_scrap_items_from_sub_assemblies` (error):
  - `v16-erpnext-scrap-items`
  - `v16-erpnext-scrap-item-doctypes`
- Advance Tax, Tax Withheld Vouchers and the TDS and TCS functions of Tax Withholding Category, replaced by Tax Withholding Entry (error):
  - `v16-erpnext-tax-withholding`
  - `v16-erpnext-tax-withholding-doctypes`
- `v16-erpnext-replaced-reports` (error): Employee Billing Summary, Project Billing Summary, BOM Stock Report, BOM Stock Calculated and Supplier-Wise Sales Analytics, replaced by new reports
- `v16-erpnext-moved-settings` (error): The frozen accounts settings and the default manufacturing warehouses, moved to Company, and `post_change_gl_entries`, moved to POS Settings
- `v16-erpnext-scrap-items-tables` (error): The `scrap_items` table of BOM and Job Card, replaced by `secondary_items`
- `v16-erpnext-budget-accounts-table` (error): Budget's `accounts` table. A Budget now covers one account
- `v16-erpnext-tax-withholding-tables` (error): Purchase Invoice's `advance_tax` and `tax_withheld_vouchers`, replaced by `tax_withholding_entries`
- `v16-erpnext-payment-balance-settings` (error): Accounts Settings' `show_account_balance` and `show_party_balance`
- `v16-erpnext-removed-methods` (error): Payment Entry's `get_party_and_account_balance`, Bank Account's `make_bank_account` and Pricing Rule's `make_pricing_rule`, removed with nothing in their place
- `v16-erpnext-make-pricing-rule-js` (error): The form helper `erpnext.utils.make_pricing_rule`. `frappe.new_doc("Pricing Rule", ...)` works on both versions
- `v16-erpnext-pos-closing-invoices` (error): POS Closing Entry's `get_pos_invoices`, replaced by `get_invoices`
- `v16-erpnext-asset-repair-cost` (error): Asset Repair's `get_repair_cost_for_purchase_invoice`, replaced by `get_unallocated_repair_cost`
- `v16-erpnext-default-supplier-purchase-orders` (error): Sales Order's `make_purchase_order_for_default_supplier` and Material Request's `get_default_supplier_query`
- `v16-erpnext-lead-source` (error): The sales funnel's `get_opp_by_lead_source`, replaced by `get_opp_by_utm_source`
- `v16-erpnext-methods-post-only` (error): A GET to one of seven methods that v15 took by any HTTP method, such as Sales Order's `update_status`
- `v16-erpnext-removed-leaderboard` (error): The `erpnext.startup.leaderboard` module and its whitelisted methods
- `v16-erpnext-removed-lead-phone-lookup` (error): `get_lead_with_phone_number`. `get_leads_with_phone_number` returns a list
- `v16-erpnext-removed-helpers` (error): Eleven helpers v15 has and v16 removed, such as `is_transfer_stock_entry`
- `v16-erpnext-removed-demo-setup` (error): `setup_demo_data` and the setup wizard's `setup_demo`
- `v16-erpnext-demo-transaction-doctypes-hook` (info): The `demo_transaction_doctypes` hook, which nothing reads on v16
- BOM Creator, rebuilt around a part tree (error):
  - `v16-erpnext-bom-creator-item-fields`: BOM Creator Item's `fg_item`, `fg_reference_id` and `parent_row_no`
  - `v16-erpnext-bom-creator-methods`: The module's `get_children` and `get_item_details`
  - `v16-erpnext-bom-configurator-js`: `frappe.ui.BOMConfigurator`
- Calls that pass an argument the function no longer takes, so they raise `TypeError` (error):
  - `v16-erpnext-removed-argument-accumulated-values`: `compute_margin_view_data`
  - `v16-erpnext-removed-argument-args`: `parse_list_filters`, `send_emails`, `get_stock_reco_qty_shift`
  - `v16-erpnext-removed-argument-bom-list`: `get_ancestor_boms`
  - `v16-erpnext-removed-argument-company`: The Negative Batch report's `get_warehouses`
  - `v16-erpnext-removed-argument-demo`: `create_bank_account`
  - `v16-erpnext-removed-argument-fail-count`: `show_job_status`
  - `v16-erpnext-removed-argument-item`: The Item Variant Details report's `get_columns` and `get_data`
  - `v16-erpnext-removed-argument-serial-nos-in-stock`: `update_common_item_properties`
  - `v16-erpnext-removed-argument-so-packed-item`: `update_packed_item_with_pick_list_info`
  - `v16-erpnext-removed-argument-sre`: `get_ssb_bundle_for_voucher`
  - `v16-erpnext-removed-argument-sre-name`: `get_serial_batch_entries_for_voucher`
  - `v16-erpnext-removed-argument-sub-assembly-items`: `get_sub_assembly_items`
- `v16-erpnext-coa-importer-validate-accounts` (error): A browser call to the Chart of Accounts Importer's `validate_accounts`, no longer whitelisted
- `v16-erpnext-depreciation-helpers` (error): Seven helpers in the Asset doctype's `depreciation.py`, renamed or replaced
- The arguments of `make_depreciation_entry`: `asset_depr_schedule_name` is now `depr_schedule_name`, and `credit_and_debit_accounts` and `depreciation_cost_center_and_depreciation_series` are gone (error):
  - `v16-erpnext-depreciation-entry-schedule-name`
  - `v16-erpnext-depreciation-entry-accounts`
  - `v16-erpnext-depreciation-entry-cost-center`
- `v16-erpnext-repost-allowed-types` (warning): Repost Allowed Types rows left unchecked on v15. v16 reads every row as allowed, so those doctypes can be reposted, along with the five the `repost_allowed_doctypes` hook adds. Nothing raises. Read from the site's records
- `v16-erpnext-asset-fields` (warning): Asset, Asset Capitalization and Asset Repair fields, such as `gross_purchase_amount`, now `net_purchase_amount`
- `v16-erpnext-bom-creator-row-settings` (warning): BOM Creator Item's `source_warehouse` and `allow_alternative_item`
- `v16-erpnext-budget-fields` (warning): Budget's `fiscal_year` and `monthly_distribution`. A Budget now covers one account over a range of fiscal years
- `v16-erpnext-inventory-dimension-mandatory` (warning): Inventory Dimension's `mandatory_depends_on`, whose condition the migration does not carry over. Conditions stored on the site are not read
- `v16-erpnext-item-wise-tax-detail` (warning): The `item_wise_tax_detail` JSON on tax rows, replaced by the Item Wise Tax Detail table
- `v16-erpnext-pos-fields` (warning): POS Profile's `disable_grand_total_to_default_mop`, turned around as `set_grand_total_to_default_mop`, and POS Closing Entry's tax `rate` and `pos_transactions` table, now `pos_invoices`
- `v16-erpnext-removed-fields` (warning): Fields removed with nothing in their place, on Company, Customer, Item, Payment Entry, Job Card and Journal Entry
- `v16-erpnext-secondary-items-fields` (warning): The scrap fields of BOM, Stock Entry Detail and Subcontracting Receipt Item, renamed to secondary item fields
- `v16-erpnext-serial-no-creation-document` (warning): Serial No's `purchase_document_no`, now `reference_name`
- `v16-erpnext-subcontracted-quantity` (warning): Purchase Order Item's `subcontracted_quantity`, now `subcontracted_qty`
- `v16-erpnext-tax-withholding-fields` (warning): The TDS fields of purchases and payments, such as Purchase Order's `apply_tds`
- `v16-erpnext-utm-fields` (warning): `source` and `campaign` on Lead, Opportunity and the sales documents, replaced by `utm_source` and `utm_campaign`
- `v16-erpnext-workstation-cost-fields` (warning): The four hourly rates of Workstation and Workstation Type, replaced by a `workstation_costs` table

Most field rules are warnings. The migration leaves the old column behind with nothing writing it again, so on an upgraded site `frappe.get_all` and `frappe.db.get_value` return what the field held at the upgrade, while `frappe.get_list` leaves the field out. The errors are where it raises: `frappe.db.get_single_value` on an old field (`v16-erpnext-moved-settings`, `v16-erpnext-payment-balance-settings`), and a removed table read off a document (`v16-erpnext-scrap-items-tables`, `v16-erpnext-budget-accounts-table`, `v16-erpnext-tax-withholding-tables`).

A field rule reports a query that names the doctype and the field in the same call, such as `frappe.get_all("Lead", fields=["source"])`, a Property Setter or Custom Field on the field, and, in Python, the field read or set on a document whose doctype the code shows: one loaded or made in the same function (`frappe.get_doc("Lead", name)`, `frappe.new_doc`, `frappe.get_cached_doc`), the doc a `doc_events` hook hands its function, `self` in a class that `override_doctype_class` names or that is built on the doctype's controller, `doc` in a DocType Event server script, and `doc` in a Notification's condition. `doc.get("source")`, `doc.set` and `doc.db_set` count too. It also follows that document's child rows, reads `frm.doc` and the field methods of `frm` inside `frappe.ui.form.on`, and reads `doc` in Print Format and Notification templates. A document that arrives any other way is missed.

## Bench and app compatibility

These rules check whether the bench can install the target at all, before any scanned code runs. They look at every app on the bench, whether a site has it installed or not. `--app` narrows them to the apps named.

- `v16-bench-python` (error): The bench's Python against v16's `requires-python`, `>=3.14,<3.15`
- `v16-app-requires-python` (error): Each app's `requires-python` in `pyproject.toml`. Reported when it allows no Python v16 runs on
- `v16-app-frappe-bound` (warning): Each app's frappe bound in `[tool.bench.frappe-dependencies]`, against frappe 16.60.2
- `v16-app-dependency-pins` (error): Each app's `[project].dependencies` against frappe v16's own pins. Reported when no version satisfies both
- `v16-app-required-apps` (error): Each app's `required_apps` hook. Reported when a required app is not on the bench
- `v16-bench-node` (error): With `--online`: the node on the bench's PATH against v16's `>=24`
- `v16-app-target-branch` (error): With `--online`: each app on frappe's version branch has a remote named `upstream` with a `version-16` branch
- `v16-app-dependency-wheels` (warning): With `--online`: the newest release of each of an app's dependencies that pip would pick on Python 3.14, read from PyPI. Reported when every release the app allows leaves out 3.14, or when the release has wheels for older Pythons and none for 3.14

The last three run git and node or ask PyPI, so they run only with `--online`. What they cannot reach is listed under [Not checked](reading-a-report.md#not-checked), never read as clean.

The severity is what the install does:

- **Python:** pip refuses to install frappe, or the app, on a Python outside `requires-python`.
- **Frappe bound:** bench only warns that the app "might not work as expected", and installs it anyway. `bench validate-dependencies` fails.
- **Dependency pins:** neither pip nor uv refuses a clash. The later install replaces the earlier version and exits 0, so frappe or the app ends up on a version it does not allow.
- **Required apps:** installing the app stops with "App ... not in apps.txt".
- **Node:** yarn refuses a package whose engines leave out the running node, so `bench switch-to-branch --upgrade` stops before anything is migrated or built.
- **Target branch:** bench reads each app's version off `upstream/version-16`. An app without it stops the switch partway: the apps before it are already on version-16, the rest are not.
- **Wheels:** pip and uv build the dependency from source, which needs a compiler and the library's headers on the server, and the install fails where they are missing.

An app's `pyproject.toml` is read only when the upgrade leaves the app on its branch, such as a custom app on `main`. An app on a frappe version branch is switched to the target's branch, which brings its own `pyproject.toml`. An app with no branch checked out, or that is not a git checkout, is listed under [Not checked](reading-a-report.md#not-checked). With `--path`, each `pyproject.toml` is read whatever branch the app is on.

## Not covered

| Change | Why there is no rule |
|---|---|
| Lists sort by `creation` instead of `modified` | `frappe.get_all` and `frappe.get_list` follow each doctype's `sort_field`, which v16 moved to `creation` on most frappe and ERPNext doctypes; an app's own doctypes keep what their JSON says. `frappe.db.get_value` with filters falls back from `modified` to `creation` on every doctype. A rule would flag thousands of correct calls |
| `User.validate_roles` | It is a method on a document. The scanner can't tell what a variable holds |
| `frappe.deprecations.deprecation_warning` | The module is already gone on v15 |
| `frappe.model.trace.traced_field_context` | A debugging helper that no app we scanned uses |
| `modules.txt` | It is a file, not an API |
| rq `use_connection` | Already gone in rq 1.15.1, which v15 installs |
| A removed ERPNext field read off a document passed in from elsewhere | Nothing there says which doctype the document is |
| Sales Order's `make_purchase_order` returns a list of Purchase Orders | `po = make_purchase_order(...)` reads the same on v15 and v16, and ERPNext v16's own code calls it that way |
| Payment Entry's `get_account_details` no longer returns `account_balance` | A key of the returned dict; nothing ties the read to the call. The balance fields are under `v16-erpnext-removed-fields` |
| A Sales Order's `make_sales_invoice` no longer skips permissions on the invoice unless asked | A correct call and a failing one differ only in who runs it |
| About 40 ERPNext functions, such as `warehouse_query`, check permissions on v16 and not on v15 | Whether a call fails depends on the user running it |
| `communication.email.make` with no reference document needs create on Communication | Depends on the user running it |
| Ten more ERPNext functions, such as `filter_batches`, take new arguments | A rule can match an argument a call passes, not one it leaves out |
| Nine ERPNext controller methods removed, such as `Project.get_billed_amount_from_parent` | They are reached through `self` or `super()`, and the scanner can't tell what class a variable holds |
| ERPNext's `update_compnay_address` is now `update_company_address` | An override of the old name stops being called, and nothing in the override names the class it replaces |
| `get_item_details` refuses `BOM Creator` as its doctype | The doctype is usually a variable |
| Holiday List's `total_holidays` is a float, with half days as 0.5 | The field still reads; only code that assumes a whole number is affected |
| Asset Capitalization's `target_asset` is required | A validation on save that depends on the record |
| An Inventory Dimension condition gets plain field values, so `doc.is_new()` raises | A site record rule compares a field with one value and can't read a condition's text |
| Data Import export for an owner-only user keeps that user's rows instead of raising | No app code is involved |
| A Print Format with no PDF generator follows a `chrome` value stored in Print Settings | An upgraded site with nothing stored keeps wkhtmltopdf |
| `frappe.query_report.chart` is a reduced handle when classic charts are off | The upgrade keeps a site that finished setup on classic charts |
| A Link field's awesomplete is a shim under the Beta combobox setting | The setting is off by default |
| `SortSelector` lost `bind_events`, its template and its dropdown markup | The names are too generic to match without flagging other code |
| The bulk edit grid no longer sets `frappe.flags.no_socketio` | frappe reads the flag on neither version |
| Leaflet moved out of `libs.bundle.js` into a bundle only MapView and Geolocation load | Its global `L` is too short to match |
| Five-element rows passed to `add_filters` no longer hide the filter | The rows are usually built elsewhere. A direct `add_filter` call is covered |
| A multi-step Web Form's `.slide-step` and `.slides-progress` markup is gone, and a Page Break in the first row names page 1 | The setup wizard's slides still use those classes |
| The upgrade steps | Not an API. See the [upgrade checklist](upgrade-checklist.md) |

To add a rule, see [Writing a rule](writing-a-rule.md).
