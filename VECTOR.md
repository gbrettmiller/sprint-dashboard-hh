---
project:
  name: GitLab Sprint Dashboard
  description: Static dashboard for displaying sprint metrics collected from GitLab (Iterations and Milestones APIs) and Jira (Agile API), deployed via GitLab Pages.
  stage: production
  started: 2026-01-27
  repo: https://git.example.com/tinkers/sprint-metrics-dashboard.git

owner:
  name: alex.r.chen.ctr
  team: Tinkerers / Cloud Services

knowledge:
  research: ./vector/research/
  schemas: ./vector/schemas/
  decisions: ./vector/decisions/
  audits: ./vector/audits/
---

# GitLab Sprint Dashboard — Project Vector

## Core Relationship

This project works with Claude Code (and any AI contributor) under a **contractor model**: Claude is a skilled contractor hired for this project. The operator is the client. The contractor does what the client asks, raises concerns before acting (not after), and never makes unilateral decisions about scope, architecture, or priorities.

**What this means in practice:**
- Claude reads doctrine before writing code.
- Claude follows ARCHITECTURE.md — not what seems clever, not what it has done elsewhere.
- Claude surfaces ambiguity before guessing. One short question beats a wrong implementation.
- Claude does not refactor, reorganize, or "improve" things it was not asked to touch.
- Claude works in the smallest scope that solves the problem.

If doctrine is wrong, Claude says so and proposes a change. It does not silently deviate.

---

## Seven Principles

These are Investiture defaults. They apply to every project using this framework.

1. **Doctrine before code.** Read VECTOR.md → CLAUDE.md → ARCHITECTURE.md before touching anything. The architecture is not a suggestion.

2. **The smallest working thing.** Implement only what the task requires. No speculative features, no preemptive abstractions, no cleanup of code outside the task scope.

3. **Raise concerns before acting.** If something seems wrong — in the architecture, the task, or the approach — surface it before writing code, not after. A note costs nothing; a wrong implementation costs review cycles.

4. **Fit the existing grain.** Match the file structure, naming conventions, import patterns, and code style already in the codebase. Do not introduce new patterns without explicit operator approval.

5. **One layer per concern.** Logic lives in its layer. Do not leak across boundaries. If a function belongs in Core, it goes in Core. If it belongs in Services, it goes in Services. Never in both.

6. **Plain over clever.** Readable code is maintainable code. Avoid abstractions that require explanation. If you need a comment to describe what the code does, rewrite the code.

7. **Leave the campsite cleaner.** If you touch a file, leave it better than you found it — but only in the area you touched. Do not use a bug fix as an excuse to restructure.

**Non-negotiables (cannot be overridden by operator):**
- Never skip architectural layer boundaries to make a task easier.
- Never generate or guess URLs unless confident they are correct and helpful.
- Never commit changes unless explicitly asked.

---

## Problem Statement

Tinkerers software teams deliver work in sprints tracked through GitLab — and, for some teams, Jira. Sprint health data — burndown rates, velocity, issue breakdown by type, and milestone progress — is not visible without navigating each tool's UI across multiple groups, projects, and boards. Team leads and program managers need a consolidated, accessible view that surfaces this data at a glance, regardless of the underlying tracker, and supports sprint review conversations.

## Target Audience

- **Primary:** Tinkerers team leads, program managers, and developers who participate in sprint planning and review. Must be on NIPR, VPN, or AVD to access.
- **Secondary:** Claude Code agent (via CLAUDE.md) — the dashboard is developed with AI-assisted tooling and the project includes a CLI-integrated issue management workflow.

## Core Value Proposition

A single static site that makes sprint health visible across all Tinkerers groups and projects without requiring GitLab or Jira access or login. Data is collected automatically from each team's tracker and rendered from pre-committed JSON files. Any team member on NIPR can open it in a browser and see the current sprint state, burndown trend, velocity history, and issue breakdown — with no authentication, no configuration, and no build step.

## What This Is Not

- It is not a task management system. It does not replace GitLab — issues, assignments, and labels are managed there.
- It does not support manual data entry. All data comes from the GitLab API via scheduled pipelines.
- It is not a real-time system. Data is refreshed hourly during business hours and once at 2 AM overnight. The dashboard reflects recent state, not the instant present.
- It does not handle classification above CUI-CTI. No data above this level should appear in sprint issues or milestone descriptions.
- It is not a general-purpose GitLab dashboard. It tracks sprint metrics only — not CI/CD health, merge request review, repository activity, or deployment status.

## Design Principles

- **Visibility over action.** The dashboard shows sprint state; it does not change it. There are no write operations from the frontend.
- **Static over dynamic.** All data is pre-generated by the pipeline and served as JSON files. There is no application server, no database, and no computation at page load.
- **Accessibility is structural.** Semantic HTML, ARIA attributes, and keyboard navigation are built into markup from the start — not added after. A feature that breaks keyboard nav is not done.
- **Configuration over code.** Adding a new group or project requires only editing `groups.json` — no code changes. The dashboard adapts to the configuration.
- **Collection is separate from display.** Python scripts own all GitLab API access. The frontend is unaware of GitLab and works from static JSON files only.

## Constraints

- **Environment:** Internal GitLab at `git.example.com`. Users must be on NIPR, VPN, or AVD. DoD PKI certificates required for SSL verification.
- **Classification:** CUI-CTI (Controlled Unclassified Information - Cyber Threat Intelligence). Governs what data appears in the dashboard and how it is handled.
- **Commit Signing:** The GitLab instance requires signed commits. The data pipeline uses the GitLab Commits API (`api_commit.py`) to bypass this requirement for automated nightly commits.
- **No Build Step:** The frontend must remain pure static HTML/CSS/JS. No bundler, transpiler, or build system. Deployment is direct from `public/`.
- **GitLab Premium:** The Iterations API requires Premium tier. Scripts auto-detect and fall back to Milestones API for Free-tier groups.
- **Fiscal Year Cutoff:** Data cutoff is October 2025 (FY2026). No historical data before this date is displayed, controlled by `EARLIEST_FY` and `EARLIEST_DATE` in `js/services/api.js`.
- **Token Scopes:** `read_api` for data collection; `api` for write operations. `CI_PUSH_TOKEN` must have Maintainer role on the repository.
- **Jira Access:** Groups sourced from Jira (`source: "jira"`) require a `JIRA_TOKEN` Personal Access Token (Server/DC, read-only) and `JIRA_URL`. Env/CI only — never committed.

## Quality Gates

A change is done when:

- Tested locally with `cd public && python -m http.server 8000` and verified in browser
- Keyboard navigation works on all interactive elements
- ARIA attributes are present on new interactive elements
- No hardcoded colors or spacing outside `css/tokens.css`
- No business logic added to a UI module (`js/*.js`) that belongs in `js/core/`
- No DOM access added to `js/core/` outside the documented exceptions
- Vitest passes for `js/core/` — new Core functions include tests; existing Core functions are being backfilled
- `git pull origin main` run before pushing (pipeline commits hourly during business hours and at 2 AM)
- For Python script changes: JSON output schema verified against dashboard expectations

---

## Research Status

| Artifact Type | Location | Status |
|--------------|----------|--------|
| User interviews | `./vector/research/interviews/` | Not started |
| JTBD analysis | `./vector/research/jtbd/` | Not started |
| Personas | `./vector/research/personas/` | Not started |
| Competitive analysis | `./vector/research/competitive/` | Not started |
| Assumptions | `./vector/research/assumptions/` | Not started |
| Data schemas | `./vector/schemas/` | Initialized (Zero Vector schemas) |
| Architecture decisions | `./vector/decisions/` | Initialized (ADR-000 template) |
| Audit reports | `./vector/audits/` | See `invest-backfill.md` |
