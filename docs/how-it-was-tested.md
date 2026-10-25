# How it was tested

Unit tests show the scanners do what the rules say. They can't show whether a rule is true for a real app. Four more checks did that.

| Check | Question it answers |
|---|---|
| Version comparison | Does a rule fire on code that really had to change? |
| Many apps | Is the report readable on real apps? |
| A real upgrade | What breaks that no rule caught? |
| Deprecation list | Is everything v16 deprecated covered? |

## 1. Version comparison

Scanned the v15 and v16 versions of frappe and erpnext with the same rules, then compared.

- A finding that is gone on v16 means the maintainers had to fix that code.
- A finding still there on v16 was read by hand.
- **Result:** one rule, `v16-sanitize-html-strips-tags`, was lowered from warning to info. No rule was dropped.

## 2. Many apps

Scanned twelve app trees: two versions each of frappe and erpnext, plus crm, helpdesk, hrms, wiki, print_designer, telephony, caffeine and bwh_hive.

- Test files caused almost all the noise. `FrappeTestCase` alone had 263 findings in frappe and 163 in erpnext.
- Outside the test helper rules, a rule passed 13 findings only in frappe's own two trees and in erpnext v15. frappe reports its own Octicons stylesheets, and on v15 the modules v16 moved out naming themselves. erpnext v15 has 84 for `v16-sql-function-string-fields` and 26 for `v16-erpnext-moved-settings`; erpnext's version-16 branch has 2 and 6.
- That is why an app on frappe's version branch, such as erpnext, is listed apart as upstream: the branch switch replaces that code.
- Every finding is saved, and the set was refrozen on 25 October 2026 with the 113 v16 rules. After any rule change, a rescan shows exactly what moved.

## 3. A real upgrade

Built a throwaway v15 site with erpnext and a test app that uses the APIs the rules name. Upgraded it to v16 and ran the test app's tests.

**Predicted and confirmed: 9**

- 6 raised an error, such as `ModuleNotFoundError` and `DoesNotExistError`.
- 3 were silent: a permission hook that started denying, a cache read that returned nothing, and a gravatar helper that returned a different value.

**Not predicted: 4**

- v16 needs Python 3.14.
- Leftover folders from removed modules stop `bench migrate`.
- `bench migrate` rewrote `sites/apps.txt` and dropped Preflight, which then installed as a bench app.
- One test helper failed for a different reason than its rule gives.

The first two are in the [upgrade checklist](upgrade-checklist.md). The Python version is now a rule too, `v16-bench-python`.

**Then clicked through the desk.** A second throwaway site, built with assets: frappe 15.124.0 and erpnext 15.124.1, upgraded to frappe 16.53.0 and erpnext 16.52.1. Fifteen customisations aimed at the desk were planted on v15, such as Client Scripts, Custom HTML Blocks on a workspace, and a Custom Field placed after a field v16 removes. About thirty pages were opened on v15, where all of them worked, and again on v16.

- All fifteen broke on v16 the way their rule says. Most raised an error dialog or a console error; a Custom Field moved to the end of its form, and an octicon rendered as nothing.
- Two breaks had no rule. Repost Allowed Types: a doctype left unchecked on v15 can be reposted on v16, through an ERPNext bug. And a custom public workspace no longer shows in v16's navigation. Both have a rule now.
- A follow-up on the same site found three more ways a workspace drops out of v16's navigation: a private one, which v16 lists only under My Space, hidden for every user by default; a public one in a custom module, which no app's rail lists; and one an app ships without `add_to_apps_screen`, which gets no tile. Each is now a rule, and each fix was checked in the desk.
- One message was wrong. `frappe.get_doc` on a doctype the upgrade removed raises `ImportError`, not `DoesNotExistError`; only a query raises that. The removed doctype rules now say both.

## 4. Deprecation list

Compared the rules against every entry in v16's deprecation list.

- 32 of 36 entries have a rule.
- The other 4 are listed under [Not covered](rules.md#not-covered).

## Where the details are

The scripts and full results are in the [`testing/`](../testing/README.md) folder of the repository.
