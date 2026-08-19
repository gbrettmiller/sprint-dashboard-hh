# Case Study: Adding a Jira Data Source to the Sprint Metrics Dashboard

**Date:** 2026-07-01
**Feature:** Data Services sprint data pulled from Jira (Server/Data Center) — GitLab issue #43
**Tooling:** Claude Code (Opus 4.8)

---

## 1. Executive Summary

The Sprint Metrics Dashboard was originally built to collect data exclusively from
GitLab (Iterations and Milestones APIs). The Data Services program elected to remain on Jira
rather than migrate to GitLab, but leadership still needed Data Services to appear on the same
dashboard as the GitLab-backed programs (Cloud Services, Service Management).

This session added a complete **Jira data-collection path** that produces the exact
same JSON that the GitLab collectors produce, so the dashboard front end renders Data Services
with **zero front-end changes**. The work was planned, implemented, tested against the
live Jira instance, documented, and merged to `master` in a **single working session**.

A mid-level developer with basic Jira familiarity, working conventionally, would be
expected to spend on the order of **7–10 working days (roughly 1.5–2 weeks)** to reach
the same outcome. See Section 5 for the breakdown and assumptions.

---

## 2. The Problem

- The dashboard's data pipeline (Python) understood only GitLab.
- Data Services lives in a **Jira Server/Data Center** instance (`jira.example.com`), which
  differs from Jira Cloud in REST API version (v2), authentication (Personal Access
  Token bearer), and response pagination.
- The dashboard's charts (burndown, velocity, type breakdown, issue tables) depend on a
  specific JSON schema. Any new source has to reproduce that schema **exactly**, including
  a daily burndown series — which GitLab provides via "resource events" but Jira does not.
- The collection runs in a CI/CD pipeline with **no public internet egress** and
  **DoD certificate** requirements, so the new integration had to fit those constraints.

## 3. What Was Delivered

**New components**
- `scripts/jira_api.py` — a Jira Server/DC REST client (bearer-token auth, `startAt`/
  `maxResults` pagination, rate-limit + server-error retry, configurable SSL) mirroring
  the resilience of the existing GitLab client.
- `scripts/jira_provider.py` — converts Jira Software sprints into the dashboard's
  standard sprint record: sprint selection from a Scrum board, issue field mapping, and
  **daily burndown reconstructed from each issue's Jira changelog** (the Jira analog to
  GitLab's resource events).

**Integrations & configuration**
- `scheduled_update.py` and `backfill.py` — added a source dispatch (`source: "jira"`)
  that leaves the existing GitLab path untouched; the FY2026-floored backfill seeds
  history for the velocity chart.
- `public/data/groups.json` — Data Services re-enabled as a Jira group with its board id and
  story-points field.
- `.gitlab-ci.yml` — Jira SSL handling wired into the existing DoD-certificate pattern;
  credentials injected as masked CI/CD variables.
- `CLAUDE.md` — documented the new source, its configuration, and a known limitation.

**Result:** 20 fiscal-year-2026 sprints backfilled and the active sprint published;
output validated to be schema-identical to the GitLab-sourced groups; front end unchanged.

## 4. How It Was Done (Process)

1. **Discovery.** Read the existing GitLab collectors and the front-end data contract to
   pin down the exact JSON schema every chart depends on, and confirmed the front end is
   source-agnostic (so the work could be isolated to the Python layer).
2. **Planning.** Produced an implementation plan and a prerequisites checklist
   (URL, board id, token handling, story-points field, issue-type mapping), and confirmed
   scope: FY26 backfill + ongoing, sprint metrics only (no reports/releases for Data Services yet).
3. **Implementation.** Built the Jira client and provider, then wired source dispatch into
   the two collectors, deliberately keeping file I/O in the existing scripts to avoid
   disturbing the working GitLab path.
4. **Live testing & debugging.** Probed the live instance; **discovered the configured
   story-points field was empty and identified the correct one** by inspecting the field
   catalog; validated that the active sprint's issue count and type mix matched the team's
   own Jira chart; confirmed exact schema parity with existing data files; and found and
   removed **stale GitLab-era placeholder data** for Data Services before regenerating cleanly.
5. **Documentation & handoff.** Updated project documentation, logged a known limitation
   for future work, and filed a follow-up backlog item for report downloads.

## 5. Effort Comparison

The estimate below is for a **mid-level developer with basic (not expert) Jira knowledge**,
working in the normal way (reading docs, trial and error, manual testing). It assumes the
developer is already familiar with Python and this codebase's general shape.

| Phase | Description | Mid-level dev estimate |
|---|---|---|
| Discovery & design | Reverse-engineer the required JSON schema and the front-end data contract; learn the Jira Server/DC + Agile REST APIs; decide the integration approach | 1.5–2 days |
| Jira API client | Auth, pagination model, retry/rate-limit handling, SSL for a DoD host | ~1 day |
| Sprint & issue mapping | Board sprint selection; map issue types, states, story points, keys → the dashboard's fields | ~1 day |
| Burndown from changelog | Research and implement daily burndown reconstruction from the Jira changelog (no direct API for this) — the hardest part, with real debugging | 1.5–2 days |
| Pipeline integration | Source dispatch in both collectors; FY-floored backfill; keep the GitLab path intact | ~0.5 day |
| Config & CI/CD | groups.json, CI variables, DoD-cert/SSL wiring | ~0.5 day |
| Live testing & data quirks | Connectivity, discovering the correct story-points field, validating against real data, cleaning stale legacy data | 1–1.5 days |
| Documentation | Update project docs; record limitations | ~0.5 day |
| **Total** | | **≈ 7–10 working days (1.5–2 weeks)** |

**Delivered with Claude Code:** a single focused session (a few hours of interactive work),
covering all of the above — planning, implementation, live testing, documentation, and a
signed merge to `master`.

Even accounting for the fact that a human's calendar time typically stretches beyond raw
effort (meetings, context-switching, waiting on access), the practical compression here is
substantial — on the order of **one afternoon versus one to two weeks**.

## 6. What Drove the Estimate (Complexity Factors)

- **Two systems, one schema.** The real difficulty was not "call the Jira API" but
  reproducing a schema defined by another system, exactly, so nothing downstream changes.
- **Burndown reconstruction.** Jira exposes no daily burndown series through a stable API;
  it had to be rebuilt from raw issue changelogs, matching the semantics the existing
  charts assume.
- **Instance-specific unknowns.** The correct story-points custom field, issue-type
  taxonomy, and "done" semantics are per-instance and are typically found by trial and
  error against live data.
- **Environment constraints.** DoD certificates, no public egress on CI, and masked-secret
  handling add setup and testing friction that pure application code does not.
- **Legacy data.** Pre-existing placeholder data for Data Services had to be recognized as stale and
  cleaned — a subtle issue that is easy to miss and produces confusing dashboard results.

## 7. Where Claude Code Added the Most Value

- **Fast, accurate discovery** of the existing schema and the source-agnostic front end,
  which correctly scoped the work to the Python layer and avoided unnecessary UI changes.
- **Pattern-faithful implementation** that mirrored the existing GitLab client/collector
  conventions, minimizing risk to the working pipeline.
- **Rigorous live validation** — including catching the wrong story-points field and the
  stale legacy data — rather than assuming the first configuration was correct.
- **Complete handoff** in the same sitting: documentation, a recorded known limitation, and
  a scoped follow-up backlog item.

## 8. Caveats

- Effort figures are estimates for comparison, not a measured benchmark of a specific
  developer.
- The human estimate assumes reasonable but not expert Jira knowledge; a Jira specialist
  would be faster, and someone new to the codebase or the DoD environment would be slower.
- One known limitation remains for a future iteration: issues removed from a sprint
  mid-flight are not returned by the sprint query, so mid-sprint removals may be slightly
  undercounted in burndown (documented in `CLAUDE.md`).
```
