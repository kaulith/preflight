# Preflight

Scans a Frappe site before a major version upgrade and lists what will break.

```bash
./env/bin/preflight --site mysite.local --target v16
```

Or an app's code on its own, with no site or bench, for CI:

```bash
preflight --path apps/my_app --target v16
```

## What it checks

- Custom apps on the bench: Python and `hooks.py` in the app's module, and JavaScript,
  TypeScript, Vue and SCSS anywhere in its repository, `frontend/` and `desk/` included.
  Vendored, built and minified files are left out
- The `execute:` lines of each app's `patches.txt`, which `bench migrate` runs as Python
- Code saved on the site: Server and Client Scripts, the scripts of non-standard Reports, Web
  Forms, Web Pages and Custom HTML Blocks, and Notification conditions. Disabled ones are left out
- Custom Fields, Property Setters and link fields that point at a removed doctype or field
- Records on the site that the target reads differently, such as the ERPNext repost types a v15
  site left unchecked
- The bench, for every app on it whether a site has it installed or not: the environment's
  Python, each app's `requires-python`, frappe bound and dependency pins, and its `required_apps`

It changes nothing on the site. A clean report means no known problems were found, not that the
upgrade is safe.

An app on frappe's own version branch (`version-15-hotfix` on a v15 bench) is listed apart and
not counted: the upgrade switches it to the target's branch, which replaces the code. Name it with
`--app` to count it. An app with no branch checked out, as every app on Frappe Cloud, can't be told
apart: its findings are counted and the report says so; there, pass `--app` for each of your own
apps. A finding in a patch the site has already run is listed apart too, as that
patch never runs again; one in a patch still to run is marked, since `bench migrate` runs it on
the new version.

With `--path` there is no site and no bench, so the site's scripts, customisations and records,
Patch Log, the bench's Python and `required_apps` are not checked; the report says so. Each
`pyproject.toml` is read whatever branch the app is on.

## Install

From the bench directory, into the bench's own environment:

```bash
./env/bin/pip install prefly
```

The package is `prefly`; the command is `preflight`. It is not a bench app: don't `bench get-app`
it, and nothing is installed on a site. `--path` needs no bench, so for it any Python 3.10 or newer
will do: `pip install prefly`.

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

Exit codes: 0 clean, 1 findings at or above `--fail-on`, 2 wrong usage, 3 the scan could not run,
with the traceback on stderr.

## Suppressing a finding

A comment on the finding's own line naming the rule leaves it out, and the report counts it as
suppressed:

```python
frappe.db.get_value("Blog Post", name)  # preflight: ignore[v16-removed-blog-doctypes]
```

```js
frappe.energy_points.get_points(user); // preflight: ignore[v16-removed-energy-points-js]
```

Several rules go in one comment, `preflight: ignore[rule-a, rule-b]`. A bare `preflight: ignore`
does nothing. It works in Python, JavaScript (`//` or `/* */`), SCSS, Vue, `pyproject.toml`,
`patches.txt` and site scripts. On an `execute:` line of `patches.txt` it costs a rerun: Patch Log
records the whole line, comment included, so the next `bench migrate` runs that patch again. Use
`--baseline` for those.

## Docs

- [Overview](https://github.com/kaulith/preflight/blob/main/docs/overview.md)
- [Getting started](https://github.com/kaulith/preflight/blob/main/docs/getting-started.md)
- [Reading a report](https://github.com/kaulith/preflight/blob/main/docs/reading-a-report.md)
- [Rules](https://github.com/kaulith/preflight/blob/main/docs/rules.md)
- [Upgrade checklist](https://github.com/kaulith/preflight/blob/main/docs/upgrade-checklist.md)
- [Writing a rule](https://github.com/kaulith/preflight/blob/main/docs/writing-a-rule.md)
- [How it was tested](https://github.com/kaulith/preflight/blob/main/docs/how-it-was-tested.md)

## Tests

From a checkout:

```bash
pip install -e . pytest
pytest
```
