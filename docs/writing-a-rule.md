# Writing a rule

A rule is one YAML file for one breaking change. Adding a rule never needs a code change.

## Where it goes

- One folder per target, such as `preflight/rules/v16/`.
- The file name is the rule id: `v16-removed-newsletter.yaml`.
- A new folder is a new target when it is named `v` and a major version (`v18`), and holds a `target.yaml` and at least one rule. `--target` offers it once its `target.yaml` says `released: true`.

## target.yaml

Each target folder holds a `target.yaml` beside its rules. The loader reads it for the target and skips it when it loads the rules:

```yaml
released: true            # the frappe major is out
checked: "2026-10-25"     # when the rules were last checked against the source, quoted
against: frappe v16.53.0  # what they were checked against
```

- All three keys are required, and no others are allowed.
- `checked` and `against` are what the report header prints: "Rules checked 2026-10-25 against frappe v16.53.0".
- A target with `released: false` still loads, so its rules are tested with the rest, but `--target` refuses it.

## The file

```yaml
id: v16-removed-newsletter
title: Newsletter moved out of the framework
severity: error
match:
  type: import_path
  paths:
    - frappe.email.doctype.newsletter
message: >
  What breaks, in the words a site owner would use.
replacement: >
  What to do instead.
fix: with-upgrade
references:
  - https://github.com/frappe/frappe/pull/32971
```

| Field | Holds |
|---|---|
| `id` | Same as the file name |
| `title` | One line, shown in the report |
| `severity` | `error` if it breaks, `warning` if it needs a look, `info` if it is only good to know |
| `match` | What to look for. See the match types below |
| `message` | What breaks |
| `replacement` | The fix |
| `fix` | Optional. `before` or `with-upgrade`: when the fix can go in. Every v16 rule has one |
| `shim` | Optional. A snippet that runs on both versions |
| `references` | At least one link that proves the claim |

Check the claim against the framework's source before writing the rule. The deprecation dumpster's own label can be wrong about the name: `frappe.tests_runner` is the label, `frappe.test_runner` the module.

The loader checks every rule when it loads. It rejects a key it does not know, at the top or inside `match`, a single value or an empty list where a list belongs, and an `id` that is not the file name. The error names the file.

## fix and shim

`fix` says when the replacement can go in, and the report prints it as "Fix before upgrading" or "Fix with the upgrade".

- `before`: the replacement already works on the version the site runs now, frappe v15 for `rules/v16`, so the change can ship ahead of the upgrade.
- `with-upgrade`: the replacement only exists on the target, so it goes in with the upgrade, or ahead of it behind a shim.
- Decide it from the source of the version being left: the import path, function, argument or behaviour the replacement names has to exist and work there.
- A fix that is not code takes the value that is true for when the site owner can act. The Newsletter app has no version-15 branch, so installing it is `with-upgrade`; v15 runs on Python 3.14 too, so rebuilding the environment on it is `before`.

`shim` is written as a literal block (`|`) so its tabs survive:

```yaml
fix: with-upgrade
shim: |
  try:
  	from frappe.utils.modules import get_modules_from_app
  except ImportError:
  	from frappe.config import get_modules_from_app
```

A moved import is shimmed this way, which Preflight does not report (see `import_path`). Any other shim goes in only when it is short and checked against the source of both versions.

## Match types

| Type | Finds |
|---|---|
| `import_path` | A Python import or use of a module or function, or its dotted path in a string |
| `call` | A Python call, optionally with a certain argument, or a request to a private host |
| `pattern` | A regular expression in JavaScript or SCSS |
| `string_contains` | A dotted path inside a string, in Python or JavaScript |
| `hook_key` | A hook declared in `hooks.py` |
| `override_subclass` | An `override_doctype_class` class that does not subclass the controller |
| `returns_none` | A hooked function that can return None |
| `unreadable_function` | A hooked function that isn't in the app's own source |
| `missing_hook` | An app that ships certain files but declares none of a hook's names in `hooks.py` |
| `doctype` | A removed doctype, wherever it is named |
| `doctype_field` | A removed or renamed field on a doctype that stays |
| `select_field` | A query field the target rejects, such as a SQL function written as a string |
| `undeclared_import` | An import of a package the target's frappe no longer installs, when the app does not declare it |
| `site_record` | Records on the site, chosen by field values, that the target reads differently |
| `bench_python` | A bench Python outside the target's range |
| `requires_python` | An app's `requires-python` that rules out the target's Python |
| `frappe_bound` | An app's frappe bound that leaves out the target |
| `dependency_pins` | An app's dependency pin that clashes with the target frappe's |
| `required_apps` | An app in `required_apps` that is not on the bench |
| `bench_node` | A node older than the target needs. `--online` only |
| `target_branch` | An app with no upstream branch for the target. `--online` only |
| `dependency_wheels` | An app dependency with no wheel or release for the target's Python. `--online` only |

Python code under an `if` that reads the frappe version (`frappe.__version__`, or a helper such as `is_frappe_version`) is not reported: it picks the code for each version on purpose.

### import_path

```yaml
match:
  type: import_path
  paths:
    - frappe.email.doctype.newsletter
```

- Matches `import`, `from ... import`, and use through an alias.
- Matches anything under the path too.
- Also matches the path given as a string to `frappe.get_attr`, `frappe.get_module`, `frappe.call` and `frappe.enqueue`.
- In `hooks.py`, matches any string that is wholly a dotted path, since Frappe resolves the functions hooks name.
- In JavaScript, matches any string that is wholly a dotted path, such as the `method` of a `frappe.call`. A path inside a longer string is not matched.
- An import under `try` whose `except` names `ImportError` or `ModuleNotFoundError` is skipped. It is written to survive the module being gone.

### call

```yaml
match:
  type: call
  paths:
    - frappe.permissions.has_permission
  with_kwargs:
    - raise_exception
  with_positional_args: 5
```

- With only `paths`, it matches every call.
- `with_kwargs` matches calls that pass these keywords.
- `with_positional_args` matches calls with at least this many positional arguments.
- With both, either one is enough.

```yaml
match:
  type: call
  paths:
    - frappe.make_get_request
  url_host: private
```

- `url_host: private` matches a call whose first argument, or `url` keyword, is a literal URL on `localhost` or on an IP address that is not globally routable: loopback, a private range, link-local.
- An f-string counts when its leading text holds the whole host.
- A hostname is not resolved, so a name that points at a private address is not reported.

```yaml
match:
  type: call
  paths:
    - frappe.desk.query_report.build_xlsx_data
  returns: 3
```

- `returns` is for a function the target makes return more values than before.
- A call whose result is indexed or sliced (`build_xlsx_data(...)[:2]`), unpacked into `returns` names, or unpacked into a starred name and at most `returns` others is not reported.
- Any other use is reported, a result held in one name included, since the name is not followed to where it is read.

### pattern

```yaml
match:
  type: pattern
  patterns:
    - \bfrappe\.views\.ListSidebar\b
```

- Runs on `.js`, `.mjs`, `.ts`, `.jsx`, `.tsx`, `.vue` and `.scss` files and on JavaScript saved on the site, one line at a time.
- Use it for client globals, which have no import to key on, and for stylesheet imports.
- Wrap the name in `\b`, or longer names with the same start match too.
- Comments are skipped, block and trailing ones included. Anything else on the line counts, strings too.

### string_contains

```yaml
match:
  type: string_contains
  paths:
    - frappe.client.get_js
```

- For endpoint names passed as text, such as in `frappe.call`.
- Matches any string that contains the path.
- In JavaScript, only real strings count. A path in a comment, outside a string, or split across two strings is not matched.
- A Python docstring is skipped.

### hook_key

```yaml
match:
  type: hook_key
  keys:
    - leaderboards
```

- Matches a hook set at the top level of the app's `hooks.py`.
- It reports that the hook is declared. It does not read the hooked function.
- Use `error` when the hook no longer works at all, `warning` when it still works but expects something different.
- When what changed is the value the hooked function returns, use `returns_none` instead.

### override_subclass

```yaml
match:
  type: override_subclass
  keys:
    - override_doctype_class
```

- Reads the class each entry names, from the app's source.
- Reports only the classes that do not inherit the doctype's controller.
- Reports nothing when the class can't be found.

### returns_none and unreadable_function

```yaml
match:
  type: returns_none
  keys:
    - has_permission
```

- Both read the function each entry of the hook names, from the app's source, and report on the entry.
- A function imported into the module the hook names, from elsewhere in the app, is followed to where it is defined.
- `returns_none` reports a function that can return None: a path that falls off the end, a bare `return`, or `return None`. Any other returned expression counts as a value, so `return helper()` is not reported even when the helper can return None.
- A path ends at `return`, `raise` or `frappe.throw`. An `if`, `try`, `with` or `match` ends it only when every branch does, and a `match` needs a catch-all case. A `while True` with no `break` ends it.
- `unreadable_function` reports an entry whose function is not in the app, such as one in another app.
- Pair them on the same keys. An entry Preflight can read gets an `error` or nothing; one it can't read still gets a `warning`.

### missing_hook

```yaml
match:
  type: missing_hook
  keys:
    - add_to_apps_screen
  paths:
    - "*/workspace/*/*.json"
```

- `paths` are globs under the directory that holds `hooks.py`. The rule matches when the app ships a file they match and its `hooks.py` declares none of `keys` at the top level.
- One finding per app, on `hooks.py` with no line, naming the first matching file and how many more there are.
- With no line, an ignore comment can't reach it. Leave it out with `--baseline`.

### doctype

```yaml
match:
  type: doctype
  doctypes:
    - Blog Post
    - Blog Category
```

Looks in these places:

- Custom Fields on the doctype, or pointing at it
- Property Setters on the doctype
- Link and table fields in the scanned apps' doctypes
- Calls that take a doctype name, first or as `doctype=`, such as `frappe.get_all("Blog Post")`
- A `"doctype"` key in a dict or a JavaScript object, such as `frappe.get_doc({"doctype": "Blog Post"})`
- `` `tabBlog Post` `` in a SQL string
- `frappe.reload_doc(module, "doctype", name)`
- `frappe.listview_settings["Blog Post"]` in JavaScript
- The keys of hooks keyed by doctype in `hooks.py`, such as `doctype_js` and `doc_events`

A doctype can belong to only one rule.

### doctype_field

```yaml
match:
  type: doctype_field
  fields:
    - Lead.source
    - Opportunity.campaign
```

- Each field is written as `Doctype.fieldname`.
- Matches a query call that names the doctype and the field in the same call, such as `frappe.get_all("Lead", fields=["source"])` or `frappe.db.get_value("Lead", name, "source")`.
- On the site, matches a Property Setter on the field and a Custom Field whose `insert_after` names it.
- In Python, also matches the field read or set on a document whose doctype the code shows: one loaded or made in the same function (`frappe.get_doc("Lead", name)`, `frappe.new_doc`, `frappe.get_cached_doc`), the doc a `doc_events` hook hands its function, `self` in a class that `override_doctype_class` names or that is built on the doctype's controller, `doc` in a DocType Event server script, and `doc` in a Notification's condition. `doc.get("source")`, `doc.set` and `doc.db_set` count too.
- A document that arrives any other way, a row of its child table, and `frm.doc` in a form script are missed, since nothing there says which doctype the document is.

### select_field

```yaml
match:
  type: select_field
  patterns:
    - ^\*$
    - ^\d+$
    - (?i)^(?:(`[\w\s-]+`|\w+)\.)?(`\w+`|\w+)(?:\s+as\s+(?:`[\w\s-]+`|'[\w\s:-]+'|\w+))?$
```

- `patterns` are the field forms the target accepts. Any other field is reported.
- Reads the `fields` of `frappe.get_all`, `frappe.get_list`, their `frappe.db` forms and `frappe.qb.get_query`, the `fieldname` of `frappe.get_value`, `frappe.db.get_value` and `frappe.db.get_values`, and `pluck=` when a list query passes no fields.
- A string is split on the commas outside parentheses, so `"name, posting_date"` is two fields.
- A list built in a variable first is read, and so is an f-string, whose substitutions read as plain field names.
- In JavaScript, reads the fields of `frappe.db.get_list` and `frappe.db.get_value`, and of a `frappe.call` or `frappe.xcall` to `frappe.client.get_list`, `frappe.client.get_value` or `frappe.desk.reportview.get_list`.
- A dict and a `frappe.qb` term are not read.

### undeclared_import

```yaml
match:
  type: undeclared_import
  paths:
    - botocore
  dependencies:
    - boto3
    - botocore
```

- `paths` is the import name, matched the way `import_path` matches it. One import per rule.
- `dependencies` are every distribution that installs it: the one that provides it, and each one that requires it. `boto3` requires `botocore`, so declaring it excuses `import botocore`, while `import boto3` has its own rule that only `boto3` excuses.
- The import is reported only when the app declares none of them, compared by normalised name, in `[project].dependencies` of its `pyproject.toml` or in its `requirements.txt`.
- An import guarded by `except ImportError` is not reported.

### site_record

```yaml
match:
  type: site_record
  doctypes:
    - Repost Allowed Types
  filters:
    parenttype: Repost Accounting Ledger Settings
    allowed: 0
  title_field: document_type
```

- Reports each record the filters select, read with one `frappe.get_all` per doctype per scan. Nothing in an app is looked at.
- `filters` is optional; each field compares for equality with one value, as `frappe.get_all` does. On v15 an empty string matches an empty or NULL column alike, so `module: ""` finds every workspace with no module.
- A filter can name a field of the doctype a Link field points to: `module.custom: 1` on Workspace selects the workspaces whose module is a custom one. That doctype is read once more; when it selects nothing, the rule reports nothing.
- `title_field` is optional: the field the finding names the record by. Without it, the record's name.
- A doctype whose table is missing, or has no column for a filter or the title field, reports nothing: the app that brings it is not installed.
- Write one only when the filters say which records break; a rule on every row of a doctype asks for an audit of records nothing is wrong with.
- `--path` reads no site, so these rules are listed as not checked.

### bench_python

```yaml
match:
  type: bench_python
  python: ">=3.14,<3.15"
```

- Compares the bench's Python with `python`, the target's `requires-python`.
- The finding names `env/bin/python` and the version.

### requires_python and frappe_bound

```yaml
match:
  type: frappe_bound
  frappe: "16.53.0"
```

- Both read each app's `pyproject.toml`.
- `requires_python` reports a `requires-python` that shares no Python release with `python`.
- `frappe_bound` reports a frappe bound in `[tool.bench.frappe-dependencies]` that `frappe` falls outside. Use the target's latest release, which is what an upgrade installs.
- Only an app the upgrade leaves on its branch is read, such as a custom app on `main`. An app with no branch checked out, or that is not a git checkout, is listed under Not checked.

### dependency_pins

```yaml
match:
  type: dependency_pins
  dependencies:
    - Babel~=2.18.0
    - pytz==2025.2
```

- `dependencies` is the target frappe's `[project].dependencies`, as written.
- Reads `[project].dependencies` in the same apps' `pyproject.toml`, and reports a pin on the same package that no version satisfies together with frappe's.
- Package names are compared the way pip compares them, so `PyYAML` is `pyyaml`.

### required_apps

```yaml
match:
  type: required_apps
```

- Reports an entry in an app's `required_apps` hook that names an app missing from `sites/apps.txt`.
- `frappe/payments`, a git URL and an `@branch` suffix all resolve to the app name.

`bench_python`, `requires_python`, `frappe_bound`, `dependency_pins` and `required_apps` check every app on the bench, installed on a site or not. `--app` narrows them to the apps named.

### bench_node, target_branch and dependency_wheels

```yaml
match:
  type: dependency_wheels
  python: ">=3.14,<3.15"
```

These run a program or ask the network, so they are checked only with `--online`. What cannot be reached, such as no node, git failing or PyPI down, is listed under Not checked, never read as clean.

- `bench_node` runs `node --version` and reports a version outside `node`, a specifier such as `">=24"`. Not run with `--path`.
- `target_branch` reads the apps on frappe's version branch, the ones the upgrade switches, and reports one with no `upstream` remote, or whose `upstream` has no `branch` (`version-16`), asked with `git ls-remote`. Not run with `--path`.
- `dependency_wheels` looks up each of an app's dependencies on PyPI and takes the newest release pip would pick on `python`. It reports one whose releases all leave that Python out in their `Requires-Python`, or that has wheels for older CPythons and none for `python`. A package with only an sdist, or only pure Python wheels, is not reported.

## Test the rule

1. Add a line that should match to `tests/fixtures/violations.py`. Use `violations.js` for a JavaScript rule, `violations.scss` for a stylesheet pattern, `hooks_violations.py` for a hook or `required_apps` rule, and `pyproject_violations.toml` for a `pyproject.toml` rule. ERPNext rules have their own `violations_erpnext.py`, `violations_erpnext.js` and `hooks_violations_erpnext.py`.
2. Add a line that should not match to `tests/fixtures/clean.py`, `clean.js`, `clean.scss` or `hooks_clean.py`, or the `clean_erpnext` files.
3. Add the rule id and line to the matching scanner test in `tests/`. `tests/test_rule_coverage.py` fails for any rule with no line in a violations fixture. The three `--online` types are left out of it; `tests/test_online_scanner.py` covers them.
4. Add the rule to the [Rules](rules.md) page.
5. Run the tests:

```bash
pytest tests/
```
