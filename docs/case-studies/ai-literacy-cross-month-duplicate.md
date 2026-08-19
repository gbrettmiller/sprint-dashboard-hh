# Case Study: Catching a Hidden Data Bug with AI — A Human-in-the-Loop Walkthrough

**Status: Resolved** — Underlying fix shipped as issue #34, merged to `master` on 2026-06-03 (commit `5637327e2`).

This is an AI-literacy case study. It walks through a real bug we found and fixed on the Sprint Metrics Dashboard while working with Claude Code, and uses it to show what *structured* AI-assisted development looks like — reading project doctrine first, fixing the right layer, verifying claims, and keeping a human at every decision point. It is deliberately light on code; the point is the workflow, not the syntax.

---

## TL;DR

A team member spotted a visual oddity on the dashboard. Working with Claude Code, we traced it to a stale duplicate record, **confirmed the truth against GitLab** rather than guessing, and fixed both the bad data *and* the underlying code bug that created it. We verified the fix three ways and shipped it with a full audit trail — all in a single short session. The thread running through it: project **doctrine** decided *where* the fix belonged, which is what separates structured AI use from "vibe-coding."

---

## The Setup

The Sprint Metrics Dashboard shows our teams' sprint health — burndown, velocity, issue breakdowns — pulled automatically from GitLab. Nobody types data into it; a scheduled job collects it each hour and commits JSON files the website reads.

While looking at the May view, a team member noticed something that *looked wrong*: the MIRARS sprint **"v3.3.1.0" appeared twice**. It showed up in the May sprint dropdown where it didn't belong, and it produced a phantom, empty bar on the velocity chart.

That instinct — "that doesn't look right" — is where the entire fix began. No automated check flagged it. A human did.

---

## The Investigation

Claude started by reading the data files behind the chart. It quickly found the culprit: the **same sprint** (internally, milestone id `2892`) was sitting in *two* monthly data files at once — April **and** May — with conflicting dates, status, and completion counts.

| Where the record lived | Dates | Status | Work done |
|---|---|---|---|
| April file | Apr 17 → Apr 30 | closed | 47 issues / 70 points |
| May file | Apr 16 → May 1 | active | 0 / 0 |

So which one was real? **Here is the key judgment moment.** Rather than guess — or trust whichever file looked more complete — we checked the **authoritative source**: Claude queried GitLab directly for milestone 2892. GitLab's answer was unambiguous: **v3.3.1.0 is closed, dated Apr 17 → Apr 30.** That made the April record correct and the May record an imposter.

Claude then scanned the *entire* dataset — every group, every project, every month — to confirm this was the **only** occurrence. It was. That scope check matters: it's the difference between "I fixed the thing you saw" and "I confirmed how widespread the thing is."

---

## Root Cause

The collector that writes these files de-duplicated records only *within a single month's file*. When this sprint's end date briefly shifted across a month boundary (Apr 30 → May 1, then back), the collector wrote a fresh copy into the new month — but never removed the old copy from the previous month.

In plain terms: imagine filing the same form into both the **April** and **May** folders because its date changed mid-month, and never going back to pull the outdated copy.

This is also where doctrine earns its keep. The project's architecture spec, `ARCHITECTURE.md`, defines a monthly file as holding *"all sprints **ending** in that month."* The orphaned record violated that written rule. Doctrine didn't just describe the file structure — it defined the invariant the data had broken, which made the bug easy to name precisely.

---

## Doctrine Decided *Where* the Fix Belongs

This is the heart of the case study.

The bug *appeared* on the velocity chart — a frontend, in-the-browser feature. The fast, tempting fix is to make the symptom disappear right where you see it: add a "remove duplicates" filter to the chart's JavaScript. The chart would look correct, and you'd move on.

Project doctrine overruled that instinct. Two rules, written down before any of this happened:

- `VECTOR.md` (project principles): **"Collection is separate from display."**
- `ARCHITECTURE.md` (technical spec): **"Data is pre-computed, not computed at request time. The browser does display logic only."**

If the browser only *displays* data, then a data-correctness problem is **not** a display problem. The correct fix is at the **source** — the data collector — so that *every* view is right: the chart, the dropdown, and any feature built later. Patching the chart would have hidden the bug in one place while leaving the bad data to resurface everywhere else.

| | Vibe-coding instinct | Doctrine-driven choice |
|---|---|---|
| Where to fix | Patch the chart code where the bug was seen | Fix the data collector at the source |
| Result | Symptom hidden in one view | Cause removed for every view |
| Guided by | Whatever's fastest | `VECTOR.md` + `ARCHITECTURE.md` layer rules |

Doctrine told us *where the fix belongs.* That single decision is the clearest illustration of structured AI use versus ad-hoc coding in this whole story.

---

## The Fix

Two parts, both at the right layer:

- **Data:** removed the stale May copy. The correct April record stayed exactly as it was.
- **Code:** taught the collector to remove any matching record from *other* monthly files before writing — so a date change can never strand an orphan again.

The change stayed deliberately small, again following `VECTOR.md`'s principles:

- **Smallest working thing** — one new helper function beside the existing one; no rewrite of the collector.
- **Fit the existing grain** — the new function uses the project's Python naming style, and we matched the exact JSON formatting of the existing files (down to checking the file's raw bytes so we wouldn't even introduce a stray blank line).
- **Leave the campsite cleaner** — we touched only the affected area, and resisted "while we're in here" refactoring.

---

## Verifying It Actually Worked

AI suggestions are not self-certifying. We checked the fix three ways:

1. A syntax check on the changed script.
2. A re-scan of the **entire** dataset — confirming **zero** cross-month duplicates remained.
3. A small functional test that recreated the exact orphan scenario and proved the new logic removes it.

This also satisfies a written **Quality Gate** in `VECTOR.md`: for Python changes, "JSON output schema [is] verified against dashboard expectations." Verification wasn't optional politeness — it's part of the project's definition of *done*.

---

## Shipping with a Paper Trail

The work followed the project's prescribed workflow, not an improvised one:

1. Create a feature branch.
2. **Create the GitLab issue (PBI #34) up front**, before writing code.
3. Implement the fix.
4. Commit with a conventional, signed commit message.
5. `git pull origin master` **before** pushing (the pipeline commits frequently; pulling first avoids conflicts).
6. Merge and push. The commit's `Closes #34` reference auto-closed the issue.
7. Add a closing comment documenting the fix and verification.

Every step here is doctrine:

- The order *branch → PBI → implement* is the workflow defined in `CLAUDE.md` and project memory.
- Conventional commit messages and *pull-before-push* are `CLAUDE.md` git rules.
- And most tellingly: `VECTOR.md` lists a **non-negotiable** — *"Never commit changes unless explicitly asked."* That is exactly why, after implementing, the AI **stopped and waited**. It did not commit, merge, or push until the human explicitly said "commit, merge, push."

The audit trail — issue, branch, signed commit, comment — is something management and teammates can review later. It isn't an afterthought; doctrine prescribed it.

---

## Where the Human Steered

AI did the legwork. The human owned the decisions. Here's the division of labor — and the doctrine governing each moment:

| Moment | Human | AI | Doctrine |
|---|---|---|---|
| Noticing the anomaly | ✅ spotted it | — | — |
| Reading doctrine before acting | — | ✅ | VECTOR: "doctrine before code" |
| Deciding scope (data-only vs. root-cause) | ✅ chose root-cause | proposed the options | VECTOR: "raise concerns before acting" |
| Choosing *where* to fix | reviewed | ✅ followed the layer rules | ARCHITECTURE: collection vs. display |
| Requiring a PBI first | ✅ team workflow | followed it | CLAUDE.md issue workflow |
| Tracing / scanning / testing | reviewed | ✅ did the work | VECTOR Quality Gates |
| Verifying against GitLab truth | ✅ insisted | executed | — |
| Deciding to commit | ✅ gave the go | ✅ held until told | VECTOR non-negotiable |

---

## How Long Would This Have Taken by Hand?

To put the productivity gain in perspective, here's a grounded estimate of how long this would take a **mid-level developer who already knows the project** to do manually — assessment through implementation, plus the "admin" overhead that real work always carries.

| Phase | Manual estimate |
|---|---|
| Triage & reproduce — open the dashboard, isolate which sprint and which data files are involved | 20–30 min |
| Investigate & confirm root cause — find the duplicate across two files, query GitLab for the authoritative answer, and work through the practical snags (the milestone's internal id vs. display id, the C/GOTS token-scoping nuance) | 60–90 min |
| Dataset-wide scope check — write a scan to confirm the problem is isolated, not systemic | 20–30 min |
| Design & implement the fix at the right layer | 45–75 min |
| Verify — write a functional test, re-scan the full dataset, syntax-check | 30–60 min |
| Data cleanup — remove the orphan and match the exact file formatting | ~15 min |
| Admin — create the PBI with acceptance criteria, branch, signed commit, pull-before-push, merge, close the issue with a note | 30–45 min |
| Documentation updates | 20–30 min |
| **Total** | **≈ 4–6 focused hours** — realistically a **half- to full working day** once normal interruptions and context-switching are counted |

By contrast, the **AI-assisted session ran start to finish in well under an hour** of elapsed time — and most of *that* was the human reviewing findings and making the scope and process calls, not waiting on mechanical work.

**Three honest caveats**, so this comparison stays credible:
- The estimate assumes a developer who knows the codebase and doesn't get badly stuck; an unfamiliar developer would take considerably longer, and a rushed one might "fix" only the chart and miss the root cause entirely.
- It **excludes** the time to write *this* case study — that's a bonus deliverable, not part of the fix.
- The AI did not replace the developer's judgment. A human still noticed the bug, chose the root-cause path, required the PBI, and authorized the commit. What the AI compressed was the *legwork*: searching files, cross-checking the API, scanning the whole dataset, writing the test, and matching formatting exactly. The speed-up is in execution, not in deciding what's worth doing.

---

## Lessons Learned

Reusable takeaways, each tied back to how we work:

- **Doctrine before code beats vibe-coding.** The AI read the project's `VECTOR.md`, `ARCHITECTURE.md`, and `CLAUDE.md` first — which is *why* it fixed the right layer instead of the convenient one.
- **Let architecture decide where a fix lives.** "Collection is separate from display" turned a tempting UI patch into a correct source fix.
- **Trust, but verify against ground truth.** We confirmed the real answer against GitLab, not against the files we happened to be handed.
- **Fix causes, not symptoms.** Ask the AI for the root cause — and whether the problem can recur.
- **Bound the blast radius.** Have the AI check whether an issue is isolated or systemic before declaring victory.
- **Smallest working thing.** Doctrine kept the change tight — no opportunistic refactor riding along with the fix.
- **Keep humans at the decision points.** The AI surfaces options and raises concerns; the human owns scope, process, and the commit.
- **The paper trail is part of the work.** Issue, branch, signed commit, pull-before-push, and a closing comment — all prescribed, all reviewable.
- **Your eye for "that looks wrong" is still the trigger.** This entire fix started with a person noticing a chart oddity.

---

## Appendix (optional — technical)

**What is "doctrine" here?** Three documents at the repository root that the AI is expected to read before writing any code:

- `VECTOR.md` — project identity, the "contractor model" for working with AI, and the Seven Principles (plus non-negotiables like "never commit unless explicitly asked").
- `ARCHITECTURE.md` — the technical specification: layers, the one-way data flow (`GitLab API → Python → JSON → browser`), naming conventions, and testing rules.
- `CLAUDE.md` — the agent briefing: the issue-management workflow, git rules, and data schema.

**The core of the code fix** — a new guard added to the collector (`scripts/scheduled_update.py`), called once before a sprint record is written:

```python
def remove_sprint_from_other_month_files(target_path: Path, sprint_id):
    """Remove any record with sprint_id from sibling month files (not target_path).

    A sprint whose end_date changes across a month or fiscal-year boundary files
    under a new month, but the stale record in its previous month file is never
    cleaned up by the within-file upsert. This strips those orphans so a sprint id
    appears in at most one month file within its group/project scope.
    """
    scope_root = target_path.parent.parent
    for other in scope_root.glob("fy*/*.json"):
        if other == target_path:
            continue
        # ...load the file, drop any record with this id, write it back...
```

**Links:**
- Issue: [#34 — Fix: cross-month sprint duplicate](https://git.example.com/tinkers/sprint-metrics-dashboard/-/work_items/34)
- Fix commit: `5637327e2` · Merge: `0d2592d4e`
