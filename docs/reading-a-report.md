# Reading a report

The report is grouped by severity, then by rule. Each rule shows what breaks, where it was found, and the fix.

The first line names the site, the frappe version on the bench, and the target. The second says when the rules were last checked, and against which release:

```text
Preflight test.localhost: frappe 15.123.1 → v16
Rules checked 2026-10-25 against frappe v16.53.0
```

With `--path` there is no site or bench, and the first line reads `Preflight code only → v16`.

## Severities

| Severity | Meaning | By default |
|---|---|---|
| `error` | Breaks on the new version | Command fails |
| `warning` | Deprecated, or behaves differently now | Printed only |
| `info` | Good to know | Printed only |

A warning is not a small error. Some warnings are silent changes: the code still runs but returns a different value.

## The fix

Each rule ends with its fix, and the label says when it can go in:

| Label | Meaning |
|---|---|
| `Fix before upgrading` | The replacement already works on the version the site runs now. Ship it ahead of the upgrade |
| `Fix with the upgrade` | The replacement only exists on the new version. It goes in with the upgrade |

Some rules add a **Shim that runs on both versions**: a short snippet, such as an import inside `try` with the old path under `except ImportError`, that lets a with-the-upgrade fix go in early. Preflight does not report the shim itself.

## Where a finding is

| It looks like | It is |
|---|---|
| `erpnext/erpnext/templates/pages/home.py:26` | A line in an app's code: the app's folder in `apps/`, then the file from the app's repository root |
| `erpnext/erpnext/patches.txt:12` | An `execute:` line in an app's `patches.txt` |
| `Server Script: Blog Post digest:2` | A line in a script saved on the site |
| `Report: Sales Summary (javascript):4` | A line in code saved on the site, in a doctype that holds code in two fields. The field is named in brackets |
| `Custom Field: Blog Post-child_table` | A record on the site. Records have no line number |
| `my_app/pyproject.toml:9` | A line in an app's `pyproject.toml`, from the bench check |
| `env/bin/python` | The bench's Python, from the bench check. The snippet gives its version |

## Upstream apps

```text
Upstream apps, not counted (1)
    erpnext on mergify/bp/version-15-hotfix/pr-58667: 188 found
```

An app on frappe's own version branch, such as erpnext on `version-15-hotfix` or a branch cut from it, is switched to the target's branch by the upgrade, and that replaces its code. What Preflight finds in it is upstream's to fix, so it is listed here, left out of the counts, and never fails the command.

- `--app erpnext` counts its findings like any other app's.
- An app that `--online` finds has no target branch upstream stays counted.

## Patches already run

```text
Rules hit in patches already run, not counted (2)
    v16-erpnext-moved-settings: 5 found
    v16-sql-function-string-fields: 7 found
```

Patch Log records these patches as run, so `bench migrate` does not run them again, and what they call can be gone on the new version without breaking anything. They are not counted. The number in brackets is the number of rules.

A finding in a patch the site has not run yet stays in the counts and ends with `[pending patch, stops bench migrate]`. `bench migrate` runs that patch on the new version, and the error stops the migration.

## Not scanned

These blocks print right above the totals. Read them first: they mean the totals are short. When any of them, or [Not checked](#not-checked), is there, a report with no findings ends with "No known incompatibilities found in what was scanned."

**Files Python could not parse**

```text
Not scanned, python 3.11.15 could not parse them (3)
    frappe/model/document.py
```

The bench's Python is older than the code. Scan from a bench with a newer Python.

**Apps with no code on the bench**

```text
Not scanned, no code on this bench (1)
    print_designer
```

The site lists the app as installed, but the bench doesn't have it. Its code was not read. Its scripts and customisations still were.

**Files or apps that could not be read**

```text
Not scanned, could not be read (1)
    my_app/public/js/vendor.js: No such file or directory
```

Each line names the file and the reason, such as a broken symlink. An app is listed here when importing it fails, and then none of its code was read.

## Not checked

```text
Not checked (1)
    pyproject.toml of my_app: not a git checkout, requires-python, frappe bound and dependency pins not checked
```

The bench check reads an app's `pyproject.toml` only when the app is checked out on a branch, because the branch says which `pyproject.toml` the upgrade installs. An app that is not a git checkout, or has no branch checked out, is listed here with the reason.

Also listed here:

- An app in `sites/apps.txt` whose code is missing or fails to import. Its `pyproject.toml` and `required_apps` were not read.
- With `--online`, a check that could not reach what it asks, such as no node on the PATH, a git remote that failed, or PyPI being down. It is never read as clean.
- An app with findings and no branch checked out, as every app on Frappe Cloud: nothing shows whether the upgrade replaces its code, so its findings stay counted. Pass `--app` for each of your own apps to leave the rest out.
- With `--path`, what needs a site or a bench: the site's scripts, Custom Fields, Property Setters, records and Patch Log, the bench's Python and `required_apps`.

## Hidden findings

`--severity` hides lower levels but still counts them:

```text
7 error
4 more below error, not shown.
```

`--severity` only changes what prints. `--fail-on` decides the exit code, and it always looks at every counted finding.

Findings left out by an ignore comment or by `--baseline` are counted on their own line, and never fail the command:

```text
2 suppressed by an ignore comment and 5 in the baseline, not counted.
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Nothing at or above `--fail-on` |
| 1 | Findings at or above `--fail-on` |
| 2 | Wrong usage, such as an unknown target or app, a missing or wrong site, or a bench already on the target |
| 3 | The scan could not run. The traceback is on stderr |

## JSON

`--format json` prints one object. It is the contract for CI: read it by key. `schema_version` goes up when a key is removed or changes meaning; a new key can arrive without it.

```json
{
  "schema_version": 1,
  "preflight_version": "0.0.1",
  "site": "mysite.local",
  "target": "v16",
  "rules": {"checked": "2026-10-25", "against": "frappe v16.53.0"},
  "python": "3.14.3",
  "frappe_version": "15.123.1",
  "severity": "info",
  "fail_on": "error",
  "verdict": "fail",
  "summary": {
    "error": 1,
    "warning": 0,
    "info": 0,
    "below_severity": 0,
    "suppressed": 0,
    "baselined": 0,
    "upstream": 188,
    "ran_patches": 0
  },
  "apps": ["erpnext", "my_app"],
  "missing_apps": [],
  "findings": [
    {
      "rule": "v16-removed-newsletter",
      "severity": "error",
      "title": "Newsletter moved out of the framework",
      "message": "...",
      "replacement": "...",
      "fix": "with-upgrade",
      "shim": null,
      "references": ["https://github.com/frappe/frappe/pull/32971"],
      "app": "my_app",
      "source": "app",
      "file": "my_app/digest.py",
      "line": 5,
      "snippet": "from frappe.email.doctype.newsletter import newsletter",
      "stops_migrate": false
    }
  ],
  "upstream": [
    {"app": "erpnext", "branch": "version-15-hotfix", "findings": ["..."]}
  ],
  "ran_patch_findings": [],
  "unparsable_files": [],
  "unreadable_files": [],
  "not_checked": []
}
```

| Field | Holds |
|---|---|
| `schema_version` | The version of this shape |
| `preflight_version` | The Preflight version that wrote the report |
| `site` | The site scanned. `null` with `--path` |
| `rules` | When the target's rules were last checked, and against what |
| `python` | The Python version that read the code |
| `frappe_version` | The frappe version on the bench. `null` with `--path` |
| `severity` | The lowest level included in `findings` |
| `fail_on` | The `--fail-on` level |
| `verdict` | `pass` or `fail`, the same answer as the exit code |
| `summary` | Counts: the findings per severity, `below_severity` for those `--severity` hides, `suppressed`, `baselined`, and the `upstream` and `ran_patches` findings at or above `severity` |
| `apps` | Apps that were scanned |
| `missing_apps` | Installed apps with no code on the bench |
| `findings` | One entry per counted finding, with its rule details |
| `upstream` | One entry per app on frappe's version branch, with its branch and its findings |
| `ran_patch_findings` | Findings in patches Patch Log records as run |
| `unparsable_files` | Files Python could not parse |
| `unreadable_files` | Files or apps that could not be read, each with the reason |
| `not_checked` | Checks that were skipped, each with the reason |

In each finding:

| Field | Holds |
|---|---|
| `fix` | `before` or `with-upgrade`, or `null` |
| `shim` | The snippet that runs on both versions, or `null` |
| `app` | The app the finding is in, or `null` when it is in none, such as a site record |
| `source` | Where it was read: `app`, `site` or `bench` |
| `file` | The file from the app's repository root, or the record's name |
| `line` | The line, or `null` when there is none |
| `stops_migrate` | `true` in a patch the site has not run yet |

## SARIF

`--format sarif` prints SARIF 2.1.0, for code scanning tools that put each finding on its line.

- Only findings in an app's files are in it. Code scanning places a result in a file, so findings on site records, the bench and an app's upstream remote are left out and counted in a note. The text and JSON reports list them.
- Code scanning needs a line for each result, so a finding with no line of its own, such as a key missing from `pyproject.toml`, is placed on line 1.
- With one app, as `--path .` from its checkout, each file is from the app's repository root. With several, it starts with the app's folder.

## HTML

`--format html` prints one page that loads nothing from the network. Save it and open it in a browser:

```bash
./env/bin/preflight --site mysite.local --target v16 --format html > report.html
```

`--open` writes the same page to a temporary file, prints its path to stderr and opens it in the browser. A scan that does not run, such as one given a wrong site, opens nothing.

- **One card per rule.** The card shows the rule's title and the fix, labelled with when it can go in, and the shim when the rule has one. Error cards start open.
- **Files are grouped.** Each file is listed once, with the line numbers of its findings.
- **Why is collapsed.** It holds what breaks, the rule id and the links that prove it.
- **Severity chips** at the top count the findings and filter the page to one level.
- **The filter box** narrows the page to the rules and files that match what you type. `/` jumps to it.
- **Upstream apps, patches already run, Not scanned and Not checked** show above the cards, the same as in the text report.
