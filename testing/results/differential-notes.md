# Loop A triage

Run: `PYTHONPATH=testing/bin:. python testing/bin/differential.py erpnext frappe` from the repo root,
python 3.14.
erpnext v15 `31803451f1` → v16 `69063c4024`, frappe v15 `5e57d292b1` → v16 `4f40f4acbb`.
Both pairs are the same release line, backports of the same PR.

Every finding whose file still fires the same rule on the v16 tree, with a verdict.

## erpnext

| rule | file | verdict |
|---|---|---|
| v16-deprecated-get-number-format-info | accounts/utils.py | leftover; v16 erpnext still imports it, and `quality_inspection.py` is the sibling call site that did change |
| v16-deprecated-read-multi-pdf | regional/report/irs_1099/irs_1099.py | leftover; deprecated in v16, removed in v17 |
| v16-removed-leaderboards-hook | hooks.py | leftover; nothing in v16 frappe reads the hook |
| v16-removed-newsletter-doctypes | public/js/newsletter.js | leftover; form script for a doctype the framework no longer ships |
| v16-sanitize-html-strips-tags | templates/pages/search_help.py | noise |

## frappe

| rule | file | verdict |
|---|---|---|
| v16-deprecated-gravatar-helpers | utils/safe_exec.py | leftover; v16 still exposes the helper to server scripts, and it returns "" now |
| v16-has-permission-hook-returns-true | hooks.py | by design; the rule fires on the declaration, which is what its severity is about |
| v16-removed-backup-doctypes | patches/v11_0/set_dropbox_file_backup.py | leftover; stale patch naming Dropbox Settings |
| v16-removed-blog-doctypes | patches/v13_0/set_read_times.py, set_route_for_blog_category.py | leftover; stale patches naming Blog Post and Blog Category |
| v16-sanitize-html-strips-tags | 10 files, `frappe/__init__.py` through `website/doctype/discussion_reply` | noise |
| v16-value-cache-nested | model/document.py | noise by this loop's criterion, accepted; see below |
| v16-deprecated-client-get-js | deprecation_dumpster.py (v16 only) | by design; the dumpster names the deprecated path as a string |

## What changed because of it

`v16-sanitize-html-strips-tags` goes from `warning` to `info`. Eleven uses survive the upgrade
untouched across both apps and not one call site changed; the two that stopped firing left the
tree for unrelated reasons (`blog_post.py` moved out with the blogs app, `www/search.py` is
gone). The behaviour change is real, so the rule stays, but nothing it reports is work.

`v16-value-cache-nested` stays a `warning`. It fires on v16's own nested-correct
`model/document.py`, which this loop grades as noise, but the corpus is the framework and the
framework is already migrated. On the tool's actual input, a pre-upgrade app, every use of
`frappe.db.value_cache` is the flat form and has to change. Narrowing it needs a matcher for a
tuple subscript, for one rule.

## Caveats found in the harness itself

- Survival is measured by rescanning the v16 tree and comparing per rule and per file, not by
  searching for the matched token. The scanner is the thing under test; a token search would
  have been a second, worse implementation of it.
- The first run was on python 3.11 and reported 0 hits where there were 3: v16 frappe files
  that 3.11 cannot parse were counted as clean. The harness now reports unparsable files, and
  must run on the newest python on the machine. Both trees now parse with 0 unparsable.
- `fixed` is inflated for the removed-module rules: 16 of the 32 blog hits on v15 frappe are
  inside `frappe/website/doctype/blog_post/` itself, and the module left the tree. A custom app
  never contains the module it is reported for, so only the consumer files
  (`templates/includes/comments/comments.py`, `www/rss.py`) are evidence.
