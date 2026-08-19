# Doctrine Audit

**Run date:** 2026-07-02
**Files audited:** VECTOR.md, ARCHITECTURE.md, CLAUDE.md
**Project stage:** production

---

### Findings

#### DRIFT — medium

**1. `ARCHITECTURE.md:Stack` and `API / Data Pattern` describe GitLab-only collection, but a second data source (Jira) is live.**
`groups.json` sets `"source": "jira"` for Data Services, and `scripts/jira_api.py` + `jira_provider.py` implement it. Both scripts already appear in the ARCHITECTURE.md structure tree, so the doctrine is internally inconsistent: the file lists the Jira scripts but its Stack table and "GitLab API → Python scripts → JSON" data-flow narrative never mention Jira. Doctrine should acknowledge the Jira path.

**2. `ARCHITECTURE.md:Stack` lists only `requests>=2.28` for data collection.**
`scripts/requirements.txt` also pins `anthropic>=0.40` and `httpx>=0.27` (the AI dependency for `generate_reports.py`). The declared stack omits the AI report-generation dependency.

**3. `VECTOR.md:Problem Statement` / `Core Value Proposition` frame the product as sprint data "collected from GitLab."**
Data Services is now sourced from Jira. A one-line acknowledgement that data comes from GitLab *or* Jira would keep the identity doc current.

---

#### STRUCTURE — medium

**4. `ARCHITECTURE.md` structure tree omits the `reports/` data directory.**
`{project-slug}/reports/sprints/{milestone-slug}.json` and `reports/months/{YYYY-MM}.json` exist on disk (`public/data/cass/mirars/reports`, `.../ppmt/reports`) and are documented in CLAUDE.md, but the ARCHITECTURE.md tree stops at `fy{YYYY}/` under the project slug. The two docs disagree.

**5. `docs/case-studies/` exists on disk but is undeclared.**
The `ARCHITECTURE.md` structure tree lists only the three top-level `docs/*.md` files; `docs/case-studies/` (2 files) is not accounted for.

---

#### GAP — low

**6. `ARCHITECTURE.md:Naming Conventions` does not cover test files (`*.test.js`).**
The `.test.js` convention is stated only in the Testing section. A naming-table row would make it auditable alongside the other file types.

**7. `CLAUDE.md` under-lists the Core DOM exception.**
CLAUDE.md (line 76) permits only `$`, `getParams`, while ARCHITECTURE.md (the authority) documents `$`, `esc`, `getParams`, and `downloadDoc`. Not a contradiction, but CLAUDE.md's summary is incomplete relative to the spec.

---

#### PLACEHOLDER — info

**8. `VECTOR.md:Constraints` (line 101) still holds the `[OPERATOR: Add any organizational constraints…]` template prompt.**
The rest of the Constraints section is fully written; this is the only unresolved bracket in the file.

**9. `VECTOR.md:Research Status` — all artifacts "Not started."**
Expected for a tool-internal project, but the stage is "production," so the research gap is a low known risk rather than a discovery-stage placeholder.

---

### Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 5 |
| Low | 2 |
| Info | 2 |

**Doctrine health: GAPS FOUND**

All three files are present, internally consistent on layers/imports/naming/testing, and grounded on disk. The prior high-severity findings (Core DOM rule, empty VECTOR governance sections, undeclared testing stance) have all been resolved since the 2026-05-01 audit. Remaining gaps are documentation lag: the Jira data source and the AI report-generation dependency post-date the last full ARCHITECTURE/VECTOR pass.

---

### Recommended Actions

**1. Update `ARCHITECTURE.md` Stack + API/Data Pattern for the second data source.**
Add the Jira path (`source: "jira"`, `jira_api.py`/`jira_provider.py`) to the data-flow narrative, and add `anthropic>=0.40` / `httpx>=0.27` to the Stack table. This closes the largest drift and makes the prose consistent with the structure tree.

**2. Add `reports/` and `docs/case-studies/` to the `ARCHITECTURE.md` structure tree** so the declared layout matches disk and CLAUDE.md.

**3. Resolve the `VECTOR.md` line-101 OPERATOR placeholder** — fill in the organizational constraints or delete the bracket.
