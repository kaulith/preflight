# Getting started

## Install

From the bench directory, into the bench's own environment:

```bash
cd ~/frappe-bench
./env/bin/pip install prefly
```

- **The package is `prefly`; the command is `preflight`.**
- **It is not a bench app.** Don't `bench get-app` it; nothing is installed on a site.
- **`--path` needs no bench.** For it, any Python 3.10 or newer will do: `pip install prefly`.

## Run the first scan

```bash
./env/bin/preflight --site mysite.local --target v16 --skip-tests
```

Read the report in this order:

1. **Not scanned** and **Not checked**, if either is there. They mean the counts are off.
2. **Errors.** These break on the new version.
3. **Warnings.** These need a look.

Each rule ends with its fix. **Fix before upgrading** works on the version you run now, so it can ship today. **Fix with the upgrade** needs the new version, unless the rule shows a shim that runs on both.

Upstream apps and patches the site has already run are listed apart and not counted. [Reading a report](reading-a-report.md#upstream-apps) says why.

`--skip-tests` leaves out test files, which keeps the report short. Run once without it before you upgrade: old test helpers don't affect production, but they do break your test suite.

## Fix one app at a time

```bash
./env/bin/preflight --site mysite.local --target v16 --app my_app --severity error
```

- `--app` can be repeated.
- `--app frappe` scans the framework itself.
- `--app erpnext` counts the findings of an app on frappe's own version branch, which a plain scan lists apart as upstream.
- Site scripts and customisations are always scanned, whatever `--app` says.

## Use it in CI

```bash
./env/bin/preflight --site mysite.local --target v16 --skip-tests --format json > preflight.json
```

With no site or bench, scan the app's checkout. Nothing from frappe is imported:

```bash
preflight --path . --target v16 --skip-tests --format sarif > preflight.sarif
```

On GitHub, this workflow in the app's repository fails a push or pull request that adds an error, and code scanning puts each finding on its line. Code scanning on a private repository needs GitHub Code Security.

```yaml
name: Preflight
on: [push, pull_request]
jobs:
  preflight:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.14"
      - run: pip install prefly==0.1.0
      - run: preflight --path . --target v16 --skip-tests --format sarif > preflight.sarif
      - uses: github/codeql-action/upload-sarif@v4
        if: ${{ !cancelled() }}
        with:
          sarif_file: preflight.sarif
```

- The command exits 1 when it finds an error, so the job fails by default.
- The version is pinned, so a release with new rules can't fail a build that passed. Raise the pin to take them in.
- `--fail-on warning` makes warnings fail the job too.
- `--fail-on never` reports without failing.
- `--format sarif` is for code scanning tools. Findings on site records, the bench and an app's upstream remote are left out of it, since code scanning places each result in a file.
- `--baseline preflight.json` leaves out what an earlier `--format json` report already found, so the job fails only on new findings. A finding matches on its rule, app, file and snippet, so a line that moves still matches.
- The JSON keys are listed under [JSON](reading-a-report.md#json). Read them by key; `schema_version` goes up when one is removed or changes meaning.

## Suppressing a finding

A comment on the finding's own line naming the rule leaves it out, and the report counts it as suppressed:

```python
frappe.db.get_value("Blog Post", name)  # preflight: ignore[v16-removed-blog-doctypes]
```

```js
frappe.energy_points.get_points(user); // preflight: ignore[v16-removed-energy-points-js]
```

- Several rules go in one comment: `preflight: ignore[rule-a, rule-b]`.
- A bare `preflight: ignore` does nothing.
- It works in Python, JavaScript (`//` or `/* */`), SCSS, Vue, `pyproject.toml`, `patches.txt` and site scripts.
- **Don't use it on an `execute:` line of `patches.txt`.** Patch Log records the whole line, comment included, so the next `bench migrate` runs that patch again. Use `--baseline` for those.

## Check the install

```bash
./env/bin/preflight --version
```

The tests are in the repository, not in the package. Clone it at the version installed, then run them with the bench's Python from its `sites` directory:

```bash
git clone --branch v0.1.0 https://github.com/kaulith/preflight ~/preflight
cd sites
../env/bin/pip install pytest
../env/bin/python -m pytest ~/preflight/tests
```

This needs no site. To also run the tests that read a real site:

```bash
PREFLIGHT_SITE=mysite.local ../env/bin/python -m pytest ~/preflight/tests
```

Those tests add a few records, scan them and roll them back. Nothing is saved.

## Python version

Preflight reads code with the bench's Python. A file that Python can't parse is skipped and listed under [Not scanned](reading-a-report.md#not-scanned). Scan from a bench whose Python is new enough for the apps on it.
