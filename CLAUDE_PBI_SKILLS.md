# Implementation Plan: GitLab Issue Management Skills

## Context

The Sprint Metrics Dashboard currently collects and displays sprint data from GitLab, but lacks direct integration for managing the project's own issues. This implementation adds custom Claude Code skills (`/read-issue`, `/list-issues`, `/create-issue`, `/implement-issue`) to enable seamless issue management directly from the development environment.

**Why this is needed:**
- The team manages project issues in the same GitLab project that hosts the code
- Current workflow requires switching to GitLab web UI to read/create issues
- Skills will enable Claude to read issue descriptions and implement the work directly
- Will facilitate collaborative PBI generation and implementation

**Environment considerations:**
- Self-hosted GitLab at git.example.com with DoD PKI certificates
- SSL verification ENABLED (`GITLAB_SSL_VERIFY=true`) - DoD certs in system CA bundle
- Authentication via `GITLAB_TOKEN` (already configured in CI/CD)
- Must follow existing Python script patterns for consistency

## Implementation Approach

### Architecture

**Shared Module Pattern**: Create centralized `scripts/gitlab_api.py` containing reusable GitLab API client, then build four standalone CLI scripts that leverage this shared module.

**Benefits:**
- Eliminates code duplication (existing scripts have identical `_get()` pagination logic)
- Consistent error handling and retry patterns across all skills
- Easy to maintain and extend with new skills
- Can optionally refactor existing scripts to use shared client

### File Structure

```
sprint-metrics-dashboard/
├── .claude/
│   ├── settings.local.json      # UPDATE: Add skill definitions
│   └── skills/                  # CREATE: Skill wrapper scripts
│       ├── read-issue.sh
│       ├── list-issues.sh
│       ├── create-issue.sh
│       └── implement-issue.sh
├── scripts/
│   ├── gitlab_api.py            # CREATE: Shared API client library
│   ├── issue_read.py            # CREATE: Read single issue
│   ├── issue_list.py            # CREATE: List issues with filters
│   ├── issue_create.py          # CREATE: Create new issue
│   └── issue_implement.py       # CREATE: Implementation workflow
```

## Implementation Steps

### Step 1: Create Shared API Client (`scripts/gitlab_api.py`)

**Purpose**: Centralize GitLab API operations to eliminate duplication.

**Key components:**
- `GitLabClient` class with session management, SSL handling, authentication
- `get()` method implementing pagination, rate limiting (429), retry logic (5xx) - extracted from existing `_get()` function pattern
- `post()` and `put()` methods with retry logic
- Issue-specific methods: `get_issue()`, `list_issues()`, `create_issue()`, `get_issue_notes()`
- Helper methods: `get_project()`, `get_group()`, `detect_tier()`

**Pattern to follow** (from [scripts/backfill.py:85-120](scripts/backfill.py#L85-L120)):
```python
# Existing _get() function shows the pattern to replicate:
# - Pagination via Link headers
# - Rate limiting with Retry-After header
# - Exponential backoff for 5xx errors
# - per_page=100 for efficient API usage
```

**Configuration pattern** (from [scripts/backfill.py:62-68](scripts/backfill.py#L62-L68)):
```python
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
API = f"{GITLAB_URL}/api/v4"
HEADERS = {"PRIVATE-TOKEN": GITLAB_TOKEN}
VERIFY_SSL = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
```

### Step 2: Implement `/read-issue` Skill

**Script**: `scripts/issue_read.py`

**Usage**: `python3 scripts/issue_read.py <project_id> <issue_iid> [--show-comments]`

**Functionality:**
1. Use `GitLabClient.get_issue()` to fetch issue details via `GET /projects/:id/issues/:issue_iid`
2. Optionally fetch comments via `GET /projects/:id/issues/:issue_iid/notes`
3. Format output with issue metadata (title, state, labels, weight, assignee, iteration, etc.)
4. Display description and comments (if requested)

**Output format:**
```
Issue #<iid>: <title>
Project: <name> (<id>)
State: <state> | Author: <author> | Assignee: <assignee>
Labels: <labels> | Weight: <weight> | Iteration: <iteration>
URL: <web_url>

Description:
────────────
<description>

[Comments if --show-comments]
```

**Wrapper**: `.claude/skills/read-issue.sh` - simple bash wrapper that calls Python script

### Step 3: Implement `/list-issues` Skill

**Script**: `scripts/issue_list.py`

**Usage**: `python3 scripts/issue_list.py [--group <id>] [--project <id>] [--state <state>] [--labels <labels>] [--format <format>]`

**Functionality:**
1. Use `GitLabClient.list_issues()` with filters (state, labels, iteration, assignee, etc.)
2. Support both group-level (`GET /groups/:id/issues`) and project-level (`GET /projects/:id/issues`)
3. Format output as table (default), JSON, or simple list

**Output formats:**
- **Table**: Columns for IID, Project, Title, State, Weight, Labels
- **JSON**: Structured data for programmatic use
- **Simple**: One-line per issue for quick scanning

**Wrapper**: `.claude/skills/list-issues.sh`

### Step 4: Implement `/create-issue` Skill

**Script**: `scripts/issue_create.py`

**Usage**: `python3 scripts/issue_create.py <project_id> [--title <title>] [--description <desc>] [--labels <labels>] [--weight <n>] [...]`

**Functionality:**
1. **Interactive mode** (when no `--title` provided): Prompt for title, description, labels, weight, assignee, iteration
2. **Non-interactive mode** (when `--title` provided): Use command-line arguments
3. Use `GitLabClient.create_issue()` via `POST /projects/:id/issues`
4. Validate project exists, iteration/milestone valid (if provided)
5. Return issue URL and metadata

**Token requirement**: Requires `api` scope (not just `read_api`)

**Wrapper**: `.claude/skills/create-issue.sh`

### Step 5: Implement `/implement-issue` Skill

**Script**: `scripts/issue_implement.py`

**Usage**: `python3 scripts/issue_implement.py <project_id> <issue_iid> [--assign-to-me]`

**Functionality:**
1. Fetch issue details via `GET /projects/:id/issues/:issue_iid`
2. Display issue summary with description
3. Optionally assign to current user via `PUT /projects/:id/issues/:issue_iid` (if `--assign-to-me`)
4. Generate commit message template with issue reference
5. Suggest branch name: `<iid>-<slugified-title>`
6. Display implementation guidance

**Output:**
```
Implementation Plan for Issue #<iid>
Issue: #<iid> - <title>
Type: <type> | Weight: <weight> | Assignee: <assignee>

Description:
────────────
<description>

Suggested Branch: git checkout -b <iid>-<slug>

Commit Message Template:
────────────
<type>: <brief>

Implements #<iid> - <title>

Issue: <web_url>

Next Steps:
1. Create feature branch
2. Implement changes
3. Reference issue in commits and MRs
```

**Wrapper**: `.claude/skills/implement-issue.sh`

### Step 6: Configure Skills in Claude

**Update**: [.claude/settings.local.json](.claude/settings.local.json)

Add `skills` array with definitions for all four skills:
```json
{
  "skills": [
    {
      "name": "read-issue",
      "description": "Fetch and display GitLab issue details",
      "command": ".claude/skills/read-issue.sh",
      "parameters": [...]
    },
    // ... three more skill definitions
  ]
}
```

Each skill definition includes:
- Name and description
- Command path (relative to project root)
- Parameter definitions (name, description, required/optional, flags)

## Critical Files Referenced

### Files to Read (for patterns):
- [scripts/backfill.py](scripts/backfill.py) - `_get()` pagination/retry pattern (lines 85-120), session setup (lines 62-68)
- [scripts/scheduled_update.py](scripts/scheduled_update.py) - Similar patterns, shows `last_updated` timestamp format
- [scripts/api_commit.py](scripts/api_commit.py) - GitLab API POST operations, error handling, Base64 encoding
- [.gitlab-ci.yml](.gitlab-ci.yml) - Environment variable setup (lines 3-8)

### Files to Create:
- `scripts/gitlab_api.py` - Shared API client (~200 lines)
- `scripts/issue_read.py` - Read skill (~150 lines)
- `scripts/issue_list.py` - List skill (~200 lines)
- `scripts/issue_create.py` - Create skill (~250 lines)
- `scripts/issue_implement.py` - Implement skill (~200 lines)
- `.claude/skills/*.sh` - Four bash wrappers (~5 lines each)

### Files to Update:
- `.claude/settings.local.json` - Add skill definitions (~80 lines JSON)

## Reusable Components from Existing Code

### From `backfill.py` and `scheduled_update.py`:
1. **`_get()` function** (lines 85-120) - Pagination, rate limiting, retry logic
   - Extract into `GitLabClient.get()` method
2. **Session setup** (lines 62-68) - Environment variable reading, header construction
   - Extract into `GitLabClient.__init__()`
3. **Logging pattern** (lines 54-56) - Consistent log format
   - Use same pattern in all new scripts
4. **Tier detection** (lines 147-156) - Auto-detect Iterations vs Milestones
   - Extract into `GitLabClient.detect_tier()` method

### From `api_commit.py`:
1. **POST request pattern** (lines 62-78) - Error handling for create operations
   - Adapt for `GitLabClient.post()` method
2. **File existence check** (lines 44-51) - HEAD request pattern
   - May be useful for future file-related operations

## Environment Setup

### Required Environment Variables:
- `GITLAB_URL` - GitLab instance URL (default: https://gitlab.com)
- `GITLAB_TOKEN` - API token
  - Read-only skills: `read_api` scope
  - Create skill: `api` scope
- `GITLAB_SSL_VERIFY` - Set to `true` (default) for proper SSL verification
- `GITLAB_GROUP` - Optional, default group ID for `/list-issues --group`
- `GITLAB_USERNAME` - Optional, for `/implement-issue --assign-to-me`

### Local Testing Setup:
```bash
export GITLAB_URL="https://git.example.com"
export GITLAB_TOKEN="<your-token>"
export GITLAB_SSL_VERIFY="true"  # SSL verification enabled
export GITLAB_GROUP="12345"  # tinkers group
```

## Verification & Testing

### Unit Testing (per script):

1. **Test `gitlab_api.py`**:
   ```bash
   # Verify client initialization and authentication
   python3 -c "from scripts.gitlab_api import GitLabClient; client = GitLabClient(); print(client.get('/user'))"
   ```

2. **Test `/read-issue`**:
   ```bash
   # Read a known issue
   python3 scripts/issue_read.py 91001 1183

   # Read with comments
   python3 scripts/issue_read.py 91001 1183 --show-comments

   # Test error handling (invalid issue)
   python3 scripts/issue_read.py 91001 999999
   ```

3. **Test `/list-issues`**:
   ```bash
   # List group issues
   python3 scripts/issue_list.py --group 18274 --state opened

   # List with labels filter
   python3 scripts/issue_list.py --project 91001 --labels "type::bug"

   # Test JSON output
   python3 scripts/issue_list.py --project 91001 --format json --limit 5
   ```

4. **Test `/create-issue`**:
   ```bash
   # Interactive mode
   python3 scripts/issue_create.py 91001

   # Non-interactive mode
   python3 scripts/issue_create.py 91001 \
     --title "Test issue" \
     --description "Test description" \
     --labels "test"
   ```

5. **Test `/implement-issue`**:
   ```bash
   # Basic workflow
   python3 scripts/issue_implement.py 91001 1183

   # With assignment
   export GITLAB_USERNAME="your-username"
   python3 scripts/issue_implement.py 91001 1183 --assign-to-me
   ```

### Integration Testing (via Claude):

```bash
# From Claude Code prompt
/read-issue 91001 1183
/list-issues --project 91001 --state opened
/create-issue 91001 --title "Test from Claude"
/implement-issue 91001 1183
```

### End-to-End Workflow Test:

1. List open issues: `/list-issues --project 91001 --state opened`
2. Read specific issue: `/read-issue 91001 <iid> --show-comments`
3. Start implementation: `/implement-issue 91001 <iid> --assign-to-me`
4. [Make code changes]
5. Create commit with issue reference
6. Create new issue: `/create-issue 91001 --title "Follow-up task"`

### Expected Outcomes:
- All scripts execute without errors in local environment
- API responses are properly formatted and displayed
- Error messages are clear and actionable
- Skills are callable from Claude Code with `/` prefix
- SSL verification works correctly with DoD certificates
- Rate limiting and retry logic handle API throttling gracefully

## Implementation Order & Dependencies

```
Phase 1: Foundation
├─ 1. Create gitlab_api.py (no dependencies)
└─ 2. Test API client standalone

Phase 2: Read-Only Skills (parallel)
├─ 3. Create issue_read.py (depends on gitlab_api.py)
├─ 4. Create issue_list.py (depends on gitlab_api.py)
├─ 5. Create shell wrappers (read-issue.sh, list-issues.sh)
└─ 6. Test both skills locally

Phase 3: Write Skills (parallel)
├─ 7. Create issue_create.py (depends on gitlab_api.py)
├─ 8. Create issue_implement.py (depends on gitlab_api.py)
├─ 9. Create shell wrappers (create-issue.sh, implement-issue.sh)
└─ 10. Test both skills locally

Phase 4: Integration
├─ 11. Update .claude/settings.local.json with all skill definitions
├─ 12. Test skills via Claude Code interface
└─ 13. Document usage in CLAUDE.md
```

## Rollout & Documentation

1. **Update CLAUDE.md** - Add section on skill usage with examples
2. **Update README.md** - Brief mention of skill availability
3. **Create examples** - Add sample workflows to project documentation
4. **Team announcement** - Share skill commands and use cases

## Future Enhancements

**Short-term:**
- `/comment-issue` - Add comments to issues
- `/update-issue` - Modify issue fields (labels, state, assignee)
- `/close-issue` - Close issues with optional comment

**Long-term:**
- Merge request integration (`/create-mr`, `/review-mr`)
- Issue templates for common task types
- Time tracking integration
- Issue dependency management

## Notes

- All scripts require `requests>=2.28` (already in `requirements.txt`)
- No new dependencies needed
- Skills work in both local dev and CI/CD environments
- Token scopes: `read_api` for reading, `api` for creating
- SSL verification enabled - DoD certificates already in system CA bundle
- Skills follow existing project patterns for consistency
