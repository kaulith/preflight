# Rules

A rule is one YAML file that describes one breaking change. `--target` picks the set of rules to run.

| Target | For | Rules |
|---|---|---|
| `v16` | A v15 site going to v16 | 113: 77 for frappe and the bench, 36 for ERPNext |

Every v16 rule was checked against v16 source code or a merged pull request, or, for a change that comes with the new Python or a package v16 installs, against that project's source or release notes. They were last checked on 25 October 2026, against frappe v16.53.0, and the report header says so. Each rule links to its proof.

Each rule also says when its fix can go in: before the upgrade, because the replacement already works on v15, or with the upgrade, because it only exists on v16. Some add a shim that runs on both. See [The fix](reading-a-report.md#the-fix).

## v16: moved out of the framework

Newsletter, Blog, Energy points and Offsite backups are separate apps now. Transaction Log and Changelog Feed are gone. Code that imports them fails, and so does anything that reads their doctypes.

| What moved | Rules | Severity |
|---|---|---|
| Newsletter | `v16-removed-newsletter`, `v16-removed-newsletter-doctypes` | error |
| Blog | `v16-removed-blog`, `v16-removed-blog-doctypes` | error |
| Energy points | `v16-removed-energy-points`, `v16-removed-energy-point-doctypes`, `v16-removed-energy-points-js` | error |
| Offsite backups | `v16-removed-backup-integrations`, `v16-removed-backup-doctypes` | error |
| Transaction Log | `v16-removed-transaction-log`, `v16-removed-transaction-log-doctypes` | error |
| Changelog Feed, with the What's New panel (v16.50.0) | `v16-removed-changelog-feed`, `v16-removed-changelog-feed-doctypes`, `v16-removed-changelog-feed-hook`, `v16-removed-changelog-feed-js` | error |

The data stays on the site. The tables survive the upgrade, so raw SQL still works, but reading through the ORM raises: a query raises `DoesNotExistError`, and `frappe.get_doc` raises `ImportError` ("Module import failed").

The Changelog Feed hook rule reports the `get_changelog_feed` hook, which nothing reads any more. The JS rule reports `frappe.boot.changelog_feed`, `frappe.boot.marketplace_apps` and `frappe.search.utils.get_marketplace_apps`, which went with the What's New panel and the Marketplace results in the awesome bar.

## v16: removed

| Rule | Severity | What is gone |
|---|---|---|
| `v16-removed-test-runner-helpers` | error | The functions that ran a suite from `frappe.test_runner`, such as `run_all_tests` and `run_tests_for_doctype`. Run the tests with `bench run-tests` |
| `v16-removed-list-sidebar` | error | `frappe.views.ListSidebar` |
| `v16-removed-leaderboards-hook` | error | The `leaderboards` hook |
| `v16-moved-frappe-config-helpers` | error | The helpers in `frappe.config`. They moved to `frappe.utils.modules` |
| `v16-moved-desk-permission-helpers` | error | `get_allowed_pages`, `get_allowed_reports`, `get_allowed_report_names` and `get_user_pages_or_reports` in `frappe.boot`. They moved to `DeskViews` in `frappe.desk.desk_views` |
| `v16-removed-workspace-sidebar-items` | error | The `frappe.desk.desktop.get_workspace_sidebar_items` endpoint. Read `frappe.boot.workspaces` in the browser instead |
| `v16-removed-workspace-sidebar-items-import` | error | `get_workspace_sidebar_items` in `frappe.desk.desktop`. It is `get_workspaces` now |
| `v16-removed-user-get-roles` | error | The `frappe.core.doctype.user.user.get_roles` endpoint |
| `v16-removed-user-get-roles-import` | error | `get_roles` in the User controller. Use `frappe.get_roles(user)` |
| `v16-removed-get-excel-date-format` | error | `frappe.utils.xlsxutils.get_excel_date_format` |
| `v16-make-xlsx-workbook` | error | An openpyxl workbook passed to `make_xlsx`. It takes an xlsxwriter workbook now |
| `v16-build-xlsx-data-returns-three` | error | `build_xlsx_data` returning two values. It returns three from v16.0.0, so unpacking the result into two names raises `ValueError`. Take the first two with `[:2]` |
| `v16-sql-function-string-fields` | error | A SQL function or expression written as a string in the fields of a query, such as `"sum(qty) as qty"` in `frappe.get_all`. Pass `{"SUM": "qty", "as": "qty"}`, or build the query with `frappe.qb` |
| `v16-has-permission-raise-exception` | error | The `raise_exception` argument of `has_permission` |
| `v16-override-doctype-class-subclass` | error | An `override_doctype_class` class that does not subclass the original controller |
| `v16-server-script-private-request` | error | Server Script requests to a private address. From v16.50.0 `frappe.make_get_request` and the other `make_*_request` helpers refuse loopback, private-range and link-local hosts. Only a literal `localhost` or IP address in the URL is judged |
| `v16-removed-octicons-import` | error | frappe's Octicons stylesheet in `frappe/public/css/octicons/`. v16.50.0 deleted it, so a stylesheet that imports it fails `bench build` |
| `v16-removed-python-stdlib` | error | Standard library modules and names that Python 3.12 to 3.14 removed, such as `distutils`, `imp`, `cgi` and `ast.Str`. v16 needs Python 3.14 |
| `v16-removed-pkg-resources` | error | `pkg_resources`. A new Python 3.14 environment has no setuptools, or one too new to ship it |
| `v16-removed-rq-connection-helpers` | error | rq's `Connection` and the connection helpers next to it. v16 installs rq 2 |

## v16: packages frappe no longer installs

frappe v15 installs these packages itself, so an app can import them without declaring them. v16 dropped them. A new v16 environment, like the one Frappe Cloud builds or the one bench builds on Python 3.14, does not have them, and the import raises `ModuleNotFoundError`. An environment upgraded in place keeps them until it is rebuilt.

Each rule covers one import, and reports it only when the app declares none of the packages that install it, in its `pyproject.toml` or `requirements.txt`. Declaring `boto3` covers `import botocore` too, since boto3 requires it; declaring only `botocore` leaves `import boto3` reported. The fix is to declare it, in a range that takes in the version v15 pins, so the app installs on both.

| Rule | Severity | Package |
|---|---|---|
| `v16-removed-bleach` | error | `bleach` |
| `v16-removed-boto3` | error | `boto3` |
| `v16-removed-botocore` | error | `botocore`, which `boto3` also installs |
| `v16-removed-s3transfer` | error | `s3transfer`, which `boto3` also installs |
| `v16-removed-dropbox` | error | `dropbox`, the Dropbox SDK |
| `v16-removed-geolite2` | error | `maxminddb-geolite2`, imported as `geolite2` |
| `v16-removed-maxminddb` | error | `maxminddb`, which `maxminddb-geolite2` also installs |
| `v16-removed-cairocffi` | error | `cairocffi` |
| `v16-removed-posthog` | error | `posthog` |

## v16: behaves differently

Nothing raises here. The code runs and gives a different result.

| Rule | Severity | What changed |
|---|---|---|
| `v16-has-permission-hook-returns-none` | error | The function a `has_permission` hook names can return None. v15 read None as no opinion; v16 reads it as deny |
| `v16-has-permission-hook-unreadable` | warning | The function a `has_permission` hook names is not in the app's own source, so Preflight can't tell whether it returns None. Check it by hand |
| `v16-value-cache-nested` | warning | `frappe.db.value_cache` is nested. The old flat key reads nothing |
| `v16-deprecated-gravatar-helpers` | warning | The gravatar helpers return an identicon or an empty string. v15.112.0 already does the same, so only a site on an older v15 sees the change |
| `v16-removed-octicons` | warning | The Octicons icon font is gone. An `octicon` class still renders, with a blank icon |
| `v16-build-xlsx-data-applied-filters` | warning | With `include_filters`, `build_xlsx_data` reads the filter rows from `data.applied_filters` (v16.17.0). Code that fills only `data.filters` gets a sheet without them |
| `v16-sanitize-html-strips-tags` | info | Forbidden tags are removed instead of escaped |
| `v16-custom-workspace-navigation` | warning | A public workspace made in the v15 desk has no module. v16 moves it into a module no app holds, so no page of the desk's navigation lists it; it still opens by its URL and from search. Read from the site's records |
| `v16-private-workspace-my-space` | warning | v16 lists a user's private workspaces only under My Space in the user menu, and the Show My Space setting that shows it is off for every user. Read from the site's records |
| `v16-custom-module-workspace-dock` | warning | A public workspace in a custom module is on no app's rail, since a rail lists only the Dock record its app ships; Manage Dock adds the module. Read from the site's records |
| `v16-app-workspaces-apps-screen` | warning | An app that ships workspaces but declares no `add_to_apps_screen` gets no tile on the Apps screen, so no page of the desk's navigation reaches them |

## v16: deprecated

These still work on v16 and are marked for removal in v17.

| Rule | Severity | What is deprecated |
|---|---|---|
| `v16-deprecated-client-get-js` | warning | `frappe.client.get_js` |
| `v16-deprecated-country-info-get-translated-dict` | warning | `country_info.get_translated_dict` |
| `v16-deprecated-email-queue-send-mail` | warning | `email_queue.send_mail` |
| `v16-deprecated-get-number-format-info` | warning | `get_number_format_info` |
| `v16-deprecated-gzip-helpers` | warning | The gzip helpers in `frappe.utils` |
| `v16-deprecated-make-esc` | warning | `frappe.utils.make_esc` |
| `v16-deprecated-read-multi-pdf` | warning | `read_multi_pdf` |
| `v16-deprecated-show-progress` | warning | `show_progress` in bulk update |
| `v16-renamed-is-column-missing` | warning | `frappe.db.is_column_missing` |
| `v16-deprecated-frappe-test-case` | warning | `FrappeTestCase` |
| `v16-deprecated-get-test-records` | warning | `frappe.get_test_records` |
| `v16-deprecated-test-runner` | warning | The helpers `frappe.test_runner` still re-exports, such as `make_test_records`. Import them from `frappe.tests.utils` |
| `v16-deprecated-tests-utils-helpers` | warning | The helpers on `frappe.tests.utils` |
| `v16-deprecated-tests-system-settings` | warning | The system settings test helpers |

The last five show up almost only in test files. `--skip-tests` hides them.

## v16: ERPNext

ERPNext v16 removed or renamed doctypes, fields, modules, methods and a hook that apps built on it use. These rules report that code, and the customisations on the site that point at them.

| Rules | Severity | What changed |
|---|---|---|
| `v16-erpnext-advance-payment-doctypes-hook` | error | The `advance_payment_doctypes` hook. ERPNext reads `advance_payment_receivable_doctypes` and `advance_payment_payable_doctypes` instead. Nothing raises: the doctypes stop taking advance payments |
| `v16-erpnext-closing-stock-balance`, `v16-erpnext-closing-stock-balance-doctype` | error | Closing Stock Balance, replaced by Stock Closing Entry |
| `v16-erpnext-homepage`, `v16-erpnext-homepage-doctypes` | error | The Homepage settings, their sections and the `/home` page template. Build the home page as a Web Page |
| `v16-erpnext-lead-source-doctype` | error | Lead Source, copied into the framework's UTM Source |
| `v16-erpnext-repost-settings`, `v16-erpnext-repost-settings-doctype` | error | Repost Accounting Ledger Settings, merged into Accounts Settings |
| `v16-erpnext-scrap-items`, `v16-erpnext-scrap-item-doctypes` | error | BOM Scrap Item and Job Card Scrap Item, now secondary items, and `get_scrap_items_from_sub_assemblies` |
| `v16-erpnext-tax-withholding`, `v16-erpnext-tax-withholding-doctypes` | error | Advance Tax, Tax Withheld Vouchers and the TDS and TCS functions of Tax Withholding Category, replaced by Tax Withholding Entry |
| `v16-erpnext-replaced-reports` | error | Employee Billing Summary, Project Billing Summary, BOM Stock Report, BOM Stock Calculated and Supplier-Wise Sales Analytics, replaced by new reports |
| `v16-erpnext-moved-settings` | error | The frozen accounts settings and the default manufacturing warehouses, moved to Company, and `post_change_gl_entries`, moved to POS Settings |
| `v16-erpnext-removed-methods` | error | Payment Entry's `get_party_and_account_balance`, Bank Account's `make_bank_account` and Pricing Rule's `make_pricing_rule`, removed with nothing in their place |
| `v16-erpnext-make-pricing-rule-js` | error | The form helper `erpnext.utils.make_pricing_rule`. `frappe.new_doc("Pricing Rule", ...)` works on both versions |
| `v16-erpnext-pos-closing-invoices` | error | POS Closing Entry's `get_pos_invoices`, replaced by `get_invoices` |
| `v16-erpnext-asset-repair-cost` | error | Asset Repair's `get_repair_cost_for_purchase_invoice`, replaced by `get_unallocated_repair_cost` |
| `v16-erpnext-default-supplier-purchase-orders` | error | Sales Order's `make_purchase_order_for_default_supplier` and Material Request's `get_default_supplier_query` |
| `v16-erpnext-lead-source` | error | The sales funnel's `get_opp_by_lead_source`, replaced by `get_opp_by_utm_source` |
| `v16-erpnext-depreciation-helpers` | error | Seven helpers in the Asset doctype's `depreciation.py`, renamed or replaced |
| `v16-erpnext-depreciation-entry-schedule-name`, `v16-erpnext-depreciation-entry-accounts`, `v16-erpnext-depreciation-entry-cost-center` | error | The arguments of `make_depreciation_entry`: `asset_depr_schedule_name` is now `depr_schedule_name`, and `credit_and_debit_accounts` and `depreciation_cost_center_and_depreciation_series` are gone |
| `v16-erpnext-repost-allowed-types` | warning | Repost Allowed Types rows left unchecked on v15. v16 reads every row as allowed, so those doctypes can be reposted, along with the five the `repost_allowed_doctypes` hook adds. Nothing raises. Read from the site's records |
| `v16-erpnext-asset-fields` | warning | Asset, Asset Capitalization and Asset Repair fields, such as `gross_purchase_amount`, now `net_purchase_amount` |
| `v16-erpnext-budget-fields` | warning | Budget's `fiscal_year` and `monthly_distribution`. A Budget now covers one account over a range of fiscal years |
| `v16-erpnext-item-wise-tax-detail` | warning | The `item_wise_tax_detail` JSON on tax rows, replaced by the Item Wise Tax Detail table |
| `v16-erpnext-pos-fields` | warning | POS Profile's `disable_grand_total_to_default_mop`, turned around as `set_grand_total_to_default_mop`, and POS Closing Entry's tax `rate` and `pos_transactions` table, now `pos_invoices` |
| `v16-erpnext-removed-fields` | warning | Fields removed with nothing in their place, on Company, Customer, Item, Payment Entry, Job Card and Journal Entry |
| `v16-erpnext-secondary-items-fields` | warning | The scrap fields of BOM, Stock Entry Detail and Subcontracting Receipt Item, renamed to secondary item fields |
| `v16-erpnext-serial-no-creation-document` | warning | Serial No's `purchase_document_no`, now `reference_name` |
| `v16-erpnext-subcontracted-quantity` | warning | Purchase Order Item's `subcontracted_quantity`, now `subcontracted_qty` |
| `v16-erpnext-tax-withholding-fields` | warning | The TDS fields of purchases and payments, such as Purchase Order's `apply_tds` |
| `v16-erpnext-utm-fields` | warning | `source` and `campaign` on Lead, Opportunity and the sales documents, replaced by `utm_source` and `utm_campaign` |
| `v16-erpnext-workstation-cost-fields` | warning | The four hourly rates of Workstation and Workstation Type, replaced by a `workstation_costs` table |

Most field rules are warnings. The migration leaves the old column behind with nothing writing it again, so on an upgraded site `frappe.get_all` and `frappe.db.get_value` return what the field held at the upgrade, while `frappe.get_list` leaves the field out. `v16-erpnext-moved-settings` is an error: `frappe.db.get_single_value` on an old field raises.

A field rule reports a query that names the doctype and the field in the same call, such as `frappe.get_all("Lead", fields=["source"])`, a Property Setter or Custom Field on the field, and, in Python, the field read or set on a document whose doctype the code shows: one loaded or made in the same function (`frappe.get_doc("Lead", name)`, `frappe.new_doc`, `frappe.get_cached_doc`), the doc a `doc_events` hook hands its function, `self` in a class that `override_doctype_class` names or that is built on the doctype's controller, `doc` in a DocType Event server script, and `doc` in a Notification's condition. `doc.get("source")`, `doc.set` and `doc.db_set` count too. A document that arrives any other way, a row of its child table, and `frm.doc` in a form script are missed.

## Bench and app compatibility

These rules check whether the bench can install the target at all, before any scanned code runs. They look at every app on the bench, whether a site has it installed or not. `--app` narrows them to the apps named.

| Rule | Severity | What it checks |
|---|---|---|
| `v16-bench-python` | error | The bench's Python against v16's `requires-python`, `>=3.14,<3.15` |
| `v16-app-requires-python` | error | Each app's `requires-python` in `pyproject.toml`. Reported when it allows no Python v16 runs on |
| `v16-app-frappe-bound` | warning | Each app's frappe bound in `[tool.bench.frappe-dependencies]`, against frappe 16.53.0 |
| `v16-app-dependency-pins` | error | Each app's `[project].dependencies` against frappe v16's own pins. Reported when no version satisfies both |
| `v16-app-required-apps` | error | Each app's `required_apps` hook. Reported when a required app is not on the bench |
| `v16-bench-node` | error | With `--online`: the node on the bench's PATH against v16's `>=24` |
| `v16-app-target-branch` | error | With `--online`: each app on frappe's version branch has a remote named `upstream` with a `version-16` branch |
| `v16-app-dependency-wheels` | warning | With `--online`: the newest release of each of an app's dependencies that pip would pick on Python 3.14, read from PyPI. Reported when every release the app allows leaves out 3.14, or when the release has wheels for older Pythons and none for 3.14 |

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
| Lists sort by `creation` instead of `modified` | It affects every `frappe.get_all` without an `order_by`. A rule would flag thousands of correct calls |
| `User.validate_roles` | It is a method on a document. The scanner can't tell what a variable holds |
| `frappe.deprecations.deprecation_warning` | The module is already gone on v15 |
| `frappe.model.trace.traced_field_context` | A debugging helper that no app we scanned uses |
| `modules.txt` | It is a file, not an API |
| rq `use_connection` | Already gone in rq 1.15.1, which v15 installs |
| A removed ERPNext field read off a document passed in from elsewhere, or off `frm.doc` | Nothing there says which doctype the document is |
| Sales Order's `make_purchase_order` returns a list of Purchase Orders | `po = make_purchase_order(...)` reads the same on v15 and v16, and ERPNext v16's own code calls it that way |
| Payment Entry's `get_account_details` no longer returns `account_balance` | A key of the returned dict; nothing ties the read to the call. The balance fields are under `v16-erpnext-removed-fields` |
| The upgrade steps | Not an API. See the [upgrade checklist](upgrade-checklist.md) |

To add a rule, see [Writing a rule](writing-a-rule.md).
