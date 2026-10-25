# Upgrade checklist

The steps for a v15 to v16 upgrade, in order. Some of these have no rule, and each one stopped a real test upgrade.

## 1. Scan

```bash
./env/bin/preflight --site mysite.local --target v16 --skip-tests --online
./env/bin/preflight --site mysite.local --target v16 --format json > preflight.json
```

- The first command is the list to fix. `--online` adds the checks that ask the network and the machine: whether each app has a `version-16` branch upstream, whether its dependencies have wheels for Python 3.14, and whether node is new enough.
- The second includes test files.
- If the report has a **Not scanned** or **Not checked** section, sort that out first.
- **Upstream apps** are listed apart. The branch switch in step 4 replaces their code, so their findings are upstream's to fix. On Frappe Cloud no app has a branch checked out, so none is listed apart: pass `--app` for each of your own apps.

## 2. Fix

- **Errors:** fix all of them. They break on v16.
- **Warnings:** read each one. Some are silent changes that reach production unnoticed.
- **Fix before upgrading** goes in now, on v15. **Fix with the upgrade** goes in with step 4, or now behind the shim the rule shows.
- **Moved modules:** install the app that took them, or remove your code and customisations that use them.

| Module | App |
|---|---|
| Newsletter | `frappe/newsletter` |
| Blog | `frappe/blogs` |
| Energy points | `frappe/eps` |
| Offsite backups | `frappe/offsite_backups` |

## 3. Move to Python 3.14

v16 needs Python 3.14. Its `pyproject.toml` says `requires-python = ">=3.14,<3.15"`, so pip refuses to install it on 3.12 or 3.13, and on 3.11 the install fails with a bare `SyntaxError`. The scan reports this as `v16-bench-python`.

```bash
rm -rf env
bench setup env --python python3.14
```

Delete `env` first. `bench setup env` does nothing when the folder already exists.

v15 runs on 3.14 too, so the bench keeps working on the new env until you switch branches.

v16 also needs node 24 or newer, or the branch switch stops when yarn refuses the old node. `--online` reports it as `v16-bench-node`. Install it first, for example `nvm install 24 && nvm alias default 24`; v15 builds with it too.

## 4. Switch branches

```bash
bench switch-to-branch version-16 frappe erpnext --upgrade
```

Each app on the version branch needs a remote named `upstream` with a `version-16` branch, or the switch stops partway. `--online` reports one that has none as `v16-app-target-branch`.

If it fails on `git fetch --all --unshallow`, fetch the branch yourself:

```bash
git -C apps/frappe fetch --depth 1 upstream version-16:version-16
git -C apps/frappe checkout version-16
```

## 5. Clear leftover folders

Do this before migrating. The branch switch leaves empty folders behind for the removed modules, and `bench migrate` then fails with:

```text
TypeError: expected str, bytes or os.PathLike object, not NoneType
```

```bash
find apps/frappe apps/erpnext -name "__pycache__" -type d -prune -exec rm -rf {} +
find apps/frappe apps/erpnext -type d -empty -delete
bench --site mysite.local clear-cache
```

## 6. Migrate

```bash
bench --site mysite.local migrate
```

What migrate does:

- **Removes** leftover workspaces, dashboards, pages and reports.
- **Keeps** your Custom Fields, Property Setters and scripts, even the ones that point at removed doctypes.
- **Keeps** the data. The tables of removed doctypes stay in the database.

## 7. Check

```bash
bench --site mysite.local run-tests --app my_app
```

- Run your own tests, not only the scan. Silent changes only show up in a failing test.
- One big failure can hide the rest. Fix it and run the tests again.
- If tests are not allowed on the site yet:

```bash
bench --site mysite.local set-config allow_tests true
```
