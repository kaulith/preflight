# Overview

Preflight scans a Frappe site before a major version upgrade and lists what will break.

```bash
./env/bin/preflight --site mysite.local --target v16
```

Or an app's code on its own, with no site or bench, for CI:

```bash
preflight --path apps/my_app --target v16
```

## What it checks

- **Custom apps on the bench:** Python and `hooks.py` in the app's module, and front-end files (`.js`, `.mjs`, `.ts`, `.jsx`, `.tsx`, `.vue`, `.scss`) anywhere in the app's repository, `frontend/` and `desk/` included.
- **Patches:** the `execute:` lines of each app's `patches.txt`, which `bench migrate` runs as Python.
- **Code saved on the site:** Server Scripts and Client Scripts, the script and JavaScript of non-standard Reports, Web Forms, Web Pages, Custom HTML Blocks and Notification conditions. Disabled ones are skipped.
- **Customisations:** Custom Fields, Property Setters and link fields that point at a doctype or field the new version removed.
- **Records:** data on the site that the new version reads differently, such as the ERPNext repost types a v15 site left unchecked.
- **The bench:** whether it can install the target. The bench's Python, and for every app on the bench, installed on the site or not: its `requires-python`, its frappe bound, its dependency pins against frappe's, and its `required_apps`. With `--online`, also whether each app's remote has the target's branch, whether its dependencies have wheels for the target's Python, and whether node is new enough.

Two kinds of finding are listed apart and not counted:

- **Upstream apps.** An app on frappe's own version branch, such as erpnext on `version-15-hotfix`, is switched to the target's branch by the upgrade, which replaces its code. Name it with `--app` to count it.
- **Patches already run.** A finding in a patch the site has already run is listed apart, as that patch never runs again. One in a patch still to run is counted and marked, since `bench migrate` runs it on the new version.

With `--path` there is no site and no bench, so the site's scripts and customisations, Patch Log, the bench's Python and `required_apps` are not checked; the report says so. Each `pyproject.toml` is read whatever branch the app is on.

## What it does not do

- It changes nothing. It adds no doctypes and writes nothing to the database.
- It does not prove an upgrade is safe. It only finds what its rules know about.

## Sample report

A real run on a v15 site with erpnext. Each rule's explanation, printed under its title, is left out here.

```text
Preflight test.localhost: frappe 15.123.1 → v16
Rules checked 2026-10-25 against frappe v16.53.0
Apps scanned: erpnext, print_designer

ERROR (2)

  v16-removed-blog-doctypes: Blog doctypes moved out of the framework
    Custom Field: Blog Post-child_table  custom field child_table on Blog Post
    Property Setter: Blog Post-published-permlevel  property setter on Blog Post field published
  Fix with the upgrade: Install the Blogs app (https://github.com/frappe/blogs) to keep the
  doctypes, or drop the customisation and the code that reads it.

Upstream apps, not counted (1)
    erpnext on mergify/bp/version-15-hotfix/pr-58667: 188 found
  These apps are on frappe's own version branch: switching them to the v16 branch replaces this
  code, so what is found in it is upstream's to fix and not in the counts below. --app <name>
  lists an app's findings.

2 error
```

erpnext here is on a branch cut from `version-15-hotfix`, which counts as frappe's version branch. `--app erpnext` lists its 188 findings and counts them.

## Options

| Option | Default | What it does |
|---|---|---|
| `--site` | | Site to scan, on the bench whose env runs Preflight. Either this or `--path` |
| `--path` | | Scan the app in this directory, its repository root or its package (the directory holding `hooks.py`), with no site or bench. Can be repeated |
| `--target` | required | Version to check against: `v16` |
| `--app` | all apps except frappe | Scan only this app of the site. Can be repeated |
| `--severity` | `info` | Lowest level to print |
| `--fail-on` | `error` | Lowest level that fails the command. `never` always passes |
| `--format` | `text` | `text`, `json`, `sarif` for code scanning tools, or `html`: one page to open in a browser (`--format html > report.html`) |
| `--open` | | Also write the `html` report to a temporary file, print its path to stderr and open it in the browser. Nothing opens when the scan does not run |
| `--baseline` | | A report written earlier with `--format json`. Findings already in it are left out and counted apart, matched on rule, app, file and snippet, so a line that moves still matches |
| `--online` | off | Also run the checks that ask the network and the machine: the app's remote has the target's branch, its dependencies have wheels for the target's Python, and node is new enough |
| `--skip-tests` | off | Leave out test files: `test_*`, `*.spec.*`, `*.test.*`, `*.cy.*`, and anything under `tests/`, `cypress/` or `e2e/` |
| `--version` | | Print the Preflight version and exit |

A `preflight: ignore[rule-id]` comment on a line leaves that finding out. See [Suppressing a finding](getting-started.md#suppressing-a-finding).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Nothing at or above `--fail-on` |
| 1 | Findings at or above `--fail-on` |
| 2 | Wrong usage, such as an unknown target or app, a missing or wrong site, or a bench already on the target |
| 3 | The scan could not run. The traceback is on stderr |

## Limits

- **Code built at run time is missed.** `getattr`, `eval`, or a doctype name put together from variables.
- **Code written to survive the change is not reported.** An import inside `try` whose `except` names `ImportError` or `ModuleNotFoundError` is skipped, and so is Python code under an `if` that reads the frappe version, through `frappe.__version__` or a helper such as `is_frappe_version`.
- **JavaScript and SCSS patterns are matched line by line.** Comments are skipped, but a pattern can't tell a call from a mention of the same name. Doctype and field rules read the call as a whole, so a call that prettier splits across lines is still matched.
- **Built files are skipped.** `dist/`, `node_modules/`, `*.min.js`, and any file with a line longer than 2,000 characters.
- **Most hook rules see the hook, not the function behind it.** The `has_permission` and `override_doctype_class` rules read the function or class in the app's own source. A `has_permission` function defined anywhere else is reported as a warning to check by hand.
- **A field read off a document is seen only where the code shows its doctype.** A doc loaded or made in the same function, a `doc_events` handler's doc, `self` in a doctype's controller, a DocType Event server script's `doc`, and a Notification condition's `doc`. One passed in from anywhere else, and `frm.doc` in a form script, are missed.
- **Behaviour changes with no API to match are missed.** v16 sorts lists by `creation` where v15 used `modified`.
- **The upgrade steps themselves are not checked.** See the [upgrade checklist](upgrade-checklist.md).
- **Some checks need `--online`.** Whether an app's remote has the target's branch, whether its dependencies have wheels for Python 3.14, and the node version are checked only with `--online`, which runs git and node and asks PyPI.

## Next

- [Getting started](getting-started.md)
- [Reading a report](reading-a-report.md)
- [Rules](rules.md)
- [Upgrade checklist](upgrade-checklist.md)
