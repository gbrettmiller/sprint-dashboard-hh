# Multi-Group Dashboard Support

**Status: Implemented** — Merged via MR !4 on 2026-02-18. All groups (Cloud Services, Service Management, Data Services) are live with data populated.

## Context

The sprint metrics dashboard currently serves a single GitLab group (Cloud Services). To consolidate sprint visibility across teams, we're adding support for multiple groups with a group selector UI. Three groups will be configured:

| Group | GitLab ID | Slug |
|-------|-----------|------|
| Cloud Services | 90001 | cloud-services |
| Service Management | 90002 | service-management |
| Data Services | 90003 | data-services |

Existing Cloud Services data will be migrated into a `cloud-services/` subdirectory. A `groups.json` config file drives both the frontend and Python scripts.

---

## Step 1: Create branch and migrate data

- Create branch `multi-group-support`
- Create `public/data/groups.json`:
  ```json
  {
    "groups": [
      {"id": 90001, "name": "Cloud Services", "slug": "cloud-services"},
      {"id": 90002, "name": "Service Management", "slug": "service-management"},
      {"id": 90003, "name": "Data Services", "slug": "data-services"}
    ],
    "default": "cloud-services"
  }
  ```
- Move existing data: `public/data/fy2026/` → `public/data/cloud-services/fy2026/` and `public/data/current-sprint.json` → `public/data/cloud-services/current-sprint.json`

## Step 2: Update HTML — `public/index.html`

- Genericize title and header — remove "Cloud Services" references
- Insert group selector nav between `</header>` and `<nav class="nav-bar">`:
  ```html
  <nav class="group-bar" aria-label="Group selection">
    <div id="group-buttons" class="group-buttons" role="tablist" aria-label="Available groups"></div>
  </nav>
  ```

## Step 3: Update CSS — `public/css/styles.css`

Add group button styles after the header section, before nav-bar styles:
- `.group-bar` — margin-bottom spacing
- `.group-buttons` — flex container with gap and wrap
- `.group-btn` — styled like sprint tabs but slightly larger (14px font, 2px border, font-weight 600), using existing `--purple`, `--border`, `--radius` variables
- `.group-btn.active` — purple background/border, white text
- `.group-btn:hover` — purple border and text color
- `.group-btn:focus-visible` — existing focus ring

## Step 4: Update JavaScript — `public/js/main.js`

### State
Add two new variables:
- `let groupsConfig = null;` — loaded from groups.json
- `let activeGroup = null;` — currently selected group object

### New helper: `dataPath(relativePath)`
Returns `data/${activeGroup.slug}/${relativePath}` (or `data/${relativePath}` as fallback if no groups configured). Used by all data-loading functions.

### Update existing data loaders
- `loadCurrentSprint()`: change path to use `dataPath('current-sprint.json')`
- `loadFY()`: change path to use `dataPath(...)`

### New functions
- `loadGroupsConfig()` — fetches `data/groups.json`, sets `activeGroup` to default group. Falls back gracefully if file missing (single-group backward compat).
- `renderGroupButtons()` — populates `#group-buttons` with button elements. Hides the group bar if only 1 group. Uses `role="tab"`, `aria-selected`, `tabindex` for accessibility.
- `switchGroup(group)` — core group-switching logic:
  1. Update `activeGroup`
  2. Update button active states
  3. Reset state (`allData = {}`, `currentSprint = null`, `selectedSprint = null`, `projectFilter = null`)
  4. Destroy existing charts (burndown, type, velocity)
  5. Show loading indicator
  6. Reload data via `loadCurrentSprint()` → `discoverFYs()` → populate dropdowns → render

### Update `init()`
Add `await loadGroupsConfig()` and `renderGroupButtons()` at the top, before existing flow.

### Keyboard navigation
Add arrow key support for group tablist (ArrowLeft/ArrowRight to move focus between group buttons).

## Step 5: Update Python scripts

### `scripts/scheduled_update.py`

- Add `load_groups()` function: reads `public/data/groups.json`, falls back to `GITLAB_GROUP` env var
- Update `month_file_path(end_date)` → `month_file_path(end_date, group_slug)` — inserts slug in path: `DATA_DIR / group_slug / f"fy{fy}" / ...`
- Update `main()`: wrap body in `for group in load_groups()` loop. Each iteration processes one group with its own `current-sprint.json` at `DATA_DIR / group_slug / "current-sprint.json"`

### `scripts/backfill.py`

- Same `load_groups()` function
- Update `detect_tier()`: add `group_encoded` parameter instead of using global `GITLAB_GROUP`
- Update `output_path(end_date)` → `output_path(end_date, group_slug)` — same pattern as nightly
- Update `main()`: wrap in group loop, pass `group_slug` to `output_path()`

### CI/CD — No changes needed
The `.gitlab-ci.yml` uses `find public/data -name '*.json'` which will automatically pick up files in group subdirectories.

## Step 6: Verification

1. **Local frontend test**: `cd public && python -m http.server 8000`
   - Group buttons render (Cloud Services, Service Management, Data Services)
   - Cloud Services loads by default with existing data
   - Service Management/Data Services show "No sprint data found" (no data yet)
   - Switching back to Cloud Services restores charts
   - FY/month dropdowns reset on group switch
   - Keyboard nav works (Tab to group buttons, arrow keys)
2. **Data migration**: verify `public/data/cloud-services/fy2026/` has all JSON files
3. **Python scripts**: verify `scheduled_update.py` reads `groups.json` and processes groups (needs API token for full test)

---

## Files to modify
- `public/data/groups.json` — **new** config file
- `public/index.html` — header text, group selector nav
- `public/css/styles.css` — group button styles
- `public/js/main.js` — state, data paths, group loading/switching/rendering
- `scripts/scheduled_update.py` — group loop, path changes
- `scripts/backfill.py` — group loop, path changes, detect_tier param
