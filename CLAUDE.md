# CLAUDE.md - Sprint Metrics Dashboard

## Project Overview

This is a static GitLab Pages dashboard that displays sprint metrics collected from GitLab's Iterations and Milestones APIs. Data is automatically collected via scheduled CI/CD pipelines and displayed in an interactive, accessible web interface.

**Tech Stack:**
- Frontend: Vanilla JavaScript, HTML5, CSS3, Chart.js v4.4.7
- Data Collection: Python 3.12 with requests library
- Deployment: GitLab Pages
- CI/CD: GitLab CI/CD with scheduled pipelines

## Architecture

### Data Flow
1. **Data Collection** (Python scripts in `scripts/`)
   - `backfill.py` - One-time historical data fetch for all past sprints
   - `scheduled_update.py` - Scheduled updates for active and recently completed sprints
   - `project_split.py` - One-time script to split group-level sprint data into per-project files
   - `generate_reports.py` - Scheduled AI report generation (test plans + sprint/monthly reports) for completed sprints and past months (project-mode groups)
   - `jira_api.py` - Shared Jira Server/Data Center REST client (bearer-token auth) for Jira-sourced groups
   - `jira_provider.py` - Turns Jira Software sprints into the standard sprint-record dict (used by `backfill.py`/`scheduled_update.py` for `source: "jira"` groups)
   - `api_commit.py` - Commits data files via GitLab Commits API (bypasses git push/signed commits)

2. **Data Storage** (`public/data/`)
   - Group configuration in `public/data/groups.json`
   - Sprint data organized by group, fiscal year (Oct-Sep), and month
   - Group-level structure: `public/data/{group-slug}/fy{YYYY}/{MM}-{mon}-{YYYY}.json`
   - Project-level structure (for `mode: "projects"` groups): `public/data/{group-slug}/{project-slug}/fy{YYYY}/{MM}-{mon}-{YYYY}.json`
   - `{group-slug}/current-sprint.json` - Active sprint per group, or `null` if none (standard mode)
   - `{group-slug}/{project-slug}/current-sprint.json` - Active sprint per project, or `null` if none (project mode)
   - Milestone data: `public/data/{group-slug}/milestones/{project-slug}/{milestone-slug}.json`
   - Milestone index: `public/data/{group-slug}/milestones/index.json`
   - Report content (project-mode): `public/data/{group-slug}/{project-slug}/reports/sprints/{milestone-slug}.json` and `reports/months/{YYYY-MM}.json` (test-plan steps + sprint/monthly goals/summary/metrics; rendered to Word client-side)

3. **Dashboard** (`public/`) — Four-layer architecture (see Frontend Architecture below)
   - **HTML pages:** `index.html`, `group.html`, `milestone.html`, `releases.html`
   - **Design System:** `css/tokens.css` (CSS variables), `css/styles.css` (imports tokens)
   - **Core (pure logic):** `js/core/utils.js`, `js/core/holidays.js`, `js/core/calculations.js`, `js/core/parsing.js`, `js/core/reports.js`, `js/core/dashboardShell.js`
   - **Services (data fetching):** `js/services/api.js`
   - **UI (page modules):** `js/home.js`, `js/group.js`, `js/milestone.js`, `js/releases.js`
   - **UI (shared controller):** `js/dashboard.js` — the sprint dashboard (charts, tables, dropdowns), mounted + rendered by both `group.js` and `home.js` via `mountDashboard()` / `renderDashboard()`
   - **Vendored:** `js/chart.min.js` (Chart.js v4.4.7), `img/` (logos)

### Key Features
- Home page with group/project listing cards showing active sprint status, with filter chips (All Projects / Active Sprints)
- Per-project sprint tracking: groups with `mode: "projects"` show per-project cards on the home page with project-scoped dashboards
- Per-group dashboard pages with direct-linkable URLs (`group.html?group={slug}` or `group.html?group={slug}&project={project-slug}`)
- Multi-group support (Cloud Services, Service Management, Data Services) — each group has its own dashboard URL
- Branding: Tinkerers favicon on all pages, group/project logos on home page cards
- Sprint navigation by fiscal year and month
- Sprint progress summary with visual progress bar, time remaining, work complete %, and scope change %
- Burndown chart (issue count or story points) with ideal line accounting for weekends/holidays
  - Visual shading for non-working days (weekends and US federal holidays)
- Project filtering via chip toggles
- Sortable issues table with status, weight, labels, clickable milestone links
- Velocity chart showing last 6 completed sprints with average velocity line, responsive to month/FY date selection
- Type breakdown doughnut chart with Initial/Completed toggle, inline count/percentage labels
  - Dynamically detects all `type::*` labels (Bug, Improvement, New Feature, DevOps, etc.)
  - Includes "Uncategorized" for issues without a type label
  - Initial = issues at sprint start; Completed = closed issues (matches stat card values)
- Milestone detail pages with parsed issue descriptions (User Story)
- Releases index page listing all milestones by project, reverse chronological, with expand/collapse
- Document generation (project-mode groups): from a completed sprint's dashboard, download **Release Notes**, **Test Plan**, and **Sprint Report** as MS Word; from a project dashboard, download a **Monthly Report** for a past month. Word is built client-side (Office-HTML); AI content (test steps, goals/summary) is precomputed by a scheduled CI job
- Full accessibility support (semantic HTML, ARIA, keyboard navigation, screen reader compatible)

### Frontend Architecture (Separation of Concerns)

The frontend JavaScript follows a **four-layer architecture**. Every file belongs to exactly one layer. Dependencies flow downward only: UI → Services → Core → Design System.

**IMPORTANT: All new frontend code MUST follow this pattern. Never add data fetching to core, business logic to UI, or DOM manipulation to services.**

| Layer | Directory | Purpose | Rules |
|-------|-----------|---------|-------|
| **Design System** | `css/tokens.css` | CSS variables (colors, spacing, radii) | All visual constants live here. No hardcoded values in `styles.css` or JS. |
| **Core** | `js/core/` | Pure business logic and utilities | No DOM access, no `fetch()`, no side effects. Fully testable without a browser. **Exception:** `utils.js` exports thin DOM helpers (`$`, `getParams`) shared by all UI modules. This is the only permitted DOM touch in Core. |
| **Services** | `js/services/` | Data fetching and external communication | No DOM manipulation, no rendering. Functions take parameters (no module state). |
| **UI** | `js/*.js` (page modules) | DOM rendering, event handlers, page state | Imports from core + services. Each page has its own module. |

**When adding a new feature, follow this order:**
1. **Design tokens first** — new colors/spacing go in `css/tokens.css`
2. **Core logic second** — pure functions in `js/core/` (calculations, parsing, utilities)
3. **Services third** — data fetching in `js/services/api.js`
4. **UI last** — page rendering in the relevant `js/*.js` page module

**Module rules:**
- All JS files use native ES modules (`import`/`export`). HTML loads them via `<script type="module">`.
- Chart.js is the exception: loaded as a classic `<script>` in `group.html` (sets `window.Chart`).
- No build step, no bundler. All import paths must use relative paths with `.js` extensions.
- Shared utilities (`$`, `esc`, `fetchJSON`, holiday functions, etc.) live in core/services — never duplicate them in page modules.
- Core functions must be **pure**: take data in, return results. No reading from module-level state in other files.

**What goes where:**

| Concern | Correct Layer | Example |
|---------|---------------|---------|
| CSS variables, colors, spacing | `css/tokens.css` | `--purple: #6b4fbb` |
| DOM helpers, HTML escaping, URL params | `js/core/utils.js` | `$()`, `esc()`, `getParams()` |
| Holiday/working day calculations | `js/core/holidays.js` | `isWorkingDay()`, `generateDateRange()` |
| Sprint metrics, filtering, sorting | `js/core/calculations.js` | `calculateProgress()`, `getFilteredIssues()` |
| Markdown section parsing | `js/core/parsing.js` | `parseSection()` |
| JSON fetching, data path resolution | `js/services/api.js` | `fetchJSON()`, `dataPath()`, `loadFY()` |
| Card rendering, chart rendering, tables | `js/{page}.js` | `renderBurndown()`, `buildCard()` |

## Project Structure

```
.
├── .gitlab-ci.yml              # CI/CD pipeline configuration
├── README.md                   # User-facing documentation
├── CLAUDE.md                   # This file - context for Claude Code
├── CLAUDE_PBI_SKILLS.md        # Future: GitLab issue management skills plan
├── docs/
│   ├── SSL_CERTIFICATE_SETUP.md    # SSL certificate configuration guide
│   ├── CUSTOM_DOCKER_IMAGE.md      # Custom Docker image with DoD certs
│   └── MULTI_GROUP_SUPPORT.md      # Multi-group feature design document
├── scripts/
│   ├── backfill.py             # Historical data collection
│   ├── scheduled_update.py     # Scheduled sprint updates
│   ├── project_split.py        # One-time: split group data into per-project files
│   ├── generate_reports.py     # Scheduled: AI report JSON (test plans + sprint/monthly reports)
│   ├── api_commit.py           # GitLab API commit utility
│   ├── gitlab_api.py           # Shared GitLab API client
│   ├── issue_read.py           # Read issue details
│   ├── issue_list.py           # List and filter issues
│   ├── issue_create.py         # Create new issues
│   ├── issue_implement.py      # Implementation workflow
│   ├── issue_comment.py        # Add issue comments
│   ├── issue_update.py         # Update issue fields
│   ├── issue_close.py          # Close issues with notes
│   └── requirements.txt        # Python dependencies (requests, anthropic, httpx)
└── public/                     # Static site root (deployed to Pages)
    ├── index.html              # Home page (group/project listing, filter)
    ├── group.html              # Sprint dashboard (?group={slug} or ?group={slug}&project={slug})
    ├── milestone.html          # Milestone detail page
    ├── releases.html           # Releases index page
    ├── css/
    │   ├── tokens.css          # Design tokens (CSS variables — colors, spacing, etc.)
    │   └── styles.css          # Stylesheet (imports tokens.css)
    ├── img/                    # Logo images (favicon, group/project logos)
    ├── js/
    │   ├── core/               # Pure logic layer (no DOM, no side effects)
    │   │   ├── utils.js        # Shared utilities ($, esc, slugify, formatLastUpdated, formatText, getParams)
    │   │   ├── holidays.js     # US federal holidays, isWorkingDay, generateDateRange
    │   │   ├── calculations.js # Sprint progress, burndown, type breakdown, velocity, filtering
    │   │   ├── parsing.js      # Markdown section parsing
    │   │   ├── reports.js      # Word/Office-HTML doc builders, sprint/month predicates
    │   │   └── dashboardShell.js # Pure HTML-string builder for the shared dashboard markup
    │   ├── services/           # Data fetching layer (all external communication)
    │   │   └── api.js          # fetchJSON, dataPath, group config, FY/sprint loading, report fetchers
    │   ├── dashboard.js        # UI: shared sprint-dashboard controller (mountDashboard/renderDashboard) — used by group.js + home.js
    │   ├── home.js             # UI: Home page (cards, filter) — imports core + services
    │   ├── group.js            # UI: Group dashboard page (resolves URL, mounts dashboard) — imports core + services + dashboard.js
    │   ├── milestone.js        # UI: Milestone detail (issues) — imports core + services
    │   ├── releases.js         # UI: Releases index (milestone list) — imports core + services
    │   └── chart.min.js        # Chart.js v4.4.7 (vendored, loaded as classic script)
    └── data/
        ├── groups.json         # Group configuration (names, IDs, slugs, logos, projects)
        └── {group-slug}/       # Group-scoped data directory (e.g., cass/, star/, p2ds/)
            ├── current-sprint.json     # Active sprint for this group
            ├── fy{YYYY}/               # Sprint data by fiscal year
            │   └── {MM}-{mon}-{YYYY}.json  # Sprints ending in that month
            ├── {project-slug}/         # Project-scoped data (project-mode groups)
            │   ├── current-sprint.json # Active sprint for this project
            │   ├── fy{YYYY}/           # Project sprint data by fiscal year
            │   └── reports/            # Generated report content (rendered to Word client-side)
            │       ├── sprints/{milestone-slug}.json  # Test plan + sprint report
            │       └── months/{YYYY-MM}.json          # Monthly report
            └── milestones/             # Milestone data by project
                ├── index.json          # All milestones index for releases page
                └── {project-slug}/     # Project-scoped milestone data
                    └── {milestone-slug}.json  # Individual milestone with issues
```

## Important Context

### GitLab Environment
- **GitLab Instance:** Internal GitLab at git.example.com
- **Classification:** CUI-CTI (Controlled Unclassified Information - Cyber Threat Intelligence)
- **Commit Signing:** Required and verified by GitLab hooks
- **API Authentication:** Uses GitLab tokens with specific scopes

### CI/CD Configuration
Required CI/CD variables (Settings > CI/CD > Variables):
- `GITLAB_URL` - GitLab instance URL (https://git.example.com)
- `GITLAB_TOKEN` - API token with `read_api` scope for reading iterations/issues (must have access to all groups in `groups.json`)
- `GITLAB_GROUP` - (Optional) Fallback group ID if `groups.json` is not configured
- `CI_PUSH_TOKEN` - API token with `api` scope + Maintainer role for committing data
- `ANTHROPIC_API_KEY` - Anthropic-compatible API key used by `generate_reports.py` for AI test steps + goals/summary. On the internal network this is an **Ask Sage** key.
- `ANTHROPIC_BASE_URL` - Anthropic-compatible endpoint for `generate_reports.py`. **Required on the CI runner**, which has no public internet egress — point it at the Ask Sage gateway (`https://ai-gateway.example.com/server/anthropic`). When unset the SDK defaults to `api.anthropic.com`, which the runner cannot reach.
- `ANTHROPIC_MODEL` - (Optional) Model id for `generate_reports.py` (default `claude-haiku-4-5-20251001`); override if the gateway exposes Claude under a different id.
- `DOD_CA_CERT` - (Optional) DoD CA certificate bundle for SSL verification (File type, ~96KB, 49 certificates)
- `JIRA_URL` - Base URL of the Jira instance for Jira-sourced groups (e.g. `https://jira.example.com`). Required when a group in `groups.json` has `source: "jira"`.
- `JIRA_TOKEN` - Jira Personal Access Token (Server/Data Center), sent as `Authorization: Bearer`. Read-only scope is sufficient. **Env/CI only — never commit.**
- `JIRA_SSL_VERIFY` - (Optional) `false`/`0`/`no` disables SSL verification (default enabled). Handled like `GITLAB_SSL_VERIFY`: bypassed by default in CI and switched on when `DOD_CA_CERT` is configured (the DoD Jira host chains to that bundle).

### Pipeline Jobs
1. **backfill** (manual) - Fetches all historical sprint data
2. **scheduled_update** (scheduled hourly during business hours and at 2 AM) - Updates active and recent sprints
3. **generate_reports** (scheduled, runs after scheduled_update) - Generates AI report JSON for newly completed sprints and past months; idempotent (skips existing) so AI usage is near-zero on routine runs; `allow_failure` so a missing key / AI error never blocks the data pipeline
4. **pages** - Deploys public/ directory to GitLab Pages

### Data Structure

**Sprint JSON** (`fy{YYYY}/{MM}-{mon}-{YYYY}.json`):
- Basic info: `id`, `title`, `state`, `start_date`, `end_date`
- Metrics: `initial_count`, `initial_weight`, `completed` (count/weight)
- `daily_burndown` - Array of `{date, remaining_count, remaining_weight}`
- `type_breakdown` - Counts by issue type (bug, improvement, new_feature, other)
- `issues` - Full issue list with id, title, description, project, weight, state, labels, milestone (`description` powers client-side Release Notes for reports-enabled standard groups like Service Management)
- `last_updated` - ISO timestamp (current sprint only)

**Milestone JSON** (`milestones/{project-slug}/{milestone-slug}.json`):
- `milestone_title`, `milestone_id`, `slug` - Milestone identification
- `project_id`, `project_name`, `group_slug` - Project context
- `issues` - Full issue list including `description` field (for section parsing)
- `last_updated` - ISO timestamp

**Milestone Index** (`milestones/index.json`):
- `projects` - Array of projects, each with `milestones` array
- Milestones sorted by `due_date` descending (newest first)
- Each milestone has `title`, `slug`, `state`, `due_date`

### Technical Considerations
- **API Commits:** Uses GitLab Commits API instead of git push to bypass signed commit requirements
- **SSL Verification:** Can be enabled via `DOD_CA_CERT` CI/CD variable (see `docs/SSL_CERTIFICATE_SETUP.md`). When not configured, SSL verification is disabled for compatibility. DoD certificates are combined with public CAs to support both PyPI package downloads and GitLab API access.
- **Iterations vs Milestones:** Scripts auto-detect GitLab tier (Premium uses Iterations, Free uses Milestones). Groups with `mode: "projects"` use project-level Milestones for sprints (filtered by `transition_date`).
- **Jira Data Source (`source: "jira"`):** A group in `groups.json` can set `source: "jira"` to pull from Jira Software (Server/Data Center) instead of GitLab. Data Services uses this. Config fields on the group: `jira_board_id` (numeric Scrum board), `jira_project_key` (optional, logging), `jira_story_points_field` (custom field id for weight, e.g. `customfield_10106`), and optional `jira_type_map` (Jira issue-type name → `type::*` label; defaults in `jira_provider.DEFAULT_TYPE_MAP`). `scheduled_update.py` and `backfill.py` dispatch on `source` (defaulting to `"gitlab"`); `jira_provider.py` fetches sprints via the Agile API, reconstructs daily burndown from the Sprint-field **changelog** (Jira's analog to GitLab resource events), maps status `statusCategory == "done"` → `closed`, derives numeric `iid` from the issue key, and emits the **identical sprint-record schema** as the GitLab path (so the frontend is unchanged). Jira backfill is floored at the FY2026 cutoff (`JIRA_BACKFILL_EARLIEST` in `backfill.py`). Scope: sprint metrics only — no milestones/releases index or AI reports for Jira groups. **Known limitation:** issues *removed* from a sprint before it ends are not returned by the `sprint = {id}` query, so mid-sprint removals may be undercounted in burndown.
- **Per-Project Sprint Tracking:** Groups with `mode: "projects"` in `groups.json` track sprints per project using Milestones. Historical group-level Iteration data is pre-split into per-project files via `project_split.py`. `scheduled_update.py` and `backfill.py` handle ongoing milestone collection. The `dataPath()` helper in `js/services/api.js` routes to `data/{group}/{project}/` when a project is active.
- **Fiscal Year:** October-September, sprints organized by end date. **Data cutoff: October 2025 (FY2026).** No sprint, milestone, or release data before this date is displayed. Controlled by `EARLIEST_FY` and `EARLIEST_DATE` constants in `js/services/api.js`. `discoverFYs()` uses `EARLIEST_FY` as the floor for FY scanning; the releases page filters milestones with `due_date < EARLIEST_DATE`. `fyMonths(fy, upToDate)` accepts an optional `Date` to cap the month list at the current date — `loadFY()` passes `new Date()` to avoid fetching future months that don't have data files yet. The dropdown population in `dashboard.js` omits `upToDate` since it already checks `if (data[key])` before rendering.
- **Working Days:** Burndown ideal line excludes weekends and US federal holidays
- **Non-Working Day Shading:** Chart.js plugin uses UTC timezone for date calculations to align with server-generated burndown data
- **Type Breakdown:** Dynamically detects all `type::*` labels from issue data and normalizes them (title case, hyphens to spaces). Issues without a type label are counted as "Uncategorized". Known types (Bug, Improvement, New Feature, DevOps, Infrastructure) have fixed chart colors; unknown types cycle through an extras palette. Initial/Completed toggle filters to sprint-start issues or closed issues respectively. A custom Chart.js plugin renders count and percentage inline on each doughnut slice (skips slices < 20°).
- **No Build Step:** Pure static site, no transpilation or bundling. Uses native ES modules (`<script type="module">`) with relative import paths and `.js` extensions.
- **Multi-Group:** Each group has its own dashboard page at `group.html?group={slug}`. Project-mode groups use `group.html?group={slug}&project={project-slug}`. The home page (`index.html`) lists all groups with sprint status cards and filter chips. `resolveGroupAndProject()` in `js/services/api.js` parses URL parameters and resolves the active group/project. The `dataPath()` helper scopes all data fetches to the active group (and project if applicable). Python scripts loop over all configured groups. Falls back to `GITLAB_GROUP` env var for single-group backward compatibility.
- **Page Navigation:** Breadcrumbs follow the pattern: Home > Group Name > All Releases > Milestone. For project-mode groups, breadcrumbs show "Group: Project". All pages resolve names from `groups.json`. The milestone and releases pages receive the group via `?group=` URL parameter. For project-mode groups, the breadcrumb group link points to `index.html` instead of `group.html`.
- **Home Page Filter:** Cards are tagged with `data-sprint-state` (active, ended, upcoming, none). Filter chips ("All Projects" / "Active Sprints") show/hide cards. Section headers hide when all their cards are filtered out. Empty state message shown when no cards match.
- **Branding:** Tinkerers favicon on all pages via `<link rel="icon">`. Group and project logos on home page cards, configured via `logo` field in `groups.json`. Projects without a `logo` fall back to their parent group's logo.
- **Empty Iteration Filtering:** GitLab iteration cadences auto-generate placeholder iterations with null titles. Python scripts skip these during data collection (`backfill.py` and `scheduled_update.py`). Frontend has a defensive fallback displaying date range if a null title is encountered.
- **Milestone Data Collection:** Python scripts fetch project-level milestones via `/api/v4/projects/:id/milestones` and store issue data with full descriptions for section parsing. Projects are discovered from sprint issue data. Milestone index is sorted by `due_date` descending.
- **Releases Page:** Displays milestones in reverse chronological order, limited to 5 most recent per project with an expand/collapse toggle.
- **Null Sentinel for current-sprint.json:** When no active sprint exists for a group or project, `scheduled_update.py` writes `null` (valid JSON) to `current-sprint.json` instead of deleting the file. This prevents 404 console errors on the frontend. `fetchJSON` returns `null` for these files, and the frontend already handles `null` by showing "No active sprint" on cards.

### Report Generation

Lets users download **Release Notes**, **Test Plans**, **Sprint Reports**, and **Monthly Reports** as MS Word documents from the dashboard. Because the site is static (GitLab Pages, no server), the architecture splits into a CI step that precomputes content and a client step that renders Word.

- **Scope by group type** (each document requires different data, so support varies):
  - **Project-mode groups (Cloud Services: ORBIT, PULSE, RELAY, SkyCast, FormFlow)** — collect per-project milestone issue **descriptions**, so they get **all four** documents (Release Notes, Test Plan, Sprint Report, Monthly Report). A sprint qualifies only when `source === "milestone"` (post-`transition_date`); historical iteration-sourced sprints have no milestone/report files.
  - **Jira-sourced standard groups (Data Services)** — no per-issue descriptions collected, so **Sprint Report + Monthly Report only**.
  - **Reports-enabled standard GitLab groups (Service Management, `"reports": true` in groups.json)** — iteration-sourced, but the sprint record's `issues` now carry `description` (added to `backfill.py`/`scheduled_update.py`), so they get **Release Notes + Sprint Report + Monthly Report** (no Test Plan). Release Notes are built client-side from the loaded sprint record's issues (these groups have no milestone JSON), grouped by project. **Historical descriptions require a one-time manual `backfill` re-run to populate; `scheduled_update` backfills active/recent sprints going forward. Until then Release Notes render "No description provided."**
- **Backend (`scripts/generate_reports.py`):** scheduled CI job (after `scheduled_update`). Project-mode groups → `process_project` (milestones via API); standard groups reading local sprint JSON (Jira **and** reports-enabled, e.g. Service Management) → `process_local_group` (`data/{group}/fy*/`). For each completed sprint and past month lacking output, calls Anthropic (`claude-haiku-4-5`) for per-issue **test-plan steps** (project-mode only; respects `test-plan::no` / `release-notes::no` labels) and sprint/monthly **goals + summary**, plus deterministic metrics. Writes JSON only to `reports/sprints/{milestone-slug}.json` and `reports/months/{YYYY-MM}.json` (group-scoped for standard groups). **Idempotent** (skips existing); **env-only secrets** (`GITLAB_TOKEN`, `ANTHROPIC_API_KEY`) with a lazy Anthropic client so idle runs need no key. No Word files are ever stored. The CI runner has no public internet egress, so the Anthropic client is pointed at the Ask Sage gateway via `ANTHROPIC_BASE_URL` (an internal `ai-gateway.example.com` host); `api.anthropic.com` is unreachable from CI.
- **Frontend:** `js/core/reports.js` builds Word-openable documents from JSON via the lightweight **Office-HTML** approach (`officeHtml()` + `downloadDoc()` in `utils.js`); `js/services/api.js` fetches the report/milestone JSON. **Release notes are built client-side with no AI** — from milestone JSON (`buildReleaseNotesDoc`, project-mode) or from the sprint record's issues (`buildReleaseNotesFromSprint`, standard reports-enabled groups). Only test plans and sprint/monthly reports depend on the CI-generated AI content.
- **UI gating:** `availableSprintDocs(sprint, group)` picks the per-button set from the sprint source + group config; `reportsEnabledFor(group, project)` gates the Monthly Report button. Sprint buttons (`#sprint-reports` in `group.html`) show only for a completed sprint whose context supports them; the Monthly Report button shows only for a past calendar month. Buttons degrade gracefully ("not generated yet") when report JSON is absent. Sprint→file mapping uses `slugify(sprint.title)` (matches the Python slug).
- **Dropped from the prototype:** the "X unit tests added" section (it read the project source repo, which the dashboard pipeline cannot access).

## Development Guidelines

### Starting a Development Session

**IMPORTANT: Always sync with remote at the start of each day's first session:**
```bash
git pull origin master
```
This is required because the pipeline automatically commits updated sprint data to `public/data/` — hourly during business hours and at 2 AM overnight. Starting your session without pulling will cause merge conflicts when you try to push.

### When Making Changes

**Frontend (HTML/CSS/JS) — follow the four-layer architecture:**
- Test changes locally with `cd public && python -m http.server 8000`
- Maintain accessibility features (semantic HTML, ARIA attributes, keyboard nav)
- Keep JavaScript vanilla (no frameworks/build tools), use native ES modules
- New pure logic goes in `js/core/`, new data fetching in `js/services/`, rendering in page modules
- Never duplicate functions across files — add shared code to the appropriate core/services module
- Chart.js is vendored - don't update without testing

**Python Scripts:**
- Test locally by setting env vars: `GITLAB_URL`, `GITLAB_TOKEN`
- Scripts read group config from `public/data/groups.json` (falls back to `GITLAB_GROUP` env var)
- Scripts write to `public/data/{group-slug}/` - don't commit test data
- Maintain backward compatibility with existing JSON schema
- Handle both Iterations (Premium) and Milestones (Free) APIs

**CI/CD Pipeline:**
- Test pipeline changes in feature branches first
- Be careful with scheduled jobs - they run automatically
- Don't modify `api_commit.py` without understanding commit signing implications

### Common Tasks

**Update dashboard styling:**
- New CSS variables (colors, spacing) go in `public/css/tokens.css`
- Layout and component styles go in `public/css/styles.css`
- Test in multiple browsers
- Verify accessibility (keyboard navigation, screen readers)

**Modify data collection logic:**
- Edit `scripts/scheduled_update.py` or `scripts/backfill.py`
- Test with real API data
- Verify JSON output schema matches dashboard expectations

**Add new chart/visualization:**
- Chart rendering goes in the shared dashboard controller (`public/js/dashboard.js`) or the relevant page module
- Data calculations go in `public/js/core/calculations.js`
- Data fetching goes in `public/js/services/api.js`
- Reference Chart.js v4.4.7 documentation
- Ensure responsive design and accessibility

**Add a new utility or calculation:**
- Pure functions go in the appropriate `js/core/` module
- If it's used by multiple pages, it MUST go in core — never duplicate

**Change fiscal year logic:**
- Update scripts in `scripts/` (Python side)
- Update `public/js/services/api.js` (FY month ranges) and `public/js/core/calculations.js` (JS side)
- Regenerate all data with backfill job

### Testing

**Frontend:**
```bash
cd public
python -m http.server 8000
# Open http://localhost:8000 in browser
```

**Python Scripts:**
```bash
cd scripts
pip install -r requirements.txt
export GITLAB_URL="https://git.example.com"
export GITLAB_TOKEN="your-token-here"
# Scripts read groups from public/data/groups.json automatically.
# Fallback: export GITLAB_GROUP="your-group-id"
python scheduled_update.py  # or backfill.py
```

**Pipeline Testing:**
- Push to feature branch
- Manually trigger pipeline
- Check job logs for errors
- Verify data files are generated correctly

## Git Workflow

- **Main branch:** `master` (default)
- **Commit messages:** Follow conventional commits (e.g., "chore:", "feat:", "fix:")
- **Auto-commits:** Pipeline commits with "chore: nightly sprint data update" — hourly during business hours and at 2 AM overnight
- **Daily sync:** Always `git pull origin master` at the start of each session — pipeline runs frequently and will cause merge conflicts if you don't sync first
- **Before pushing:** Always pull before pushing to handle auto-commits from scheduled jobs

## Deployment

- Automatic via GitLab Pages when pushing to `master`
- URL pattern: `https://<namespace>.gitlab.io/<project-path>/`
- Publishes `public/` directory contents
- No build step required (static files only)

## Troubleshooting

**"Updates were rejected" when pushing:**
- Scheduled pipeline likely committed new data
- Run `git pull origin master` then `git push origin master`

**Data not showing in dashboard:**
- Check browser console for JavaScript errors
- Verify JSON files exist in `public/data/{group-slug}/fy{YYYY}/`
- Ensure `public/data/groups.json` lists the correct group slugs
- Check fiscal year/month dropdowns match available data
- Ensure the URL has a valid `?group=` parameter (e.g., `group.html?group=cass`)

**Pipeline failures:**
- 401 errors: Check `GITLAB_TOKEN` scope and permissions
- SSL errors: See `docs/SSL_CERTIFICATE_SETUP.md` for certificate configuration
- Pip install failures: Ensure pip runs before DoD certificate configuration (pip needs public CAs for PyPI)
- No data committed: Check if scripts found any iterations to process

## GitLab Issue Management

The project includes a complete suite of scripts for managing GitLab issues directly from the command line or within Claude Code. This enables end-to-end workflows like "Implement ORBIT #1234" where Claude can read, implement, update, and close issues.

### Available Scripts

All scripts are in the `scripts/` directory and require environment variables to be set (see Configuration below).

#### Read-Only Operations

**`scripts/issue_read.py`** - Read and display issue details
```bash
# Using default project (GITLAB_PROJECT=99001)
python3 scripts/issue_read.py <issue_iid> [--show-comments]

# Examples
python3 scripts/issue_read.py 1183
python3 scripts/issue_read.py 1183 --show-comments

# Override with explicit project
python3 scripts/issue_read.py 91001 1183
```

**`scripts/issue_list.py`** - List and filter issues
```bash
python3 scripts/issue_list.py [--group <id>] [--project <id>] [options]

# Examples - using default project
python3 scripts/issue_list.py --state opened
python3 scripts/issue_list.py --format json --limit 10

# Group-level queries
python3 scripts/issue_list.py --group 18274 --labels "type::bug,priority::high"

# Override with explicit project
python3 scripts/issue_list.py --project 91001 --state opened

# Options:
#   --state opened|closed|all
#   --labels comma-separated
#   --format table|json|simple
#   --limit N
#   --assignee username
#   --iteration ID
```

#### Write Operations

**`scripts/issue_create.py`** - Create new issues
```bash
# Using default project
python3 scripts/issue_create.py [project_id] [options]

# Interactive mode
python3 scripts/issue_create.py

# Non-interactive mode
python3 scripts/issue_create.py --title "Fix bug" \
  --description "Details" --labels "bug,critical" --weight 3

# Explicit project override
python3 scripts/issue_create.py 91001 --title "Different project issue"
```

**`scripts/issue_implement.py`** - Start implementation workflow
```bash
# Using default project
python3 scripts/issue_implement.py <issue_iid> [--assign-to-me]

# Examples
python3 scripts/issue_implement.py 1183
python3 scripts/issue_implement.py 1183 --assign-to-me

# Explicit project override
python3 scripts/issue_implement.py 91001 1183

# Displays:
# - Issue details and description
# - Suggested branch name
# - Commit message template
# - Next steps
```

**`scripts/issue_comment.py`** - Add comments to issues
```bash
# Using default project
python3 scripts/issue_comment.py <issue_iid> [--body "text"]

# Examples
python3 scripts/issue_comment.py 1183 --body "Implementation complete"
python3 scripts/issue_comment.py 1183  # Interactive mode

# Explicit project override
python3 scripts/issue_comment.py 91001 1183 --body "Different project"
```

**`scripts/issue_update.py`** - Update issue fields
```bash
# Using default project
python3 scripts/issue_update.py <issue_iid> [options]

# Examples
python3 scripts/issue_update.py 1183 --add-labels "status::in-progress"
python3 scripts/issue_update.py 1183 --remove-labels "status::todo"
python3 scripts/issue_update.py 1183 --state-event close
python3 scripts/issue_update.py 1183 --weight 5 --assignee username

# Explicit project override
python3 scripts/issue_update.py 91001 1183 --add-labels "priority::high"

# Options:
#   --title "New title"
#   --description "New description"
#   --labels "replace,all"
#   --add-labels "add,these"
#   --remove-labels "remove,these"
#   --state-event close|reopen
#   --assignee username
#   --weight N
#   --iteration ID
```

**`scripts/issue_close.py`** - Close issues with notes
```bash
# Using default project
python3 scripts/issue_close.py <issue_iid> [options]

# Examples
python3 scripts/issue_close.py 1183
python3 scripts/issue_close.py 1183 --note "Implemented in commit abc123"
python3 scripts/issue_close.py 1183 --note "Fixed and verified" \
  --add-labels "status::done,verified"

# Explicit project override
python3 scripts/issue_close.py 91001 1183 --note "Different project"
```

### Configuration

**Required Environment Variables:**
```bash
export GITLAB_URL="https://git.example.com"
export GITLAB_TOKEN="<token>"          # API scope for write operations, read_api for read-only
export GITLAB_SSL_VERIFY="true"        # Enable SSL verification (default)
```

**Optional Environment Variables:**
```bash
export GITLAB_PROJECT="99001"          # Sprint Metrics Dashboard project (default for all commands)
export GITLAB_GROUP="18274"            # Default group ID
export GITLAB_USERNAME="your-user"     # For --assign-to-me flag
export GITLAB_ISSUE_TOKEN="<token>"    # Overrides GITLAB_TOKEN for issue metadata scripts only
                                       # (issue_read, issue_list, issue_create, issue_comment,
                                       #  issue_update, issue_close). Use a Cloud Services group token
                                       # to access ORBIT, PULSE, RELAY, etc.
                                       # issue_implement.py always uses GITLAB_TOKEN (repo access).
```

**Token Scopes:**
- **Read-only operations** (`issue_read.py`, `issue_list.py`): Requires `read_api` scope
- **Write operations** (all others): Requires `api` scope
- **`GITLAB_ISSUE_TOKEN`**: Requires `read_api` for read-only scripts, `api` for write scripts

**Note**: All issue management scripts default to project 99001 (Sprint Metrics Dashboard). You can override by providing an explicit project_id argument.

### Complete Workflow Example

When implementing an issue (e.g., "Implement ORBIT #1234"), use the following workflow:

```bash
# 1. Read the issue to understand requirements
python3 scripts/issue_read.py 1234 --show-comments

# 2. Start implementation workflow (displays branch name, commit template)
python3 scripts/issue_implement.py 1234 --assign-to-me

# 3. Create feature branch and make changes
git checkout -b 1234-issue-title-slug

# 4. Update labels to reflect progress
python3 scripts/issue_update.py 1234 --add-labels "status::in-progress"

# 5. Add progress comment
python3 scripts/issue_comment.py 1234 --body "Implementation complete, testing locally"

# 6. After testing, update status
python3 scripts/issue_update.py 1234 --add-labels "status::testing" \
  --remove-labels "status::in-progress"

# 7. Close issue when complete
python3 scripts/issue_close.py 1234 \
  --note "Implemented in commit abc123, verified in testing" \
  --add-labels "status::done"
```

### Using in Claude Code

Claude can invoke these scripts directly via the Bash tool to enable several key workflows:

#### Workflow 1: Collaborative PBI Creation
Discuss and refine a Product Backlog Item (PBI) conversationally, then create it directly in GitLab:

**Example conversation:**
```
User: "I need a feature to export sprint metrics to CSV"

Claude: "Let me help design that feature. Here's what I'm thinking:

Title: Add CSV export for sprint metrics

Description:
- Export current sprint data to CSV format
- Include columns: Issue ID, Title, State, Weight, Labels, Project
- Add download button to dashboard UI
- Support filtering (same as current dashboard filters)

Acceptance Criteria:
- [ ] CSV download button added to dashboard
- [ ] Export includes all filtered issues
- [ ] File naming: sprint-{title}-{date}.csv
- [ ] Handles special characters in data

Would you like me to add any other requirements?"

User: "Yes, also add assigned user and dates. Then create the issue."

Claude: "Creating issue in GitLab..."
[Runs: python3 scripts/issue_create.py 91001 --title "Add CSV export for sprint metrics" ...]

"✓ Issue #1245 created: https://git.example.com/project/issues/1245"
```

This eliminates context switching between chat and GitLab UI during backlog grooming sessions.

#### Workflow 2: Complete Issue Implementation
When you say "Implement ORBIT #1234", Claude will:

1. Read the issue details using `issue_read.py`
2. Start the implementation workflow with `issue_implement.py`
3. Make code changes with your participation
4. Update status and labels during work using `issue_update.py`
5. Add progress comments using `issue_comment.py`
6. Close the issue when complete using `issue_close.py`

This maintains a full audit trail in GitLab that management can track on sprint boards.

### Shared API Client

All scripts use a shared `scripts/gitlab_api.py` module that provides:
- Centralized authentication and session management
- Automatic pagination for large result sets
- Rate limiting with `Retry-After` header respect
- Exponential backoff for server errors (5xx)
- Consistent error handling and logging

You can test the API client directly:
```bash
python3 scripts/gitlab_api.py  # Displays authenticated user info
```

## Future Enhancements

### Additional Issue Operations
- Link related issues
- Bulk operations (close multiple, update multiple)
- Issue templates for common task types

### Merge Request Integration
- Create merge requests from command line
- Review and approve MRs
- Link MRs to issues automatically

### Custom Docker Image
For cleaner SSL certificate handling, a custom Docker image with pre-installed DoD certificates is documented in `docs/CUSTOM_DOCKER_IMAGE.md`. This would eliminate the need for CI/CD variable configuration and simplify the pipeline.

**Benefits:**
- Certificates baked into image
- Faster pipeline execution
- Simpler configuration
- Better maintainability

**Status:** Awaiting coordination with sysops for container registry access

## Additional Resources

- Chart.js v4.4.7 docs: https://www.chartjs.org/docs/4.4.7/
- GitLab Iterations API: https://docs.gitlab.com/ee/api/iterations.html
- GitLab Issues API: https://docs.gitlab.com/ee/api/issues.html
- GitLab Pages docs: https://docs.gitlab.com/ee/user/project/pages/
- DoD PKI: https://public.cyber.mil/pki-pke/
