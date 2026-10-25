# Writing a rule

One YAML file per breaking change, in the directory for the target version
(`rules/v16/`, `rules/v17/`). Rules are data; the engine does not change when a
rule is added. A directory under `rules/` that holds a `target.yaml` is a target,
and the id carries its target as a prefix by convention.

The file name is the rule id, and the loader rejects a rule whose `id` does not
match its file name.

```yaml
id: v16-removed-newsletter
title: Newsletter moved out of the framework
severity: error            # error | warning | info
match:
  type: import_path
  paths:
    - frappe.email.doctype.newsletter
message: >
  What breaks, in the words a site owner would use.
replacement: >
  What to do instead.
fix: with-upgrade          # optional: before | with-upgrade
references:                # at least one; the thing that proves the claim
  - https://github.com/frappe/frappe/pull/32971
```

Severity: `error` means it raises after the upgrade, `warning` means deprecated
or changed behaviour that needs an audit, `info` means worth knowing.

Check the claim against the target's source before writing the rule; the deprecation
dumpster's own label can be wrong about where a function is imported from, or about its name
(`frappe.tests.upate_system_settings` is the label, `update_system_settings` is the import;
`frappe.tests_runner` is the label, `frappe.test_runner` the module). The
`references` list points at the merged PR, the dumpster entry or the source file
that proves it.

## `fix` and `shim`

`fix` says when the replacement can go in. `before` means it already works on the version the
site runs now, frappe v15 for `rules/v16`, so the change can ship ahead of the upgrade.
`with-upgrade` means the replacement only exists on the target, so it goes in with the upgrade,
or ahead of it behind a shim. Decide it from the source of the version being left, at the commit
that was checked: the import path, function, argument or behaviour the replacement names has to
exist and work there. A fix that is not code takes the value that is true for when the site
owner can act. The Newsletter app has no version-15 branch, and on v15 its doctypes still belong
to frappe, so installing it is `with-upgrade`; v15 runs on Python 3.14 too, so rebuilding the
environment on it is `before`.

`shim` is a snippet that runs on both versions, written as a literal block (`|`) so its tabs
survive:

```yaml
fix: with-upgrade
shim: |
  try:
  	from frappe.utils.modules import get_modules_from_app
  except ImportError:
  	from frappe.config import get_modules_from_app
```

A moved import is shimmed this way, which Preflight does not report (see `import_path`). Any
other shim goes in only when it is short and checked against the source of both versions. Both
keys are optional.

## `target.yaml`

Each target directory holds a `target.yaml` beside its rules. The loader reads it for the target
and skips it when it loads the rules:

```yaml
released: true            # the frappe major is out
checked: "2026-10-25"     # when the rules were last checked against the source, quoted
against: frappe v16.53.0  # what they were checked against
```

All three keys are required, and no others are allowed. A target with `released: false` still
loads, so its rules are tested with the rest, but `--target` refuses it unless the hidden
`--unreleased` flag is passed, and the error's list of available targets leaves it out.

`rules/v17` targets a version that is not released: it tracks frappe develop, its `target.yaml`
says `released: false`, and `--target` refuses it. Its API rules were last checked on 2026-10-25
against develop at `c4e97234b4`. It holds three kinds of rule:

- `v17-deprecated-*`, severity `warning`: a deprecation whose dumpster entry or deprecation
  warning names v17 as the removal and that is still present on develop. Nothing breaks yet.
- `v17-removed-*` and `v17-moved-*`, severity `error`: a path that is gone from develop, with
  the PR that removed it as the reference.
- `v17-bench-python` and `v17-app-*`: what the bench must satisfy to install develop, checked
  against develop at `191a3e2664` on 2026-10-24, and `v17-app-dependency-pins` at `c4e97234b4`
  on 2026-10-25. Their severity is what the install does: pip refuses a Python outside
  `requires-python` (`error`), bench only warns on a frappe bound (`warning`), and a clashing pin
  leaves frappe or the app on a version it does not allow (`error`).

A deprecated rule becomes an error, and is renamed, only once the path is gone from develop.
Recheck the directory against develop before each release, and pin dumpster references to the
commit that was checked, since a branch link stops proving anything once the entry is deleted.

## `import_path`

Matches `import x.y`, `from x import y`, aliased imports and attribute access
through an alias. Prefix match: `frappe.social.doctype.energy_point_log` also
matches `frappe.social.doctype.energy_point_log.energy_point_log.get_points`.

A name pulled in with `from x import y` is reported on the import line, not on
each later use of the bare name.

An import under a `try` whose `except` names `ImportError` or
`ModuleNotFoundError`, or in that handler, is not reported: it is written to
survive the module being gone, like the test shim
`try: from frappe.tests import IntegrationTestCase` with
`except ImportError: from frappe.tests.utils import FrappeTestCase`. Only the
import statements are skipped; a call in the same block is still reported.

The same paths are matched where the code names one as a string for the
framework to resolve: the first argument, or the `method` keyword, of
`frappe.get_attr`, `frappe.get_module`, `frappe.call`, `frappe.enqueue` and
`frappe.utils.background_jobs.enqueue`, listed in `python_scanner.ATTR_APIS`.
Matching is by path segment, so `frappe.utils.gzip_compression` is not a hit on
`frappe.utils.gzip_compress`, and a path in a string nothing resolves is not a
reference.

In `hooks.py`, every string in a top-level assignment that is wholly a dotted
path is matched the same way, keys included, since Frappe resolves the functions
that `scheduler_events`, `doc_events`, `override_whitelisted_methods` and the
other hooks name. A string a `string_contains` rule already reports is left to
that rule, so one entry is not reported twice.

In JS, every string literal that is wholly a dotted path is matched the same way,
wherever it sits, since `frappe.call`, `frappe.xcall` and a frappe-ui resource's
`url` hand it to frappe to resolve
(`method: "frappe.email.doctype.newsletter.newsletter.subscribe"`). A path inside
a longer string is not, and a string a `string_contains` rule already reports is
left to that rule.

## `call`

Matches calls to one of `paths`. On its own it matches every call; the optional
keys narrow it to calls that pass a removed argument:

```yaml
match:
  type: call
  paths:
    - frappe.permissions.has_permission
  with_kwargs:            # all of these keywords are passed
    - raise_exception
  with_positional_args: 5 # or: at least this many positional arguments, because
                          # the removed argument was the 5th
```

With both given, a call matches on either, which is how an argument that can be
passed both ways is caught in one rule.

`url_host: private` narrows the call to one that requests a private host: its first argument,
or its `url` keyword, is a literal URL whose host is `localhost` or an IP address that is not
globally routable (loopback, a private range, link-local). An f-string counts when its leading
text holds the whole host. Only a literal host is judged: a hostname is not resolved, so a name
that points at a private address is not reported.

```yaml
match:
  type: call
  paths:
    - frappe.make_get_request
  url_host: private
```

`returns` is for a function the target makes return more values than before. It leaves out a call
whose result is already taken apart in a way that works there: indexed or sliced
(`build_xlsx_data(...)[:2]`), unpacked into `returns` names, or unpacked into a starred name and
at most `returns` others (`rows, widths, *rest = build_xlsx_data(...)`). Any other use is
reported, an unpack into fewer names and a result held in one name included, since the name is not
followed to where it is read:

```yaml
match:
  type: call
  paths:
    - frappe.desk.query_report.build_xlsx_data
  returns: 3
```

## `pattern`

A line-based regular expression, run over the app's `.js`, `.mjs`, `.ts`, `.jsx`,
`.tsx`, `.vue` and `.scss` files and the site's Client Scripts. Use it for client
globals, which have no import to key on, and for stylesheet imports:

```yaml
match:
  type: pattern
  patterns:
    - \bfrappe\.views\.ListSidebar\b
```

Anchor the name with `\b`, or a longer name sharing the prefix
(`frappe.views.ListSidebarGroupBy`) is reported too. Comments are blanked before
the line is matched, block and trailing ones included; anything else on the line
counts, strings too, so the scanner cannot tell a call from a mention.

## `string_contains`

Matches a dotted path inside a string literal, in Python and JS both: the
endpoint names that `frappe.call`, `frappe.xcall`, `frappe.enqueue` and
`override_whitelisted_methods` carry as text.

```yaml
match:
  type: string_contains
  paths:
    - frappe.client.get_js
```

Substring match, so a longer path under the same prefix matches as well. Python
strings come off the AST. JS strings come from a lexer that skips comments and
reads a template literal's text between its substitutions, so a path written
outside a string, or split across two, is not a hit. A Python docstring is
skipped, since it names a path without calling it.

## `hook_key`

Matches a hook an app declares at the top level of its own `hooks.py`, by name.
Nothing else in the app is looked at, and a name bound inside a function is not a
hook:

```yaml
match:
  type: hook_key
  keys:
    - leaderboards
```

The finding lands on the assignment, so a rule of this type says the hook is
declared, not what the hooked function does. That makes severity a judgement
about the declaration itself: `error` when declaring the hook is already broken
in the target version (nothing reads it any more, so the feature is gone),
`warning` when the framework still reads it but expects something different back,
which every declaring app has to audit one by one. Where the difference is in what
the hooked function returns, `returns_none` reads the function instead.

## `override_subclass`

Reads the class an `override_doctype_class` entry names, out of the app's own
source, and reports only the entries whose class does not inherit the doctype's
controller:

```yaml
match:
  type: override_subclass
  keys:
    - override_doctype_class
```

The hook value is a dotted path into the app being scanned, so the check needs no
import: the module file is read off disk, the `class X(Base)` line is parsed, and
the base names are compared against the doctype with its spaces and dashes
removed, which is how `get_controller` spells the controller. A base imported
under an alias is resolved from that file's import statements, relative imports
resolved against the file holding them, and a base defined in the app is followed
one class at a time, so inheriting the controller through another class still
counts.

Nothing is reported when the class cannot be read: a path that does not resolve
already throws in `get_controller` on the version being left behind, so the app
is broken before the upgrade and its own boot says so. That is what lets this
type carry `error` where a rule on the declaration alone can only carry
`warning`, and the finding lands on the dict entry rather than the hook.

A rule of this type only works where the app's source is on disk, which means
`app_path` must reach the scanner; the site script scan passes no app and reports
nothing for it.

## `returns_none` and `unreadable_function`

Read the function each entry of the hook names, out of the app's own source the
way `override_subclass` reads a class, and report on the dict entry:

```yaml
match:
  type: returns_none
  keys:
    - has_permission
```

`returns_none` reports a function that can return None: a path that falls off the
end, a bare `return`, or `return None`. A path ends at `return`, `raise` or
`frappe.throw`, and an `if`, `try` or `with` ends it only when every branch does.
Any other returned expression counts as a value, so a function that returns a
helper's result is not reported even when the helper can return None; only the
hooked function is read, not what it calls.

`unreadable_function` reports the entries whose function cannot be read out of the
app's own source: one in another app, an import chain that leaves the app or loops,
or a path that does not resolve. A function imported into the module the hook names
is followed to where the app defines it. Pair it with a `returns_none`
rule on the same keys, so an entry the check cannot read still asks for an audit
at `warning`, while an entry it can read gets an `error` or nothing.

Both need `app_path`, as `override_subclass` does.

## `missing_hook`

Matches an app that ships files the target only shows through a hook, while its
`hooks.py` declares none of the hook's names at the top level:

```yaml
match:
  type: missing_hook
  keys:
    - add_to_apps_screen
  paths:                     # globs under the directory that holds hooks.py
    - "*/workspace/*/*.json"
```

One finding per app, on `hooks.py` with no line, naming the first file the globs
match from the repository root and how many more there are. Having no line, it
cannot take an ignore comment; `--baseline` leaves it out. A companion app that
mounts on a host app's rail through a Dock record it ships (`mount_on`) needs no tile
of its own and is reported all the same.

## `doctype`

Matches a doctype the target version removed, by exact name:

```yaml
match:
  type: doctype
  doctypes:
    - Blog Post
    - Blog Category
```

These places are looked at, and each finding says which one it came from:

- a Custom Field on the doctype, or a link or table field pointing at it
- a Property Setter on the doctype
- a link or table field in one of the scanned apps' own doctypes
- a doctype named as a literal argument to an API that takes one, first or as
  `doctype=` (`frappe.get_all("Blog Post")`, `frappe.get_single`, `frappe.db.exists`,
  `frappe.qb.DocType`, `frappe.ui.form.on`, `frappe.set_route("List", "Blog Post")`)
- the value of a `"doctype"` key in a dict literal or a JS object
  (`frappe.get_doc({"doctype": "Blog Post", ...})`,
  `createListResource({ doctype: "Blog Post" })`)
- the key of `frappe.listview_settings` in JS (`frappe.listview_settings["Blog Post"]`)
- a table named in any string, by the exact name between backticks
  (`` `tabBlog Post` `` in raw SQL)
- a doctype `frappe.reload_doc(module, "doctype", name)` loads, compared by
  scrubbed name (`blog_post`): v16 opens the missing JSON file and raises
- a key of a hook keyed by doctype in `hooks.py` (`doctype_js`, `doc_events`,
  `has_permission` and the rest of `hooks_scanner.DOCTYPE_HOOKS`)

A doctype belongs to one `doctype` rule. The loader rejects a second one naming the
same doctype, because the scanners key a doctype to a single rule and the other one
would never fire.

The API lists are in `python_scanner.DOCTYPE_APIS` and `js_scanner.DOCTYPE_APIS`.
Keeping to them, and to the dict key, the backticked table and `reload_doc`, is
what makes the name safe to match: doctype names are ordinary words, and
`__("Newsletter")` in a label is not a reference to the doctype. `reload_doc` is
read in Python only. A doctype built at run time is
missed, the same way the other matchers miss `getattr`.

The schema findings carry no line number, so the report shows the record name on
its own.

## `doctype_field`

Matches a field the target version removed or renamed on a doctype that stays, written as
`Doctype.fieldname`:

```yaml
match:
  type: doctype_field
  fields:
    - Lead.source
    - Opportunity.campaign
```

The field is looked for in a query API call that names the doctype and the field in the same
call (`frappe.get_all("Lead", fields=["source"])`, `frappe.db.get_value("Lead", name,
"source")`), on the site in a Property Setter on the field and in a Custom Field whose
`insert_after` names it, and in Python where the field is read or set on a document whose doctype
the code shows (`doc.source`, `doc.get("source")`, `doc.set` and `doc.db_set`): one loaded or made
in the same function by `frappe.get_doc`, `get_cached_doc`, `get_last_doc`, `get_single` or
`new_doc` with the doctype as a literal, the doc a `doc_events` hook hands its function, `self` in a
class `override_doctype_class` names or one built on the doctype's controller, `doc` in a DocType
Event server script, and `doc` in a Notification's condition. A document that arrives any other way, a row of its child table, and
`frm.doc` in a form script are not followed.

## `undeclared_import`

Matches an import of a package the target's frappe no longer installs, when the app does not
declare it:

```yaml
match:
  type: undeclared_import
  paths:              # the import name, matched the way import_path matches it
    - botocore
  dependencies:       # every distribution that, declared by the app, installs it
    - boto3
    - botocore
```

The import is reported only when the app declares none of `dependencies`, compared by
normalised name, in `[project].dependencies` of its `pyproject.toml` or in its
`requirements.txt`. An import guarded by `except ImportError`, as for `import_path`, is not
reported. A finding is dropped as soon as the app declares any one of the distributions, so a
rule names one import, and lists the distribution that provides it with each one that requires
it: `boto3` brings `botocore`, so declaring it excuses `import botocore`, while declaring only
`botocore` leaves `import boto3` to its own rule. Check each requirement in the metadata of the
release that the frappe being left pins, boto3 1.34.143 for frappe v15.

## `select_field`

Matches a string the code passes as the fields of a query, when none of
`patterns` accepts it. The patterns are the field forms the target accepts,
copied from its `frappe/database/query.py`, so the rule reports what the target
rejects:

```yaml
match:
  type: select_field
  patterns:               # the accepted forms; any other field is reported
    - ^\*$
    - ^\d+$
    - (?i)^(?:(`[\w\s-]+`|\w+)\.)?(`\w+`|\w+)(?:\s+as\s+(?:`[\w\s-]+`|'[\w\s:-]+'|\w+))?$
```

The fields read are the `fields` argument, by keyword or second position, of
`frappe.get_all`, `frappe.get_list`, `frappe.db.get_all`, `frappe.db.get_list`
and `frappe.qb.get_query`, and the `fieldname` argument, by keyword or third
position, of `frappe.get_value`, `frappe.db.get_value` and
`frappe.db.get_values`, listed in `python_scanner.SELECT_FIELD_APIS`. A bare
string and each string in a list or tuple are split on the commas outside
parentheses, the way v16 splits them, so `"name, posting_date"` is two fields and
`"ifnull(qty, 0)"` is one. An f-string is read with each `{...}` as a plain name,
so `f"sum({field}) as total"` is reported and `f"{field} as total"` is not. A list
held in a local name is read with every string the function gives it (`=`,
`append`, `extend`, `+=`) before the call. `pluck=` is read when no fields are
passed, as v16 then selects it. In JS, the literal `fields` of `frappe.db.get_list`,
`frappe.db.get_value` and the `frappe.client` query methods called through
`frappe.call` are read. A dict (`{"SUM": "qty"}`) and a `frappe.qb` term are not.

## `site_record`

Matches records on the site, for a change that makes the target read data the version being left
wrote in a different way. Nothing in an app is looked at:

```yaml
match:
  type: site_record
  doctypes:
    - Repost Allowed Types
  filters:                    # optional: field: value, all must hold
    parenttype: Repost Accounting Ledger Settings
    allowed: 0
  title_field: document_type  # optional: the field the finding names the record by
```

Each doctype is read with one `frappe.get_all` per scan, nothing per record, so a filter compares
for equality and takes one value. The filters go to `frappe.get_all` as written and mean what they
mean there: on frappe v15 an empty string matches an empty or NULL column alike, which is how
`module: ""` finds every workspace with no module.

A filter can also name a field of the doctype a Link field points to, as `module.custom: 1` does
on Workspace: that doctype is read once for the names the filter selects, and the records whose
Link field holds one of them are returned. A linked filter that selects nothing reports nothing,
and so does a Link field the doctype lacks.

Each record returned is a finding labelled by its doctype and name (`Repost Allowed Types:
s19du55nnr`), with the value of `title_field`, or the name when there is none, and then the filters
as the snippet. A doctype whose table is missing, or has no column for a filter or the title field,
is not queried and reports nothing: the app that brings it is not installed, or the site never had
the field. The columns come from frappe's cached table columns, so the check costs no query once
the cache holds them. A rule that filters on a field the target removed therefore reports nothing
on a site that started on the target.

Write one only when the filters say which records break: a rule on every row of a doctype asks
for an audit of records nothing is wrong with. A `site_record` rule claims no doctype, so it can
name one a `doctype` rule names. `--path` reads no site and lists the records as not checked.

## `bench_python`

Matches the Python the bench environment runs against the target's `requires-python`:

```yaml
match:
  type: bench_python
  python: ">=3.14,<3.15"
```

The finding names `env/bin/python` and the version, with no line.

## `requires_python` and `frappe_bound`

Read each app's `pyproject.toml`. `requires_python` reports a `requires-python` that shares no
Python release with `python`. `frappe_bound` reports a frappe bound in
`[tool.bench.frappe-dependencies]` that `frappe` falls outside, compared with `semantic_version`
the way bench's `validate_dependency` compares it:

```yaml
match:
  type: frappe_bound
  frappe: "16.53.0"   # the target's latest release, which is what an upgrade installs
```

Only an app the upgrade leaves on its branch is read: one checked out on a named branch that is
not the version branch of the frappe the bench runs (`version-15`, `-hotfix` or `-beta` on a v15
bench) and not cut from one, like a custom app on `main` or Insights on its own `version-3`. A
frappe version branch is switched to the target's, which carries its own `pyproject.toml`. An app
on no branch, detached or not a git checkout at all, says nothing about where it goes, so its
`pyproject.toml` is listed as not checked, with the reason.

## `dependency_pins`

Reads `[project].dependencies` in the `pyproject.toml` of the same apps `requires_python` reads,
and reports a dependency on a distribution that `dependencies` also names, compared by normalised
name (`PyYAML` is `pyyaml`), when no version satisfies both:

```yaml
match:
  type: dependency_pins
  dependencies:       # the target frappe's [project].dependencies, as written
    - Babel~=2.18.0
    - pytz==2025.2
```

bench installs each app with pip or uv into the env that already holds frappe's pins, and neither
refuses a clash: the later install replaces the version the earlier one put in and exits 0. The
finding shows frappe's pin beside the app's.

Finding a version both accept is an approximation: only 0, each version either side names, and one
above each are tried. That is exact for the `==`, `~=` and `>=` with `<` that frappe writes; a
pair whose shared versions all lie past a `!=` wildcard (`!=1.*`) reads as a clash. Environment
markers are ignored, and a direct URL (`PyPika @ git+...`) names no version, so it never clashes.

## `required_apps`

Reports an entry in an app's `required_apps` hook that names an app missing from
`sites/apps.txt`. The entry is parsed the way `frappe.installer.parse_required_app_name` parses
it, so `frappe/payments`, a git URL and an `@branch` suffix all resolve to the app name.

These five check every app on the bench, whether a site has it installed or not, and `--app`
narrows them to the apps named.

## `bench_node`, `target_branch` and `dependency_wheels`

These run a program or ask the network, so they are checked only with `--online`, and
`tests/test_rule_coverage.py` leaves them out; `tests/test_online_scanner.py` covers them. What
cannot be reached (no node, git failing, PyPI down) is listed under "Not checked", never read as
clean.

- `bench_node` runs `node --version` and reports a version outside `node`, a specifier such as
  `">=24"`. Not run with `--path`, which has no bench.
- `target_branch` reads the apps on frappe's version branch, the ones the upgrade switches, and
  reports one with no `upstream` remote, or whose `upstream` has no `branch` (`version-16`),
  asked with `git ls-remote`. Only `upstream` is asked, since it is the remote
  `bench switch-to-branch` reads. Not run with `--path`.
- `dependency_wheels` looks up each of an app's dependencies on PyPI and takes the newest release
  pip would pick on `python`. It reports a dependency whose matching releases all exclude that
  Python in their Requires-Python, or whose release has wheels for older CPythons but none usable
  on `python`. A package that ships only an sdist, or only pure Python wheels, is not reported. An
  app on frappe's version branch is skipped, as its `pyproject.toml` is replaced.

```yaml
match:
  type: dependency_wheels
  python: ">=3.14,<3.15"
```

## Testing a rule

The loader validates every rule at load time, so any scan checks the syntax and
names the file that is wrong.

Add the offending line to `tests/fixtures/violations.py` (`violations.js` for a
JS rule, `violations.scss` for a stylesheet pattern, `hooks_violations.py` for a hook,
`missing_hook` or `required_apps` rule, with the file a `missing_hook` rule's globs match under
`tests/fixtures/digest`, `pyproject_violations.toml` for a `pyproject.toml` rule) and a near miss
(the replacement API, a similarly named function) to `tests/fixtures/clean.py`, `clean.js`,
`clean.scss` or `hooks_clean.py`, then add the rule id and line to the expectation in
`tests/test_python_scanner.py`, `tests/test_js_scanner.py` or
`tests/test_hooks_scanner.py`.
`tests/test_rule_coverage.py` asserts that every shipped rule has a line in one
of the violations fixtures, for every target.

A `site_record` rule has no line to put in a fixture, so the coverage test leaves it out. Its test
goes in `tests/test_site_records.py` instead: a fixture makes the record on the site, with a near
miss beside it, and rolls both back. Those tests run only against a site, from the bench's `sites`
directory with `PREFLIGHT_SITE` set, and skip on a site that no longer has the doctypes they make.

Then add the rule to the right table on the Rules page of the docs, which is the list a
reader sees before they install anything.

```
pytest tests/
```
