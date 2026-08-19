# GitLab Sprint Dashboard

A static dashboard for displaying sprint metrics, deployed via GitLab Pages. Data is collected automatically through scheduled CI/CD jobs using the GitLab API.

## Quick Start

> **Note:** This dashboard connects to an internal GitLab instance at `git.example.com`. You must be on NIPR, VPN, or AVD.

### View the dashboard locally

Sprint data is already committed to the repo — no credentials needed to browse it:

```bash
cd public
python -m http.server 8000
# Open http://localhost:8000
```

### Set up issue management scripts

To read and manage GitLab issues from the command line or with Claude Code:

```bash
pip install -r scripts/requirements.txt

# Add to ~/.bashrc or ~/.zshrc so these persist across sessions:
export GITLAB_URL="https://git.example.com"
export GITLAB_SSL_VERIFY="true"
export GITLAB_TOKEN="<your-personal-access-token>"  # Personal access token with api scope (Profile > Access Tokens)
export GITLAB_USERNAME="your.username"              # Optional: enables --assign-to-me flag
```

### Stay in sync with nightly data

The pipeline commits updated sprint data every night at 2 AM. Always pull before starting work to avoid merge conflicts:

```bash
git pull origin master
```

## Features

- **Multi-Group Support**: Home page lists all groups with active sprint status; each group has its own dashboard at a direct-linkable URL (`group.html?group={slug}`)
- **Per-Project Sprint Tracking**: Groups can use `mode: "projects"` to track sprints per project using Milestones instead of group-level Iterations. Each project gets its own card on the home page and its own dashboard (`group.html?group={slug}&project={project-slug}`)
- **Home Page Filtering**: Filter chips to show all projects or only those with active sprints
- **Branding**: Tinkers favicon on all pages; group and project logos on home page cards (configured via `logo` field in `groups.json`)
- **Sprint Navigation**: Browse sprints by fiscal year (Oct-Sep) and month
- **Burndown Chart**: Toggle between issue count and story points; ideal line accounts for weekends and US federal holidays; visual shading highlights non-working days
- **Project Filtering**: Filter all views by project using chip toggles
- **Issues Table**: Sortable, collapsible table of all sprint issues with status, weight, labels, and clickable milestone links
- **Velocity Chart**: Last 6 completed sprints with average velocity line
- **Type Breakdown**: Doughnut chart showing bug/improvement/feature distribution (excludes uncategorized issues)
- **Milestone Detail Pages**: View all issues for a milestone with parsed User Story sections
- **Releases Index**: Browse all milestones grouped by project, sorted newest-first with expand/collapse for projects with many milestones
- **Document Generation** (project-mode groups): Download **Release Notes**, **Test Plan**, and **Sprint Report** as MS Word from a completed sprint's dashboard, and a **Monthly Report** for a past month from a project dashboard. Word is generated client-side (Office-HTML); AI content (test steps, goals/summary) is precomputed by a scheduled CI job (`generate_reports.py`)
- **Accessibility**: Semantic HTML, ARIA attributes, keyboard navigation, screen reader support

## Project Structure

```
.gitlab-ci.yml          # CI/CD pipeline configuration
scripts/
  # Dashboard data collection
  backfill.py           # One-time historical data fetch
  scheduled_update.py   # Scheduled update for active sprints
  project_split.py      # One-time: split group data into per-project files
  generate_reports.py   # Scheduled: AI report JSON (test plans + sprint/monthly reports)
  api_commit.py         # Commits files via GitLab API

  # Issue management tools
  gitlab_api.py         # Shared GitLab API client
  issue_read.py         # Read issue details
  issue_list.py         # List and filter issues
  issue_create.py       # Create new issues
  issue_implement.py    # Implementation workflow helper
  issue_comment.py      # Add issue comments
  issue_update.py       # Update issue fields
  issue_close.py        # Close issues with notes

  requirements.txt      # Python dependencies
public/
  index.html            # Home page (group listing with sprint status)
  group.html            # Per-group sprint dashboard (?group={slug})
  milestone.html        # Milestone detail page
  releases.html         # Releases index page
  css/
    tokens.css          # Design tokens (CSS variables)
    styles.css          # Stylesheet (imports tokens.css)
  img/                  # Logos and branding images
  js/
    core/               # Pure logic (no DOM, no side effects)
      utils.js          # Shared utilities ($, esc, slugify, getParams, etc.)
      holidays.js       # US federal holidays, isWorkingDay, generateDateRange
      calculations.js   # Sprint progress, burndown, type breakdown, velocity
      parsing.js        # Markdown section parsing
      reports.js        # Word/Office-HTML doc builders, sprint/month predicates
    services/
      api.js            # Data fetching, path resolution, FY/sprint loading, report fetchers
    home.js             # UI: Home page (cards, filter)
    main.js             # UI: Sprint dashboard (charts, tables)
    milestone.js        # UI: Milestone detail (issues)
    releases.js         # UI: Releases index (milestone list)
    chart.min.js        # Chart.js v4.4.7 (vendored)
  data/
    groups.json         # Group configuration (names, IDs, slugs, logos, projects)
    {group-slug}/       # Group-scoped data directory
      current-sprint.json   # Active sprint (or `null` if none)
      fy{YYYY}/             # Sprint data organized by fiscal year
        {MM}-{mon}-{YYYY}.json  # Sprints ending in that month
      {project-slug}/       # Project-scoped data (for project-mode groups)
        current-sprint.json # Active sprint (or `null` if none)
        fy{YYYY}/           # Project sprint data by fiscal year
      milestones/           # Milestone data by project
        index.json          # All milestones index
        {project-slug}/     # Project-scoped milestone data
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

Milestone data is collected per project and stored separately from sprint data. Each milestone JSON file contains the full issue list with `description` fields, enabling section parsing for the milestone detail pages.

**Milestone index** (`milestones/index.json`) lists all milestones grouped by project, sorted by due date (newest first). The **releases page** reads this index and the **milestone detail page** reads individual milestone files.

Data is populated by `backfill.py` (historical) or `scheduled_update.py` (ongoing). Run backfill to initially populate all milestone data.

## Setup

### Prerequisites

- GitLab Premium or Ultimate (uses Iterations API)
- Python 3.8+
- CI/CD runner with network access to GitLab instance

### CI/CD Variables

Configure these in **Settings > CI/CD > Variables**:

| Variable | Description | Required Scope |
|----------|-------------|----------------|
| `GITLAB_URL` | GitLab instance URL (e.g., `https://gitlab.example.com`) | — |
| `GITLAB_TOKEN` | API token for reading iterations/issues (must have access to all configured groups) | `read_api` |
| `GITLAB_GROUP` | (Optional) Fallback group ID if `groups.json` is not configured | — |
| `CI_PUSH_TOKEN` | API token for committing data files | `api` + Maintainer role |
| `ANTHROPIC_API_KEY` | Anthropic-compatible API key for `generate_reports.py` (Ask Sage key on the CDSO network) | — |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible endpoint for `generate_reports.py`. Required on CI (no public egress) — Ask Sage gateway `https://api.genai.army.mil/server/anthropic` | — |
| `ANTHROPIC_MODEL` | (Optional) Model id for `generate_reports.py` (default `claude-haiku-4-5-20251001`) | — |
| `DOD_CA_CERT` | (Optional) DoD CA certificate bundle for SSL verification | File type |

**SSL Configuration**: If your GitLab instance uses DoD PKI certificates, see `docs/SSL_CERTIFICATE_SETUP.md` for instructions on enabling SSL verification. When not configured, the pipeline uses SSL bypass for compatibility.

### Group Configuration

Groups are configured in `public/data/groups.json`:

```json
{
  "groups": [
    {
      "id": 18274, "name": "CASS", "slug": "cass",
      "logo": "img/CASS-Logo.png",
      "mode": "projects",
      "transition_date": "2026-03-04",
      "projects": [
        {"id": 10324, "name": "MIRARS", "slug": "mirars", "logo": "img/MIRARS-Logo.png"},
        {"id": 10541, "name": "PPMT", "slug": "ppmt", "logo": "img/PPMT-Logo.png"},
        {"id": 10832, "name": "TOMT", "slug": "tomt"},
        {"id": 10313, "name": "ArmyWX", "slug": "armywx"},
        {"id": 10314, "name": "QuickSubmitForms", "slug": "quicksubmitforms"}
      ]
    },
    {"id": 18275, "name": "STAR", "slug": "star", "logo": "img/STAR-Logo.png"},
    {"id": 19322, "name": "P2DS", "slug": "p2ds", "logo": "img/P2DS-Logo.png"}
  ],
  "default": "cass"
}
```

Each group needs:
- `id` — GitLab group ID
- `name` — Display name shown on home page cards and breadcrumbs
- `slug` — URL parameter and directory name for data storage (e.g., `group.html?group=cass`, `public/data/cass/`)
- `logo` — (Optional) Path to logo image displayed on home page cards
- `default` — Slug of the group used as fallback when no group is specified

**Project mode** (`mode: "projects"`): Groups can track sprints per project instead of using a single group-level iteration. Additional fields:
- `mode` — Set to `"projects"` to enable per-project sprint tracking
- `transition_date` — Date cutoff; milestones with `start_date >= transition_date` are treated as sprints
- `projects` — Array of project objects with `id`, `name`, `slug`, and optional `logo` (falls back to group logo)

The `GITLAB_TOKEN` must have `read_api` access to all configured groups. If `groups.json` is not present, scripts fall back to the `GITLAB_GROUP` environment variable for single-group operation.

### Initial Data Load

Run the backfill job to fetch historical sprint data:

1. Go to **Build > Pipelines**
2. Click **Run pipeline**
3. Add variable: `BACKFILL = true`
4. Run the pipeline

This fetches all historical iterations and organizes them by fiscal year.

### Schedule Hourly Updates During Business Hours

Set up automatic updates throughout the workday:

1. Go to **Build > Pipeline schedules**
2. Create new schedule
3. Set cron: `0 7-17 * * 1-5` (every hour, 7 AM–5 PM, Monday–Friday)
4. Target branch: `master`

This keeps the active sprint burndown and issue data current throughout the day.

### Schedule Nightly Updates

Set up an overnight update to capture any late-day changes:

1. Go to **Build > Pipeline schedules**
2. Create new schedule
3. Set cron: `0 2 * * *` (2 AM daily)
4. Target branch: `master`

The nightly job updates the active sprint and two most recently completed sprints.

## Local Development

### Running the Dashboard Locally

```bash
cd public
python -m http.server 8000
# Open http://localhost:8000
```

### Running Data Scripts Locally

```bash
cd scripts
pip install -r requirements.txt

# Set environment variables
export GITLAB_URL="https://gitlab.example.com"
export GITLAB_TOKEN="your-read-api-token"

# Scripts read group config from public/data/groups.json automatically.
# Fallback: set GITLAB_GROUP="12345" if groups.json is not configured.

# Run backfill (writes to public/data/{group-slug}/)
python backfill.py

# Run scheduled update
python scheduled_update.py
```

## GitLab Issue Management

The project includes command-line tools for managing GitLab issues directly, enabling seamless workflows for backlog grooming and issue implementation.

### Setup

Set environment variables:

```bash
export GITLAB_URL="https://git.example.com"
export GITLAB_TOKEN="<your-personal-access-token>"  # api scope — covers all issue and data scripts
export GITLAB_SSL_VERIFY="true"

# Optional - set defaults to avoid repeating project/group IDs
export GITLAB_PROJECT="10324"
export GITLAB_GROUP="18274"
export GITLAB_USERNAME="your-username"      # For --assign-to-me flag
```

Create your personal access token at: **Profile > Access Tokens** — select `api` scope.

**Token Scopes:**
- Read-only operations (read, list): `read_api` scope minimum
- Write operations (create, update, comment, close): `api` scope required

> **Advanced:** `GITLAB_ISSUE_TOKEN` can override `GITLAB_TOKEN` for issue scripts only (useful if `GITLAB_TOKEN` is a narrow-scoped CI token rather than a personal access token).

### Available Commands

#### Read Issues

```bash
# Display issue details
python3 scripts/issue_read.py 10324 1183

# Include comments
python3 scripts/issue_read.py 10324 1183 --show-comments
```

#### List Issues

```bash
# List open issues in a project
python3 scripts/issue_list.py --project 10324 --state opened

# List issues with filters
python3 scripts/issue_list.py --group 18274 --labels "type::bug,priority::high"

# Output as JSON
python3 scripts/issue_list.py --project 10324 --format json --limit 10
```

#### Create Issues

```bash
# Interactive mode (prompts for title, description, labels, etc.)
python3 scripts/issue_create.py 10324

# Command-line mode
python3 scripts/issue_create.py 10324 \
  --title "Add CSV export feature" \
  --description "Export sprint data to CSV format" \
  --labels "type::feature,priority::high" \
  --weight 5
```

#### Update Issues

```bash
# Add labels to track progress
python3 scripts/issue_update.py 10324 1183 --add-labels "status::in-progress"

# Update multiple fields
python3 scripts/issue_update.py 10324 1183 \
  --weight 8 \
  --assignee username \
  --add-labels "status::testing"
```

#### Add Comments

```bash
# Add a comment
python3 scripts/issue_comment.py 10324 1183 \
  --body "Implementation complete, testing locally"

# Interactive mode (prompts for comment)
python3 scripts/issue_comment.py 10324 1183
```

#### Close Issues

```bash
# Simple close
python3 scripts/issue_close.py 10324 1183

# Close with note and labels
python3 scripts/issue_close.py 10324 1183 \
  --note "Implemented in commit abc123, verified in testing" \
  --add-labels "status::done,verified"
```

### Common Workflows

#### Workflow 1: Backlog Grooming with Claude Code

Use Claude Code to collaboratively design and create issues:

1. Discuss feature ideas with Claude
2. Refine requirements and acceptance criteria
3. Have Claude create the issue in GitLab with all details
4. Issue appears immediately on sprint board for planning

**Example:**
```
User: "I need a feature to export sprint metrics to CSV"
Claude: [Helps design feature, defines acceptance criteria]
User: "Create that issue in GitLab"
Claude: [Runs issue_create.py with full details]
Result: Issue #1245 created in GitLab
```

#### Workflow 2: Complete Issue Implementation

Implement an issue from start to finish with full GitLab tracking:

```bash
# 1. Read the issue
python3 scripts/issue_read.py 10324 1234 --show-comments

# 2. Get implementation guidance (branch name, commit template)
python3 scripts/issue_implement.py 10324 1234 --assign-to-me

# 3. Create branch and implement
git checkout -b 1234-feature-title

# 4. Update status as you work
python3 scripts/issue_update.py 10324 1234 --add-labels "status::in-progress"

# 5. Add progress comments
python3 scripts/issue_comment.py 10324 1234 --body "Implementation complete"

# 6. Update status during testing
python3 scripts/issue_update.py 10324 1234 \
  --add-labels "status::testing" \
  --remove-labels "status::in-progress"

# 7. Close when verified
python3 scripts/issue_close.py 10324 1234 \
  --note "Implemented and verified" \
  --add-labels "status::done"
```

This maintains a complete audit trail in GitLab that management can track on sprint boards.

### Script Help

All scripts include detailed help:

```bash
python3 scripts/issue_read.py --help
python3 scripts/issue_list.py --help
python3 scripts/issue_create.py --help
python3 scripts/issue_update.py --help
python3 scripts/issue_comment.py --help
python3 scripts/issue_close.py --help
python3 scripts/issue_implement.py --help
```

## Deployment

The dashboard deploys automatically via GitLab Pages when changes are pushed to `master`. The `pages` job in `.gitlab-ci.yml` publishes the `public/` directory.

Access the deployed dashboard at: `https://<namespace>.gitlab.io/<project-path>/`

## Technical Notes

- **Frontend Architecture**: JavaScript follows a four-layer architecture: Design System (`css/tokens.css`) → Core (`js/core/`) → Services (`js/services/`) → UI (`js/*.js`). All files use native ES modules with no build step. Shared logic lives in core/services; page modules handle rendering only.
- **Data Cutoff**: No sprint, milestone, or release data before October 2025 (FY2026) is displayed. Controlled by `EARLIEST_FY` and `EARLIEST_DATE` constants in `js/services/api.js`.
- **Null Sentinel Files**: `scheduled_update.py` writes `null` to `current-sprint.json` when no active sprint exists (instead of deleting the file). This prevents 404 console errors while the frontend displays "No active sprint" as before.
- **API Commits**: Data files are committed via the GitLab Commits API rather than git push. This bypasses signed commit requirements on some instances.
- **SSL Verification**: Can be enabled via the `DOD_CA_CERT` CI/CD variable (see `docs/SSL_CERTIFICATE_SETUP.md`). When configured, DoD certificates are combined with public CAs to support both PyPI package downloads and GitLab API access. Falls back to SSL bypass if not configured.
- **Iterations vs Milestones**: Scripts auto-detect whether the instance uses Iterations (Premium) or Milestones (Free/Premium). Groups with `mode: "projects"` use project-level Milestones for sprints (filtered by `transition_date`), while historical data uses group-level Iterations.
- **Per-Project Data**: For project-mode groups, `project_split.py` splits historical group-level sprint data into per-project files with recalculated burndown and stats. `scheduled_update.py` and `backfill.py` handle ongoing project-level milestone collection.
- **Fiscal Year**: Sprints are organized by fiscal year (October-September) based on sprint end date. `loadFY()` only fetches months up to the current date to avoid 404s for future months.
- **Working Days**: Burndown ideal line calculation excludes weekends and US federal holidays.
- **Non-Working Day Shading**: Chart.js plugin uses UTC timezone for consistent date handling aligned with server-generated data.
- **Type Breakdown**: Excludes issues without explicit type labels to provide cleaner metrics.
- **Milestone Data**: Collected at the project level via `/api/v4/projects/:id/milestones`. Projects are discovered from sprint issue data. Issue descriptions are stored for section parsing (User Story, Acceptance Criteria, Description).
- **Report Generation**: For project-mode groups, `generate_reports.py` (scheduled, after `scheduled_update`) precomputes report content as JSON for completed milestone-sprints and past months — test-plan steps and sprint/monthly goals+summary via the Anthropic API, plus deterministic metrics. It is idempotent (skips existing output) and reads all secrets from env/CI variables. The dashboard renders this JSON (and existing milestone JSON for release notes) into MS Word client-side via `js/core/reports.js` (Office-HTML) + `downloadDoc()`. No Word files are stored.
- **Section Parsing**: Issue descriptions are parsed for named sections (e.g. User Story). Section headers (`###` / `##`) are matched with a tolerant regex that handles case-insensitive matching.

## Troubleshooting

**Pipeline fails with 401 Unauthorized**
- Verify `GITLAB_TOKEN` has `read_api` scope and access to the target group

**Pipeline fails with SSL certificate errors**
- See `docs/SSL_CERTIFICATE_SETUP.md` for configuring DoD certificates
- Ensure `DOD_CA_CERT` variable is set as File type (not Variable)
- Check that the certificate bundle contains valid PEM-formatted certificates

**Pip install fails in pipeline**
- Ensure pip packages are installed before DoD certificate configuration
- Pip needs public CAs to access PyPI; DoD certs are appended afterward

**Data not appearing in dashboard**
- Check that JSON files exist in `public/data/{group-slug}/fy{YYYY}/`
- Verify the fiscal year/month dropdowns match available data
- Ensure `public/data/groups.json` lists the correct group slugs
- Ensure the URL has a valid `?group=` parameter (e.g., `group.html?group=cass`)

**Burndown chart shows no data**
- Ensure `daily_burndown` array is populated in the sprint JSON
- Check browser console for JavaScript errors

**Project filter shows no projects**
- Projects are derived from issues; sprints with no issues will have no filter options
