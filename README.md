# GitLab Sprint Dashboard

A static dashboard for displaying sprint metrics. Data currently lives in
`public/data/` as static JSON files, maintained by hand; a future iteration may
reintroduce automated collection and/or migrate to a real database (SQLite or Supabase).

## Quick Start

### View the dashboard locally

Sprint data is already committed to the repo — no credentials or setup needed to browse it:

```bash
cd public
python -m http.server 8000
# Open http://localhost:8000
```

## Features

- **Multi-Group Support**: Home page lists all groups with active sprint status; each group has its own dashboard at a direct-linkable URL (`group.html?group={slug}`)
- **Per-Project Sprint Tracking**: Groups can use `mode: "projects"` to track sprints per project using Milestones instead of group-level Iterations. Each project gets its own card on the home page and its own dashboard (`group.html?group={slug}&project={project-slug}`)
- **Home Page Filtering**: Filter chips to show all projects or only those with active sprints
- **Branding**: Favicon on all pages; group and project logos on home page cards (configured via `logo` field in `groups.json`)
- **Sprint Navigation**: Browse sprints by fiscal year (Oct-Sep) and month
- **Burndown Chart**: Toggle between issue count and story points; ideal line accounts for weekends and US federal holidays; visual shading highlights non-working days
- **Project Filtering**: Filter all views by project using chip toggles
- **Issues Table**: Sortable, collapsible table of all sprint issues with status, weight, labels, and clickable milestone links
- **Velocity Chart**: Last 6 completed sprints with average velocity line
- **Type Breakdown**: Doughnut chart showing bug/improvement/feature distribution (excludes uncategorized issues)
- **Milestone Detail Pages**: View all issues for a milestone with parsed User Story sections
- **Releases Index**: Browse all milestones grouped by project, sorted newest-first with expand/collapse for projects with many milestones
- **Document Generation** (project-mode groups): Download **Release Notes**, **Test Plan**, and **Sprint Report** as MS Word from a completed sprint's dashboard, and a **Monthly Report** for a past month from a project dashboard. Word is generated client-side (Office-HTML) from the report JSON already present in `public/data/`
- **Accessibility**: Semantic HTML, ARIA attributes, keyboard navigation, screen reader support

## Project Structure

```
.gitlab-ci.yml          # CI: runs the test suite
netlify.toml             # Netlify static deploy config
vercel.json              # Vercel static deploy config
public/
  index.html            # Home page (group listing with sprint status)
  group.html             # Per-group sprint dashboard (?group={slug}&project={slug})
  milestone.html          # Milestone detail page
  releases.html            # Releases index page
  css/
    tokens.css          # Design tokens (CSS variables)
    styles.css           # Stylesheet (imports tokens.css)
  img/                  # Logos and branding images
  js/
    core/               # Pure logic (no DOM, no side effects)
      utils.js          # Shared utilities ($, esc, slugify, getParams, etc.)
      holidays.js       # US federal holidays, isWorkingDay, generateDateRange
      calculations.js   # Sprint progress, burndown, type breakdown, velocity
      parsing.js        # Markdown section parsing
      reports.js        # Word/Office-HTML doc builders, sprint/month predicates
      dashboardShell.js # Pure HTML-string builder for the shared dashboard markup
    services/
      api.js            # Data fetching, path resolution, FY/sprint loading, report fetchers
    dashboard.js        # UI: shared sprint-dashboard controller (mounted by group.js and home.js)
    home.js             # UI: Home page (cards, filter)
    group.js            # UI: Group dashboard page
    milestone.js        # UI: Milestone detail (issues)
    releases.js          # UI: Releases index (milestone list)
    chart.min.js         # Chart.js v4.4.7 (vendored)
  data/
    groups.json          # Group configuration (names, IDs, slugs, logos, projects)
    {group-slug}/         # Group-scoped data directory
      current-sprint.json    # Active sprint (or `null` if none)
      fy{YYYY}/               # Sprint data organized by fiscal year
        {MM}-{mon}-{YYYY}.json   # Sprints ending in that month
      {project-slug}/        # Project-scoped data (for project-mode groups)
        current-sprint.json   # Active sprint (or `null` if none)
        fy{YYYY}/               # Project sprint data by fiscal year
        reports/                # Report content (rendered to Word client-side)
      milestones/             # Milestone data by project
        index.json             # All milestones index
        {project-slug}/        # Project-scoped milestone data
          {milestone-slug}.json  # Milestone with issues
```

## Data Structure

Each sprint JSON file contains:

| Field | Description |
|-------|-------------|
| `id`, `title`, `state` | Basic sprint info |
| `start_date`, `end_date` | Sprint date range |
| `initial_count`, `initial_weight` | Day 1 commitment |
| `completed_count`, `completed_weight` | Final completed totals |
| `daily_burndown` | Array of `{date, remaining_count, remaining_weight}` |
| `type_breakdown` | Counts by issue type (bug, improvement, new_feature, other) |
| `issues` | Full issue list with id, title, project, weight, state, labels, milestone |
| `last_updated` | ISO timestamp (current sprint only) |

### Milestone Data

Milestone data is stored per project, separately from sprint data. Each milestone JSON file
contains the full issue list with `description` fields, enabling section parsing for the
milestone detail pages.

**Milestone index** (`milestones/index.json`) lists all milestones grouped by project, sorted
by due date (newest first). The **releases page** reads this index and the **milestone
detail page** reads individual milestone files.

## Editing Data

There is no collection pipeline right now — `public/data/` is the source of truth and is
edited directly. To add or update a sprint, milestone, or report:

1. Follow the JSON shape of an existing file in the same directory (see Data Structure above).
2. Update `current-sprint.json` to `null` when a group/project has no active sprint (don't
   delete the file — the frontend expects it to exist and return `null`).
3. If you add a new group or project, add it to `public/data/groups.json` — no code changes
   needed.

This is a deliberate stepping stone: the plan is to eventually move this data into a real
database (SQLite or Supabase) rather than continue hand-editing JSON at scale.

## Local Development

```bash
cd public
python -m http.server 8000
# Open http://localhost:8000
```

Run the test suite from the repo root:

```bash
npm ci
npm test
```

## Deployment

This is a plain static site — `public/` is the entire deploy artifact, no build step
required. Config is included for both:

- **Netlify** — `netlify.toml` sets the publish directory to `public`. Connect the repo in
  the Netlify dashboard and it deploys on every push.
- **Vercel** — `vercel.json` configures the output directory as `public`. Connect the repo
  in the Vercel dashboard and it deploys on every push.

Either platform works identically since there's no server-side code.

## Technical Notes

- **Frontend Architecture**: JavaScript follows a four-layer architecture: Design System (`css/tokens.css`) → Core (`js/core/`) → Services (`js/services/`) → UI (`js/*.js`). All files use native ES modules with no build step. Shared logic lives in core/services; page modules handle rendering only. See `ARCHITECTURE.md` for details.
- **Data Cutoff**: No sprint, milestone, or release data before October 2025 (FY2026) is displayed. Controlled by `EARLIEST_FY` and `EARLIEST_DATE` constants in `js/services/api.js`.
- **Null Sentinel Files**: `current-sprint.json` holds `null` when no active sprint exists, rather than the file being deleted. This prevents 404 console errors while the frontend displays "No active sprint" as before.
- **Fiscal Year**: Sprints are organized by fiscal year (October-September) based on sprint end date. `loadFY()` only fetches months up to the current date to avoid 404s for future months.
- **Working Days**: Burndown ideal line calculation excludes weekends and US federal holidays.
- **Non-Working Day Shading**: Chart.js plugin uses UTC timezone for consistent date handling aligned with the stored data.
- **Type Breakdown**: Excludes issues without explicit type labels to provide cleaner metrics.
- **Report Generation**: For project-mode groups, `public/data/{group}/{project}/reports/` holds precomputed report content (test-plan steps, sprint/monthly goals + summary, deterministic metrics) as JSON. The dashboard renders this JSON (and existing milestone JSON for release notes) into MS Word client-side via `js/core/reports.js` (Office-HTML) + `downloadDoc()`. No Word files are stored; nothing regenerates this JSON automatically right now.
- **Section Parsing**: Issue descriptions are parsed for named sections (e.g. User Story). Section headers (`###` / `##`) are matched with a tolerant regex that handles case-insensitive matching.

## Troubleshooting

**Data not appearing in dashboard**
- Check that JSON files exist in `public/data/{group-slug}/fy{YYYY}/`
- Verify the fiscal year/month dropdowns match available data
- Ensure `public/data/groups.json` lists the correct group slugs
- Ensure the URL has a valid `?group=` parameter (e.g., `group.html?group=cloud-services`)

**Burndown chart shows no data**
- Ensure `daily_burndown` array is populated in the sprint JSON
- Check browser console for JavaScript errors

**Project filter shows no projects**
- Projects are derived from issues; sprints with no issues will have no filter options
