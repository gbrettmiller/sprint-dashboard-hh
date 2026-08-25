# GitLab Sprint Dashboard — Project Overview

## Problem Statement

Software teams deliver work in sprints tracked through GitLab — and, for some teams, Jira.
Sprint health data — burndown rates, velocity, issue breakdown by type, and milestone
progress — is not visible without navigating each tool's UI across multiple groups,
projects, and boards. Team leads and program managers need a consolidated, accessible view
that surfaces this data at a glance, regardless of the underlying tracker, and supports
sprint review conversations.

## Target Audience

Team leads, program managers, and developers who participate in sprint planning and review.

## Core Value Proposition

A single static site that makes sprint health visible across all groups and projects without
requiring GitLab or Jira access or login. Any team member can open it in a browser and see
the current sprint state, burndown trend, velocity history, and issue breakdown — with no
authentication, no configuration, and no build step.

## What This Is Not

- It is not a task management system. It does not replace GitLab — issues, assignments, and
  labels are managed there.
- It does not support manual data entry through the UI. Data lives in `public/data/` as JSON
  files, currently maintained by hand.
- It is not a real-time system. It reflects whatever state the JSON data was last updated to.
- It is not a general-purpose GitLab dashboard. It tracks sprint metrics only — not CI/CD
  health, merge request review, repository activity, or deployment status.

## Design Principles

- **Visibility over action.** The dashboard shows sprint state; it does not change it. There
  are no write operations from the frontend.
- **Static over dynamic.** All data is served as JSON files. There is no application server,
  no database, and no computation at page load.
- **Accessibility is structural.** Semantic HTML, ARIA attributes, and keyboard navigation
  are built into markup from the start — not added after. A feature that breaks keyboard nav
  is not done.
- **Configuration over code.** Adding a new group or project requires only editing
  `groups.json` — no code changes. The dashboard adapts to the configuration.

## Constraints

- **No Build Step:** The frontend must remain pure static HTML/CSS/JS. No bundler,
  transpiler, or build system. Deployment is direct from `public/`.
- **Data source:** `public/data/*.json` is the source of truth for now, updated by hand. A
  future iteration may reintroduce automated collection and/or migrate to a real database
  (SQLite or Supabase) — see `README.md`.
- **Fiscal Year Cutoff:** Data cutoff is October 2025 (FY2026). No historical data before
  this date is displayed, controlled by `EARLIEST_FY` and `EARLIEST_DATE` in
  `js/services/api.js`.

## Quality Gates

A change is done when:

- Tested locally with `cd public && python -m http.server 8000` and verified in browser
- Keyboard navigation works on all interactive elements
- ARIA attributes are present on new interactive elements
- No hardcoded colors or spacing outside `css/tokens.css`
- No business logic added to a UI module (`js/*.js`) that belongs in `js/core/`
- No DOM access added to `js/core/` outside the documented exceptions
- Vitest passes for `js/core/` — new Core functions include tests
