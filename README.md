# Preflight

Scans a Frappe site before a major version upgrade and lists what will break: removed and renamed
APIs in its apps, site scripts and customisations, and what the bench needs for the new version. It
changes nothing on the site.

## Install and run

From the bench directory, into the bench's own environment:

```bash
./env/bin/pip install prefly
./env/bin/preflight --site mysite.local --target v16
```

For CI, scan an app's checkout with no site or bench:

```bash
pip install prefly
preflight --path . --target v16
```

A clean report means no known problems were found, not that the upgrade is safe.

## Docs

- [Overview](https://github.com/kaulith/preflight/blob/main/docs/overview.md): what it checks, options, exit codes, limits
- [Getting started](https://github.com/kaulith/preflight/blob/main/docs/getting-started.md): install, the first scan, CI, suppressing a finding
- [Reading a report](https://github.com/kaulith/preflight/blob/main/docs/reading-a-report.md)
- [Rules](https://github.com/kaulith/preflight/blob/main/docs/rules.md)
- [Upgrade checklist](https://github.com/kaulith/preflight/blob/main/docs/upgrade-checklist.md)
- [Writing a rule](https://github.com/kaulith/preflight/blob/main/docs/writing-a-rule.md)
- [How it was tested](https://github.com/kaulith/preflight/blob/main/docs/how-it-was-tested.md)

## License

MIT
