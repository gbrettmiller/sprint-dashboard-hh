# ARCHITECTURE.md — GitLab Sprint Dashboard

**Last Updated:** 2026-07-02

This file is the technical specification. When in doubt about how to build something, this file decides. The philosophy behind these decisions lives in VECTOR.md. The agent briefing and workflow documentation lives in CLAUDE.md.

---

## Layers

The frontend follows a strict four-layer architecture. Dependencies flow **downward only**. A lower layer never imports from a higher layer.

| Layer | Location | Purpose | Rules |
|-------|----------|---------|-------|
| **Design System** | `public/css/tokens.css` | CSS custom properties — all colors, radii, focus rings | No hardcoded values in `styles.css` or JS. All visual constants live here. |
| **Core** | `public/js/core/` | Pure business logic — calculations, parsing, utilities, holidays, report/document builders | No DOM access. No `fetch()`. No side effects. Testable without a browser. **Exception:** `utils.js` exports thin DOM helpers (`$`, `getParams`) shared by all UI modules and a DOM-based file download trigger (`downloadDoc`). These are the only permitted DOM touches in Core. |
| **Services** | `public/js/services/api.js` | Data fetching and path resolution | No DOM manipulation. No rendering. Stateless functions. |
| **UI** | `public/js/*.js` (page modules + shared controllers) | DOM rendering, event handlers, page-scoped state | Imports from Core + Services (and, for a shared controller, from another UI module). One page module per page. UI logic shared by multiple pages lives in a **shared controller** module (e.g. `dashboard.js`, mounted + rendered by `group.js` and `home.js`). |

### Import Direction

```
UI page modules (js/home.js, js/group.js, js/milestone.js, js/releases.js)
     ↓ imports from                    ↘ imports from
Shared UI controller (js/dashboard.js)  → (same layer; downward-only otherwise)
     ↓ imports from
Services (js/services/api.js)
     ↓ imports from
   Core (js/core/utils.js, calculations.js, holidays.js, parsing.js, reports.js, dashboardShell.js)
     ↓ uses tokens from
Design System (css/tokens.css)
```

A shared controller sits in the UI layer and may be imported by page modules (same-layer import). The downward-only rule still holds: no UI module (page or controller) is imported by Services or Core.

**The single exception:** Chart.js is loaded as a classic `<script>` in `group.html` (sets `window.Chart`). It is vendored and not an ES module. All other JS files use native ES modules with relative paths and `.js` extensions.

---

## Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Vanilla JavaScript (ES modules), HTML5, CSS3 | No build step, no framework dependency, direct deployment to GitLab Pages |
| Charts | Chart.js v4.4.7 (vendored at `js/chart.min.js`) | Mature library; vendored to avoid CDN dependency on restricted network |
| Styling | CSS custom properties (`tokens.css` + `styles.css`) | Centralized design tokens with no preprocessor |
| Build | None | Static site; `public/` deploys directly to GitLab Pages |
| Data Collection | Python 3.12, `requests>=2.28` | HTTP client for the GitLab REST API and the Jira Server/DC REST API (see Data Sources below) |
| AI Reports | `anthropic>=0.40`, `httpx>=0.27` | `generate_reports.py` calls an Anthropic-compatible endpoint (Ask Sage gateway) for test-plan steps and sprint/monthly goals + summary |
| Deployment | GitLab Pages via `.gitlab-ci.yml` | Integrated with the same GitLab instance that hosts the data source |
| CI Runners | `python:3.12-slim` (collect stage), `alpine:latest` (pages stage) | Minimal images; DoD certificates applied at runtime via `DOD_CA_CERT` variable |

---

## Project Structure

```
sprint-metrics-dashboard/
├── .gitlab-ci.yml              # Pipeline: collect → test → pages stages
├── .gitignore
├── ARCHITECTURE.md             # This file — technical specification
├── CLAUDE.md                   # Agent briefing and workflow documentation
├── CLAUDE_PBI_SKILLS.md        # Future: GitLab issue management skills plan
├── VECTOR.md                   # Project identity and doctrine
├── README.md                   # User-facing documentation
├── package.json                # Vitest dev dependency; "type": "module"
├── package-lock.json
├── vitest.config.js            # Vitest config — scoped to public/js/core/**/*.test.js
├── docs/
│   ├── SSL_CERTIFICATE_SETUP.md    # DoD PKI certificate configuration
│   ├── CUSTOM_DOCKER_IMAGE.md      # Custom runner image design doc
│   ├── MULTI_GROUP_SUPPORT.md      # Multi-group feature design doc
│   └── case-studies/               # Post-hoc write-ups of notable fixes/integrations
├── scripts/                    # Python: data collection + issue management
│   ├── gitlab_api.py           # Shared API client (auth, pagination, retry, backoff)
│   ├── backfill.py             # One-time historical data fetch
│   ├── scheduled_update.py     # Scheduled: active + recent sprint update
│   ├── project_split.py        # One-time: split group data into per-project files
│   ├── generate_reports.py     # Scheduled: AI report JSON (test plans + sprint/monthly reports)
│   ├── jira_api.py             # Shared Jira Server/DC REST client (bearer-token auth)
│   ├── jira_provider.py        # Jira sprints → standard sprint-record dict (source: "jira" groups)
│   ├── api_commit.py           # Commits JSON via GitLab Commits API (bypasses signed-commit hook)
│   ├── issue_read.py           # Read GitLab issue details
│   ├── issue_list.py           # List and filter issues
│   ├── issue_create.py         # Create new issues
│   ├── issue_implement.py      # Implementation workflow helper
│   ├── issue_comment.py        # Add issue comments
│   ├── issue_update.py         # Update issue fields
│   ├── issue_close.py          # Close issues with notes
│   └── requirements.txt        # requests>=2.28
├── public/                     # Static site root — deployed to GitLab Pages
│   ├── index.html              # Home page (group/project cards with filter)
│   ├── group.html              # Sprint dashboard (?group={slug}&project={slug})
│   ├── milestone.html          # Milestone detail page
│   ├── releases.html           # Releases index page
│   ├── css/
│   │   ├── tokens.css          # [Design System] CSS custom properties
│   │   └── styles.css          # [Design System] Imports tokens.css; all component styles
│   ├── img/                    # Logos: favicon.svg, group and project logos
│   ├── js/
│   │   ├── core/               # [Core] Pure logic — no DOM, no fetch, no side effects
│   │   │   ├── utils.js        # $(), esc(), slugify(), getParams(), formatText(), officeHtml(), downloadDoc()
│   │   │   ├── holidays.js     # US federal holidays, isWorkingDay(), generateDateRange()
│   │   │   ├── calculations.js # calculateProgress(), burndown, velocity, type breakdown, filtering
│   │   │   ├── parsing.js      # parseSection()
│   │   │   ├── reports.js      # Word/Office-HTML doc builders, sprint/month predicates
│   │   │   └── dashboardShell.js # Pure HTML-string builder for the shared dashboard markup
│   │   ├── services/           # [Services] External data only
│   │   │   └── api.js          # fetchJSON(), dataPath(), resolveGroupAndProject(), loadFY(), discoverFYs()
│   │   ├── dashboard.js        # [UI] Shared sprint-dashboard controller — mountDashboard(), renderDashboard()
│   │   ├── home.js             # [UI] Home page rendering and filter chips
│   │   ├── group.js            # [UI] Group dashboard page — resolves URL, mounts + renders dashboard.js
│   │   ├── milestone.js        # [UI] Milestone detail — issues, dialogs
│   │   ├── releases.js         # [UI] Releases index — milestone list with expand/collapse
│   │   └── chart.min.js        # Chart.js v4.4.7 (vendored, classic script — sets window.Chart)
│   └── data/                   # Pre-generated JSON — written by Python scripts, served statically
│       ├── groups.json         # Group + project configuration (IDs, slugs, logos, mode)
│       └── {group-slug}/
│           ├── current-sprint.json     # Active sprint data or `null` sentinel
│           ├── fy{YYYY}/
│           │   └── {MM}-{mon}-{YYYY}.json   # All sprints ending in that month
│           ├── {project-slug}/              # project-mode groups only
│           │   ├── current-sprint.json
│           │   ├── fy{YYYY}/
│           │   └── reports/                 # AI report JSON (rendered to Word client-side)
│           │       ├── sprints/{milestone-slug}.json   # test plan + sprint report
│           │       └── months/{YYYY-MM}.json           # monthly report
│           └── milestones/
│               ├── index.json               # All milestones sorted by due_date descending
│               └── {project-slug}/
│                   └── {milestone-slug}.json
└── vector/                     # Investiture research artifacts
    ├── research/               # Interviews, JTBD, personas, competitive, assumptions
    ├── schemas/                # Zero Vector schema definitions
    ├── decisions/              # Architecture Decision Records (ADRs)
    └── audits/                 # Investiture skill chain audit reports
```

---

## Naming Conventions

| File Type | Convention | Example |
|-----------|-----------|---------|
| JS source files | `camelCase.js` | `utils.js`, `calculations.js` |
| Python source files | `snake_case.py` | `scheduled_update.py`, `issue_read.py` |
| HTML pages | `lowercase.html` | `index.html`, `group.html` |
| CSS files | `lowercase.css` | `tokens.css`, `styles.css` |
| Data directories | `kebab-case` | `public/data/cass/`, `mirars/` |
| Data files | `{MM}-{mon}-{YYYY}.json` | `04-apr-2026.json` |
| CSS classes | Semantic, no utility prefix | `.group-card`, `.skip-link`, `.home-filter` |
| JS exports | `camelCase` functions; `UPPER_SNAKE` constants | `fetchJSON`, `EARLIEST_FY` |

---

## Styling

All CSS custom properties are declared in `public/css/tokens.css` on `:root`. `public/css/styles.css` imports `tokens.css` and contains all component styles.

**Rules:**
- New colors and spacing values go in `tokens.css` before `styles.css`. Never hardcode a **color** (hex, `rgb()`, `rgba()`) or a **spacing value** (`margin`, `padding`, `gap`) outside of `tokens.css` — spacing uses the `--space-*` scale.
- **Typography & radii (token scales exist; prefer them):** `font-size` uses the `--fs-*` scale, `font-weight` the `--fw-*` scale, `line-height` the `--lh-*` scale, and `border-radius` the `--radius` / `--radius-sm` / `--radius-pill` tokens. Use these tokens for new or changed styles. Raw `px` typography still present in `styles.css` is being migrated and is **not** flagged in the interim.
- **Not tokenized (raw `px` is allowed):** border widths (`1px`/`2px`), fixed layout dimensions (`max-width`, `width`/`height`, `minmax()`), positioning offsets (`top`/`left`), and media-query breakpoints. Two negative spacing offsets remain raw as documented idioms: the `.visually-hidden` `-1px` clip and the `.sprint-goal` `-8px` pull-up.
- Class names are semantic — they describe the component, not its visual appearance.
- No utility class frameworks (Tailwind, Bootstrap). No CSS modules. No CSS-in-JS.

**Documented exception — generated Word documents:** `js/core/reports.js` builds downloadable MS Word files via the Office-HTML approach. That HTML carries its own inline `<style>` block, rendered by Word in isolation from `tokens.css`, so CSS custom properties are unavailable there. Hardcoded values inside those Office-HTML strings (e.g. the `#999` table border) are the one permitted place for raw colors/spacing in JS.

Current design tokens:
- **Color:** `--purple`, `--purple-light`, `--purple-dark`, `--purple-faint`, `--purple-overlay`, `--purple-glow`, `--bg`, `--bg-hover`, `--card`, `--white`, `--text`, `--text-muted`, `--border`, `--green`, `--green-light`, `--red`, `--blue`, `--orange`, `--gray`, `--gray-light`, `--backdrop`
- **Radius / focus:** `--radius`, `--radius-sm`, `--radius-pill`, `--focus-ring`
- **Typography:** `--fs-2xs` … `--fs-5xl` (font-size scale), `--fw-normal`/`--fw-medium`/`--fw-semibold`/`--fw-bold` (weights), `--lh-tight`/`--lh-normal`/`--lh-relaxed` (line heights)
- **Spacing (4px base):** `--space-3xs` (2px), `--space-2xs` (4px), `--space-xs` (8px), `--space-sm` (12px), `--space-md` (16px), `--space-lg` (20px), `--space-xl` (24px), `--space-2xl` (32px), `--space-3xl` (48px), `--space-4xl` (64px)

---

## State Management

There is no shared state library. Each page module (`js/*.js`) manages its own module-level state.

**Conventions:**
- Module-level `let` variables hold page state (e.g., `let currentSprint = null`, `let burndownChart = null`).
- State is initialized on page load and mutated in response to user events or data loads.
- Core functions are stateless — they take data in and return results. They do not read module-level state from other files.
- State does not cross page boundaries. Each page is a full load.

---

## API / Data Pattern

Data flows in one direction: **GitLab / Jira API → Python scripts → JSON files → browser fetch → rendering**.

1. **Collection:** Python scripts hit the GitLab REST API (`/api/v4/groups/:id/iterations`, `/api/v4/projects/:id/milestones`, `/api/v4/projects/:id/issues`) and write structured JSON to `public/data/`. Groups configured with `"source": "jira"` in `groups.json` (e.g. Data Services) are collected from Jira Software (Server/DC) instead — `jira_api.py` (bearer-token REST client) and `jira_provider.py` fetch sprints via the Agile API and emit the **identical sprint-record schema** as the GitLab path, so the frontend is unaware of the source.
2. **Commit:** `api_commit.py` uses the GitLab Commits API to push data files. This bypasses the instance's signed-commit hook requirement for automated pipeline commits.
3. **Serve:** GitLab Pages serves `public/` as static files. No server-side computation at read time.
4. **Fetch:** The browser fetches JSON via `fetchJSON()` in `js/services/api.js`. All network access goes through this function. It returns `null` on non-OK responses, preventing thrown errors from missing data files.
5. **Render:** UI page modules receive fetched data and call Core functions to compute metrics, then render to the DOM.

**Data path resolution:** `dataPath(activeGroup, activeProject, relativePath)` in `api.js` scopes all fetches to the active group and project. UI modules never construct data paths directly.

**Null sentinel:** When no active sprint exists, `scheduled_update.py` writes `null` to `current-sprint.json` (valid JSON) rather than deleting the file. This prevents 404 errors in the browser console; `fetchJSON` returns `null`, and UI modules display "No active sprint."

**Iterations vs Milestones:** Scripts auto-detect the GitLab tier. Premium groups use the Iterations API. Groups with `mode: "projects"` in `groups.json` use project-level Milestones filtered by `transition_date`.

**Data source (`source`):** Each group in `groups.json` declares a `source`, defaulting to `"gitlab"`. `backfill.py` and `scheduled_update.py` dispatch on it. `"jira"` groups pull from Jira via `jira_provider.py` (sprint metrics only — no milestones/releases index or AI reports); Jira backfill is floored at the FY2026 cutoff. See CLAUDE.md → "Jira Data Source" for the field-level config.

---

## Testing

**Framework:** Vitest
**Scope:** All pure functions in `js/core/` — `utils.js`, `holidays.js`, `calculations.js`, `parsing.js`, `reports.js`, `dashboardShell.js`

The Core layer is the natural testing boundary. Core functions are pure (data in, result out) with no network calls. The DOM helpers declared as exceptions (`$`, `esc`, `getParams`, and the `downloadDoc` file download trigger in `utils.js`) are excluded — they are thin wrappers with no logic to test.

All existing Core functions are being backfilled with tests. New Core functions must include tests before merge.

**File convention:** `*.test.js` alongside source (e.g., `public/js/core/utils.test.js`)

**Run:** `npm test` or `npx vitest run`

---

## Development Principles

Inferred from observed patterns across the codebase. These describe the architectural beliefs behind the conventions — the "why" that guides edge-case decisions.

**Data is pre-computed, not computed at request time.** Sprint metrics, burndown arrays, and type breakdowns are computed by Python scripts at collection time and stored as JSON. The browser does display logic only. Nothing is calculated server-side at page load.

**Layer boundaries are enforced by convention, not tooling.** There is no bundler or linter enforcing the four-layer rule. It is enforced by code review and this document. Every contributor is responsible for placing new code in the correct layer.

**Static over dynamic.** Every feature that could be done server-side is done at collection time (Python) or at client render time (JS). There is no application server, no API gateway, no database query at page load.

**Accessibility is structural, not cosmetic.** Semantic HTML, ARIA attributes, keyboard navigation, and skip links are part of the markup spec, not retrofitted. A feature that breaks keyboard navigation is not done.

---

## What Not to Do

- **No hardcoded colors or spacing (`margin`/`padding`/`gap`) in `styles.css` or JS.** Colors and spacing belong in `css/tokens.css` (`--space-*` for spacing). Raw `px` is fine for borders, font sizes, radii, fixed dimensions, and breakpoints. The sole exception for raw colors/spacing in JS is the Office-HTML `<style>` block in `reports.js`, which Word renders without access to `tokens.css`.
- **No DOM access in `js/core/` — except the documented exceptions.** `utils.js` may export thin DOM helpers (`$`, `esc`, `getParams`) and a DOM-based file download trigger (`downloadDoc`). Everything else that touches `document` or `window` belongs in a UI module.
- **No `fetch()` calls outside `js/services/api.js`.** All network access goes through the Services layer.
- **No DOM manipulation in `js/services/api.js`.** Services fetch and return data. They do not touch the DOM.
- **No upward imports.** Core does not import from Services or UI. Services do not import from UI.
- **No build tools.** No webpack, Vite, Rollup, Babel, or TypeScript compilation. Import paths must use `.js` extensions for native ES module resolution.
- **No framework dependencies.** Vanilla JS only. No React, Vue, Angular, or Svelte.
- **No API keys or tokens in client-side JS.** All authenticated GitLab API access is Python-only, in the CI/CD pipeline.
- **Files approaching 300 lines — consider splitting.** If a module is growing, look for a pure function to extract into `js/core/`.

---

## How to Add a Feature

Follow this order. Do not skip steps.

1. **Design tokens first.** New colors or spacing go in `css/tokens.css` before anywhere else.
2. **Core logic second.** Write pure functions in the appropriate `js/core/` module. If it has no DOM dependency and no network call, it is Core.
3. **Services third.** If the feature needs new data fetching or a new data path, add it to `js/services/api.js`.
4. **UI last.** Wire rendering and event handling in the relevant page module (`js/home.js`, `js/group.js`, `js/milestone.js`, or `js/releases.js`), or the shared dashboard controller (`js/dashboard.js`) if it applies to the dashboard shown on multiple pages.
5. **Python if needed.** If the feature requires new data fields, add collection logic to `scheduled_update.py` or `backfill.py` and extend the JSON schema — keeping backward compatibility.

**Before shipping:**
- Test with `cd public && python -m http.server 8000`
- Verify keyboard navigation works on all interactive elements
- Verify ARIA attributes are present where needed
- Pull before pushing: `git pull origin main` (nightly pipeline commits at 2 AM and will cause rejected pushes otherwise)

---

## Flexible Preferences

These are preferences, not rules. They can be overridden with good reason.

- Prefer `async/await` over raw Promise chains.
- Prefer named exports over default exports (matches the existing codebase).
- Prefer template literals for HTML string construction over concatenation.
- Python scripts: PEP 8 style; descriptive variable names; no magic numbers.

---

## Decisions

Architecture decisions are recorded in `./vector/decisions/` using the ADR format (see `ADR-000-template.md`).

Decisions that shaped this architecture and are worth recording as ADRs:

| Decision | Status |
|----------|--------|
| Use GitLab Commits API instead of `git push` for data commits (bypasses signed-commit hook) | Accepted |
| Four-layer JS architecture with no build step | Accepted |
| Fiscal year data cutoff at October 2025 (FY2026) | Accepted |
| Null sentinel for `current-sprint.json` instead of file deletion | Accepted |
| Vendor Chart.js rather than load from CDN | Accepted |
| Per-project sprint tracking via Milestones (filtered by `transition_date`) for `mode: "projects"` groups | Accepted |
