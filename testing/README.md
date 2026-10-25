# Testing plan

`pytest tests/` proves the scanners do what the rules say. It runs on both bench envs (Python
3.14) and on Python 3.10 without frappe, the floor of Preflight's `requires-python`. It cannot say
whether a rule is true of a real app, whether the report is readable, or what the upgrade breaks
that no rule covers. Four loops do that, each with its own output and its own pass criteria.

## Rule 0: nothing under `~/company_projects` is written

The three benches are working benches. This plan reads their checkouts once, to copy source
trees out, and writes nothing into them: no symlink, no `apps.txt` line, no pip install, no
site, no backup file, no branch switch.

The scripts, the frozen expectations, the probe app and the six write-ups live in `testing/` in
this repo. The corpus they scan lives outside it, in `~/preflight-corpus`, or in
`$PREFLIGHT_CORPUS` when that is set. Everything else they run against is rebuilt under
`~/preflight-test`, which is disposable:

```
~/preflight-test/
  venv/                 python3.14 venv, preflight installed editable, no bench, no site
  bench/                the throwaway bench, built only for loop C
  results/              reports, expectation files, triage notes
  bin/                  the harness scripts, copied from testing/bin
```

Cleanup is `bench --site v15.preflight.test drop-site --force` in the bench, then
`rm -rf ~/preflight-test`. Nothing else is left behind. The folder name drops the space; bench
and pip both handle a space badly.

One-time setup:

```
mkdir -p ~/preflight-test/results
cp -R testing/bin ~/preflight-test/bin
/opt/homebrew/bin/python3.14 -m venv ~/preflight-test/venv
~/preflight-test/venv/bin/pip install -e ~/code/personal/preflight
```

The harness runs the newest python on the machine, 3.14, because the scanners parse source
written for v16 and a file the parser chokes on is scanned as clean. Any 3.14 with pyyaml,
packaging and semantic-version will do, and a v16 bench's `env/bin/python` has all three. The
scripts run from the repo root:

```
PYTHONPATH=testing/bin:. python testing/bin/corpus_scan.py          # write testing/expected/<tree>.json
PYTHONPATH=testing/bin:. python testing/bin/corpus_scan.py --check  # compare with it, exit 1 on drift
```

Loop C's bench starts on python3.11 for v15 and is rebuilt on 3.14 for v16, in C5.

The corpus is one clone per tree at the commit its `testing/expected/<tree>.json` records, with
that hash in `<tree>.commit` beside it, so a rerun means the same thing. The repos: frappe/frappe
for frappe-v15 and frappe-v16, frappe/erpnext for erpnext-v15 and erpnext-v16, bwhtech/hive for
bwh_hive, and frappe/<tree> for crm, helpdesk, hrms, wiki, print_designer, telephony and caffeine.
One tree, rebuilt:

```
corpus=${PREFLIGHT_CORPUS:-~/preflight-corpus}
git init -q $corpus/erpnext-v15
git -C $corpus/erpnext-v15 fetch --depth 1 https://github.com/frappe/erpnext.git <commit>
git -C $corpus/erpnext-v15 checkout FETCH_HEAD
echo <commit> > $corpus/erpnext-v15.commit
```

## Loop A: differential, against the app's own v16 branch

What it proves: precision. A finding on the v15 tree is worth reporting if the app's
maintainers had to change that code to run on v16.

Pairs available on this machine: erpnext (v15 line vs v16 line) and frappe (same). Both are
already in the corpus.

`testing/bin/differential.py`, as built, run from the repo root as
`PYTHONPATH=testing/bin:. python testing/bin/differential.py erpnext frappe`:

1. Scan `<app>-v15` in the corpus with `harness.scan_tree`, which runs `app_scan.scan_app`, the
   scan `--path` runs, with no site. It hands the hooks scanner the app path; without it an
   `override_subclass` rule reads every tree as clean, which is how the Phase 14 re-freeze
   flattered itself.
2. Scan `<app>-v16` the same way, and compare the two sets per rule and per file. The
   scanner is what is under test, so survival is decided by rescanning rather than by searching
   for the matched token, which would be a second, worse copy of the scanner.
3. Per rule: `fixed` (fired on v15, not on v16, with `file_gone` saying whether the file itself
   left the tree), `survived` (fires on both), `only_v16` (fires on v16 alone).
4. Every `survived` file gets a one-word human verdict: `leftover` (the app carries dead or
   broken code, a true positive nobody has acted on), `noise` (the rule is wrong about this
   code) or `by_design` (the rule fires on a declaration or a dumpster string, which is what its
   severity already says).

Run it on the newest python on the machine, and read the unparsable count it prints first. On
python 3.11 the first run called `frappe.db.value_cache` gone from v16's `model/document.py`
because 3.11 cannot parse those files, and an unparsable file counts as clean.

Output: `results/differential/<app>.json`, a per-rule table on stdout, and the verdicts in
`results/differential/notes.md`.

`fixed` flatters any rule whose removed module is in the tree being scanned: half the blog hits
on v15 frappe are inside `frappe/website/doctype/blog_post/` itself. A custom app never holds the
module it is reported for, so only the consumer files count as evidence.

Pass: no rule has a `noise` verdict. A rule that gets one is narrowed or dropped in the same
change, with the finding that produced it quoted in the ROADMAP entry.

Known answers to check the harness against, from the Phase 8 run: erpnext's `leaderboards`
hook and `frappe.ui.form.on("Newsletter")` in `public/js/newsletter.js` must both come out
`survived` and be marked `leftover`; `frappe.db.value_cache` in frappe's own
`model/document.py` must come out `survived` and be marked `noise`, because v16 writes it the
nested way and the rule still fires.

What it cannot do: it grades what maintainers changed, not what breaks. Loop C does that.

## Loop B: corpus noise profile

What it proves: the report is readable on a real app, and a rule change moves only what it
was meant to move.

`testing/bin/corpus_scan.py` runs the same scan over every tree in the corpus, with no site,
and writes `testing/expected/<tree>.json`: every finding as `(rule id, file, line, snippet)`,
sorted, the commit the tree was copied at, the unparsable files, and a count per rule both ways,
with tests and with `--skip-tests`. The table on stdout prints them as `skipped/total`, so a
rule that lives only in test files is visible as `0/263`. `--check` rescans and exits 1 on
drift, naming each finding that appeared or disappeared, and flagging a tree whose commit has
moved under the frozen file. It loads the v16 rules only; freezing v17 waits for the v17 backlog.
Last refrozen on 25 October 2026, with the 95 v16 rules; `--check` exits 0.

Two uses:

- **Noise.** Any rule with more than 50 findings in one app is looked at: is it an `info`, is
  it already covered by `--skip-tests`, or is the matcher too broad? `get_test_records` at 224
  findings in erpnext is what produced `--skip-tests`, and that decision should come from a
  count, not a guess.
- **Drift.** After any rule or scanner change, rerun and diff against the committed
  expectation files. Every added or removed finding is either intended and named in the
  ROADMAP entry for that change, or a regression. This is the cheap check that Phase 9's
  "both benches report what they did before" was, made repeatable and app-wide.

Pass: the diff is empty, or every line of it is accounted for in the change's ROADMAP entry.

## Loop C: the real upgrade

What it proves: recall. A and B cannot see a break that no rule covers; this is the only loop
that can.

Built in `~/preflight-test/bench`, never in a company bench.

**Prerequisites:** the mariadb root password for `bench new-site`, and mariadb and redis up. No
service gets started here, and no `bench start`, `watch`, `worker` or `schedule`; every step is a
one-shot command.

### C1. Build the v15 side

```
bench init --frappe-branch version-15 --python /opt/homebrew/bin/python3.11 --skip-assets ~/preflight-test/bench
cd ~/preflight-test/bench
bench get-app --branch version-15 --skip-assets erpnext
env/bin/pip install -e ~/code/personal/preflight
bench new-site v15.preflight.test --db-root-password root --admin-password <you pick>
bench --site v15.preflight.test install-app erpnext
bench --site v15.preflight.test set-config allow_tests true
```

The bench wants redis on 11000 and 13000 and nothing serves those, so point it at the standalone
redis that is already running, on its own database numbers; that starts no service and leaves the
three working benches, on 11004/13004, 11006/13006 and 11008/13008, alone:

```
bench set-config -g redis_cache "redis://127.0.0.1:6379/10"
bench set-config -g redis_queue "redis://127.0.0.1:6379/11"
bench set-config -g redis_socketio "redis://127.0.0.1:6379/12"
```

### C2. Install the probe app

`bench new-app` prompts, so write the app by hand: `pyproject.toml`, the package, `hooks.py`,
`modules.txt`, and a module directory holding `__init__.py`. Then
`env/bin/pip install -e apps/upgrade_probe` and a line in `sites/apps.txt`. `bench setup
requirements` refuses an app that is not a git repository, so `git init` it, with no commit.

The app is deliberately made of the things the rules name: imports of the removed modules, a
`has_permission` hook that returns True only for the owner, an `override_doctype_class` whose
class subclasses `Document` instead of the controller, a `leaderboards` hook, a flat-key
`value_cache` read, and the deprecated helpers. Imports of removed modules go inside the function
that needs them, so one probe failing does not take the module down with it.

Each one gets a test, so "did it break" is a test result and not an opinion, and three hazards no
rule covers go in on purpose: a default-ordered read taken as the oldest row, a removed doctype
named in raw SQL, and the override reaching a controller method. This app is the instrument; it
is what makes recall measurable at all, because a real client site is not available here.

### C3. Seed the site customisations

Through the desk or `bench --site v15.preflight.test console`, one of each thing the schema
rules claim: a Custom Field on Newsletter, a link field on Contact pointing at Blog Post, a
Property Setter on Energy Point Log, a Server Script using `frappe.get_test_records`, a
Client Script on Blog Post using `frappe.energy_points`.

### C4. Record the prediction, and the baseline

```
env/bin/preflight --site v15.preflight.test --target v16 --format json \
  > ~/preflight-test/results/upgrade/before.json
env/bin/preflight --site v15.preflight.test --target v16 \
  > ~/preflight-test/results/upgrade/before.txt
cd sites && ../env/bin/python ../../bin/run_probes.py v15
```

The probe run comes before the upgrade, not after. The first time through, the branch switch was
already running when the runner was written, so there is no v15 baseline for the two silent
changes; the assertions in the probe tests carried the old values instead, which worked but was
luck.

### C5. Upgrade

```
git -C apps/frappe fetch --depth 1 upstream version-16:version-16 && git -C apps/frappe checkout version-16
git -C apps/erpnext fetch --depth 1 upstream version-16:version-16 && git -C apps/erpnext checkout version-16
find apps/frappe apps/erpnext -name "__pycache__" -type d -prune -exec rm -rf {} +
find apps/frappe apps/erpnext -type d -empty -delete
rm -rf env && bench setup env --python /opt/homebrew/bin/python3.14
env/bin/pip install -e apps/frappe -e apps/erpnext -e apps/upgrade_probe -e ~/code/personal/preflight
bench --site v15.preflight.test clear-cache
bench --site v15.preflight.test migrate > ~/preflight-test/results/upgrade/migrate.log 2>&1
```

Four things the written plan got wrong, each found by running it:

- `bench switch-to-branch` dies on `git fetch --all --unshallow` against a shallow clone whose
  only remote is called `upstream`, so fetch and check out the branch directly.
- v16 needs python 3.14 (`>=3.14,<3.15`), so the env is rebuilt on 3.14; `bench setup env --python` on an
  existing env does nothing, hence the `rm -rf env`. v15 ran on 3.11, which is why the bench was
  built that way.
- The removed modules survive the checkout as directories holding only `__pycache__`, which makes
  them namespace packages with no `__file__` and kills migrate inside `frappe/model/sync.py`.
  Deleting the caches and then the empty directories is what fixes it.
- `bench setup requirements` stops at the first app it cannot read as a git repository, so the
  apps go in with pip directly.

### C6. Collect what actually broke

- `migrate.log`: every traceback and every patch that failed, and the orphaned doctypes it names.
- `run_probes.py v16`: one line per probe, the value it returned or the exception it raised, next
  to the v15 baseline from C4.
- `bench --site v15.preflight.test run-tests --app upgrade_probe`: one failure per broken API.
  A total break hides the rest, so expect to fix it and run the suite twice; the override that
  does not subclass failed every `setUp` and masked all 13 tests.
- The Error Log rows the migrate and the test run left.
- What migrate did to the seeded customisations, and to the data under a removed doctype: the
  customisation rows all survive, the tables survive, and single doctypes keep their rows in
  `tabSingles`, so raw SQL answers while the ORM raises. That sentence is now in the five
  doctype rules.
- A desk smoke pass with agent-browser, `--session preflight-upgrade`, on the list views of
  the doctypes the probe app touches. Needs `bench build`, which `--skip-assets` left undone.
  Ran on 25 October 2026 on a second bench built with assets, frappe 15.124.0 to 16.53.0 with
  fifteen planted desk customisations: `testing/results/desk-smoke.md`.

### C7. Score it

Two numbers, written to `results/upgrade/score.md`:

- **Missed**: a break with no matching finding in `before.json`. Each one becomes a rule, with
  the traceback as its `references` entry and a line in the violations fixture, in the same
  change.
- **Predicted but fine**: a finding whose code ran unchanged after the upgrade. Each one gets
  a verdict: severity too high, matcher too broad, or correct-but-latent (the code path was
  never exercised, which is not the rule's fault).

Pass: zero missed breaks left without a rule, and every predicted-but-fine finding carries a
verdict.

### C8. Tear down

`bench --site v15.preflight.test drop-site --force` if the database matters to you, then
`rm -rf ~/preflight-test/bench`. The site lives only in this bench's own mariadb databases, so
dropping the site is what cleans the database side.

## Loop D: rule sourcing from the upgrade history

What it proves: coverage of what v16 actually removed, rather than of what the wiki wrote
down. The wiki gave two claims in Phase 2; one was wrong and one was understated.

Over `corpus/frappe-v16`, with the v15 tree beside it:

```
git -C ~/company_projects/v16-bench/apps/frappe log --oneline v15.x.x..version-16 \
  -- frappe/deprecation_dumpster.py
git -C ~/company_projects/v16-bench/apps/frappe log --oneline v15.x.x..version-16 \
  -- frappe/patches/v16_0/
```

plus a diff of the public surface: every name exported from `frappe/__init__.py`,
`frappe/utils/__init__.py` and `frappe/model/document.py` on v15 that is absent on v16.
Each hit is a rule candidate that arrives with its own reference, which is what the ground
rules ask for. `switch_default_sort_order.py` is what that looks like when it works.

Pass: every entry in v16's `deprecation_dumpster.py` is either a shipped rule or a line in the
ROADMAP saying why it is not one.

## Order and cost

A first: one script over trees already on disk, grades every rule at once, no site, and it
gives B its triage baseline. B next, same harness, one more script. D is reading, an afternoon.
C last and only once A and B have stopped finding cheap problems, because it is a bench build,
a site, a probe app and a day.

## Where the results live

Each loop's run gets a ROADMAP entry in the same shape as a phase: what ran, what it found,
what changed because of it, and the exit line with the numbers. What is kept in the repo is what
a rerun needs: `testing/bin` (the four scripts), `testing/expected` (the frozen corpus, which is
what `--check` compares against), `testing/upgrade_probe` (the instrument, reusable for a v17
target), and `testing/results` (the six write-ups). The venv, the bench and the site are rebuilt
from the commands above and die with `~/preflight-test`; the corpus trees live in
`~/preflight-corpus`.
