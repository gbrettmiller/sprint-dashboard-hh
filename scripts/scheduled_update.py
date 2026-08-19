#!/usr/bin/env python3
"""
Scheduled update script: Updates the current active sprint and two most recently
completed sprints. Runs on any configured CI/CD schedule (hourly during business
hours and at 2 AM nightly).

- Active sprint → public/data/current-sprint.json AND its fiscal year month file
- Completed sprints → their respective fiscal year month files

Usage:
    export GITLAB_TOKEN=glpat-...
    export GITLAB_URL=https://gitlab.com
    export GITLAB_GROUP=engineering-team2841005  # fallback if no groups.json
    python3 scripts/scheduled_update.py

Groups are loaded from public/data/groups.json when available. Falls back to
GITLAB_GROUP env var for backward compatibility.
"""

import os
import re
import sys
import json
import time
import logging
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
GITLAB_GROUP = os.environ.get("GITLAB_GROUP", "")
API = f"{GITLAB_URL}/api/v4"
HEADERS = {"PRIVATE-TOKEN": GITLAB_TOKEN}
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"

MONTH_NAMES = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr", 5: "may", 6: "jun",
    7: "jul", 8: "aug", 9: "sep", 10: "oct", 11: "nov", 12: "dec",
}

TYPE_LABELS = {"type::bug", "type::improvement", "type::new-feature", "type::new feature"}
GROUPS_FILE = DATA_DIR / "groups.json"


def load_groups():
    """Load group definitions from groups.json, falling back to GITLAB_GROUP env var."""
    if GROUPS_FILE.exists():
        with open(GROUPS_FILE) as f:
            config = json.load(f)
        groups = config.get("groups", [])
        if groups:
            return groups
    # Backward compatibility: single group from env var
    if GITLAB_GROUP:
        return [{"id": GITLAB_GROUP, "name": GITLAB_GROUP, "slug": GITLAB_GROUP}]
    return []


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
log = logging.getLogger("nightly")

# ---------------------------------------------------------------------------
# HTTP helpers (same as backfill)
# ---------------------------------------------------------------------------
VERIFY_SSL = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")

session = requests.Session()
session.headers.update(HEADERS)
session.verify = VERIFY_SSL


def _get(url, params=None):
    results = []
    params = dict(params or {})
    params.setdefault("per_page", 100)
    page_url = url

    while page_url:
        for attempt in range(5):
            resp = session.get(page_url, params=params)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning("Rate-limited, sleeping %ds", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        else:
            resp.raise_for_status()

        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data

        page_url = None
        params = {}
        link = resp.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                page_url = part.split("<")[1].split(">")[0]
                break

    return results


# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------
def detect_tier(group_encoded):
    url = f"{API}/groups/{group_encoded}/iterations"
    resp = session.get(url, params={"per_page": 1})
    if resp.status_code == 200:
        log.info("Premium detected – using Group Iterations API")
        return "iterations"
    log.info("Free tier detected – using Group Milestones API")
    return "milestones"


# ---------------------------------------------------------------------------
# Fetch sprints
# ---------------------------------------------------------------------------
def fetch_iterations_by_state(group_encoded, state):
    url = f"{API}/groups/{group_encoded}/iterations"
    return _get(url, {"state": state, "include_ancestors": "false"})


def fetch_milestones_by_state(group_encoded, state):
    url = f"{API}/groups/{group_encoded}/milestones"
    return _get(url, {"state": state})


def normalize_iteration(it):
    return {
        "id": it["id"],
        "iid": it.get("iid"),
        "title": it["title"],
        "start_date": it["start_date"],
        "end_date": it["due_date"],
        "state": it["state"],
        "source": "iteration",
        "description": it.get("description") or None,
    }


def normalize_milestone(ms):
    return {
        "id": ms["id"],
        "iid": ms.get("iid"),
        "title": ms["title"],
        "start_date": ms["start_date"],
        "end_date": ms["due_date"],
        "state": ms["state"],
        "source": "milestone",
        "description": ms.get("description") or None,
    }


def get_target_sprints(group_encoded, tier):
    """Return (active_sprint_or_None, [up to 2 most recently closed sprints])."""
    active = None
    closed = []

    if tier == "iterations":
        # Active
        raw = fetch_iterations_by_state(group_encoded, "current")
        # Skip iterations without a title (unused cadence placeholders)
        raw = [it for it in raw if it.get("title")]
        if raw:
            active = normalize_iteration(raw[0])
        # Closed
        raw = _get(
            f"{API}/groups/{group_encoded}/iterations",
            {"state": "closed", "include_ancestors": "false"},
        )
        closed = [normalize_iteration(it) for it in raw if it.get("title")]
    else:
        # Fetch both active and closed milestones
        today = date.today()
        all_milestones = []
        for state in ("active", "closed"):
            raw = fetch_milestones_by_state(group_encoded, state)
            all_milestones.extend(
                m for m in raw if m.get("start_date") and m.get("due_date")
            )

        for m in all_milestones:
            s = date.fromisoformat(m["start_date"])
            e = date.fromisoformat(m["due_date"])
            if s <= today <= e:
                active = normalize_milestone(m)
            elif e < today:
                # Past-due milestones count as completed regardless of API state
                closed.append(normalize_milestone(m))

    # Sort closed by end_date descending, take 2
    closed.sort(key=lambda s: s["end_date"], reverse=True)
    recent_closed = closed[:2]

    return active, recent_closed


# ---------------------------------------------------------------------------
# Issue fetching and sprint record building (reused from backfill)
# ---------------------------------------------------------------------------
def fetch_sprint_issues(group_encoded, sprint):
    if sprint["source"] == "iteration":
        params = {"iteration_id": sprint["id"]}
    else:
        params = {"milestone": sprint["title"]}
    url = f"{API}/groups/{group_encoded}/issues"
    params["scope"] = "all"
    params["state"] = "all"
    return _get(url, params)


def get_milestone_events(project_id, issue_iid):
    url = f"{API}/projects/{project_id}/issues/{issue_iid}/resource_milestone_events"
    try:
        return _get(url)
    except Exception:
        return []


def get_iteration_events(project_id, issue_iid):
    url = f"{API}/projects/{project_id}/issues/{issue_iid}/resource_iteration_events"
    try:
        return _get(url)
    except Exception:
        return []


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_sprint_record(group_encoded, sprint, issues_raw):
    s_start = date.fromisoformat(sprint["start_date"])
    s_end = date.fromisoformat(sprint["end_date"])

    issues_table = []
    type_counts = {"bug": 0, "improvement": 0, "new_feature": 0, "other": 0}
    total_weight = 0
    initial_ids = set()

    daily_adds = {}
    daily_removes = {}
    daily_closes = {}

    for issue in issues_raw:
        iid = issue["iid"]
        project_id = issue["project_id"]
        weight = issue.get("weight") or 0
        total_weight += weight

        labels = [l for l in issue.get("labels", [])]
        label_set_normalized = {l.lower() for l in labels}

        matched = label_set_normalized & TYPE_LABELS
        if "type::bug" in matched:
            type_counts["bug"] += 1
        elif "type::improvement" in matched:
            type_counts["improvement"] += 1
        elif "type::new-feature" in matched or "type::new feature" in matched:
            type_counts["new_feature"] += 1
        else:
            type_counts["other"] += 1

        date_added = None
        date_removed = None

        if sprint["source"] == "milestone":
            events = get_milestone_events(project_id, iid)
            for ev in events:
                ms = ev.get("milestone")
                if ms and ms.get("id") == sprint["id"]:
                    action = ev.get("action")
                    ev_date = ev["created_at"][:10]
                    if action == "add":
                        date_added = ev_date
                    elif action == "remove":
                        date_removed = ev_date
        else:
            events = get_iteration_events(project_id, iid)
            for ev in events:
                it = ev.get("iteration")
                if it and it.get("id") == sprint["id"]:
                    action = ev.get("action")
                    ev_date = ev["created_at"][:10]
                    if action == "add":
                        date_added = ev_date
                    elif action == "remove":
                        date_removed = ev_date

        if date_added is None:
            date_added = sprint["start_date"]

        added_d = date.fromisoformat(date_added)
        if added_d <= s_start:
            initial_ids.add(issue["id"])
        else:
            daily_adds.setdefault(added_d, []).append(weight)

        if date_removed:
            removed_d = date.fromisoformat(date_removed)
            if removed_d <= s_end:
                daily_removes.setdefault(removed_d, []).append(weight)

        date_closed = None
        if issue.get("closed_at"):
            date_closed = issue["closed_at"][:10]
            closed_d = date.fromisoformat(date_closed)
            if s_start <= closed_d <= s_end:
                daily_closes.setdefault(closed_d, []).append(weight)

        web_url = issue.get("web_url", "")
        parts = web_url.split("/-/")
        project_name = parts[0].rsplit("/", 1)[-1] if parts else ""

        milestone = None
        ms_obj = issue.get("milestone")
        if ms_obj:
            milestone = ms_obj.get("title")

        issues_table.append({
            "id": issue["id"],
            "iid": iid,
            "title": issue["title"],
            # Stored so standard groups (e.g. Service Management) can build Release Notes from
            # the sprint record directly — they have no per-project milestone JSON.
            "description": issue.get("description") or "",
            "project_id": project_id,
            "project_name": project_name,
            "weight": weight,
            "state": issue["state"],
            "labels": labels,
            "milestone": milestone,
            "date_added_to_sprint": date_added,
            "date_closed": date_closed,
            "date_removed_from_sprint": date_removed,
            "web_url": web_url,
        })

    initial_count = len(initial_ids)
    initial_weight = sum(
        i.get("weight") or 0 for i in issues_raw if i["id"] in initial_ids
    )

    remaining_count = initial_count
    remaining_weight = initial_weight
    burndown = []

    # For active sprint, only build burndown up to today
    burn_end = min(s_end, date.today())

    for d in daterange(s_start, burn_end):
        for w in daily_adds.get(d, []):
            remaining_count += 1
            remaining_weight += w
        for w in daily_removes.get(d, []):
            remaining_count -= 1
            remaining_weight -= w
        for w in daily_closes.get(d, []):
            remaining_count -= 1
            remaining_weight -= w

        burndown.append({
            "date": d.isoformat(),
            "remaining_count": max(remaining_count, 0),
            "remaining_weight": max(remaining_weight, 0),
        })

    completed_issues = [i for i in issues_table if i["state"] == "closed"]
    completed_count = len(completed_issues)
    completed_weight = sum(i["weight"] for i in completed_issues)

    return {
        "id": sprint["id"],
        "title": sprint["title"],
        "start_date": sprint["start_date"],
        "end_date": sprint["end_date"],
        "state": sprint["state"],
        "source": sprint["source"],
        "goal": sprint.get("description") or None,
        "initial_totals": {
            "count": initial_count,
            "weight": initial_weight,
        },
        "burndown": burndown,
        "type_breakdown": type_counts,
        "completed": {
            "count": completed_count,
            "weight": completed_weight,
        },
        "issues": issues_table,
    }


# ---------------------------------------------------------------------------
# Fiscal year / month helpers
# ---------------------------------------------------------------------------
def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def month_file_path(end_date: date, group_slug: str, project_slug: str = None) -> Path:
    fy = fiscal_year(end_date)
    month_str = f"{end_date.month:02d}-{MONTH_NAMES[end_date.month]}-{end_date.year}"
    if project_slug:
        return DATA_DIR / group_slug / project_slug / f"fy{fy}" / f"{month_str}.json"
    return DATA_DIR / group_slug / f"fy{fy}" / f"{month_str}.json"


def remove_sprint_from_other_month_files(target_path: Path, sprint_id):
    """Remove any record with sprint_id from sibling month files (not target_path).

    A sprint whose end_date changes across a month or fiscal-year boundary files
    under a new month, but the stale record in its previous month file is never
    cleaned up by the within-file upsert. This strips those orphans so a sprint id
    appears in at most one month file within its group/project scope.
    """
    # target_path = .../{group}[/{project}]/fy{YYYY}/{month}.json
    # scope_root  = .../{group}[/{project}] — glob fy*/*.json stays within this
    # scope (it does not descend into project subdirs or milestones/).
    scope_root = target_path.parent.parent
    for other in scope_root.glob("fy*/*.json"):
        if other == target_path:
            continue
        try:
            data = json.loads(other.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "sprints" not in data:
            continue
        kept = [s for s in data["sprints"] if s.get("id") != sprint_id]
        if len(kept) != len(data["sprints"]):
            data["sprints"] = kept
            other.write_text(json.dumps(data, indent=2))
            log.info("Removed stale sprint id=%s from %s", sprint_id, other)


def upsert_sprint_in_month_file(path: Path, record):
    """Insert or replace a sprint record in a month JSON file."""
    remove_sprint_from_other_month_files(path, record["id"])
    if path.exists():
        month_data = json.loads(path.read_text())
    else:
        end_d = date.fromisoformat(record["end_date"])
        month_data = {
            "fiscal_year": fiscal_year(end_d),
            "month": end_d.month,
            "year": end_d.year,
            "sprints": [],
        }

    # Replace existing or append
    sprints = month_data["sprints"]
    replaced = False
    for i, s in enumerate(sprints):
        if s["id"] == record["id"]:
            sprints[i] = record
            replaced = True
            break
    if not replaced:
        sprints.append(record)

    sprints.sort(key=lambda s: s["start_date"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(month_data, indent=2))


# ---------------------------------------------------------------------------
# Project-mode sprint collection (milestones as sprints per project)
# ---------------------------------------------------------------------------
def fetch_project_sprint_issues(project_id, sprint):
    """Fetch issues for a project-level milestone sprint."""
    url = f"{API}/projects/{project_id}/issues"
    return _get(url, {
        "milestone": sprint["title"],
        "scope": "all",
        "state": "all",
    })


def process_project_mode(group):
    """Process a group where each project has its own sprint milestones."""
    group_slug = group["slug"]
    group_name = group["name"]
    transition_date = group.get("transition_date", "1970-01-01")
    projects = group.get("projects", [])
    seen_projects = set()

    for project in projects:
        project_id = project["id"]
        project_slug = project["slug"]
        project_name = project["name"]

        log.info("-" * 40)
        log.info("Project: %s (ID: %s, slug: %s)", project_name, project_id, project_slug)

        # Fetch project-level milestones (active + closed)
        all_milestones = []
        for state in ("active", "closed"):
            url = f"{API}/projects/{project_id}/milestones"
            try:
                raw = _get(url, {"state": state})
            except Exception as e:
                log.warning("Could not fetch %s milestones for %s: %s", state, project_name, e)
                continue
            # Filter to sprint milestones: must have start_date and due_date,
            # and start_date >= transition_date
            for m in raw:
                if (m.get("start_date") and m.get("due_date")
                        and m["start_date"] >= transition_date):
                    all_milestones.append(m)

        if not all_milestones:
            log.info("  No sprint milestones found (after transition date)")

        # Identify current and recent closed sprints
        today = date.today()
        active = None
        closed = []

        for m in all_milestones:
            s = date.fromisoformat(m["start_date"])
            e = date.fromisoformat(m["due_date"])
            if s <= today <= e:
                active = normalize_milestone(m)
            elif e < today:
                closed.append(normalize_milestone(m))

        closed.sort(key=lambda s: s["end_date"], reverse=True)
        recent_closed = closed[:2]

        # --- Process active sprint ---
        current_sprint_path = DATA_DIR / group_slug / project_slug / "current-sprint.json"

        if active:
            log.info(
                "  Active sprint: %s  (%s → %s)",
                active["title"], active["start_date"], active["end_date"],
            )
            issues_raw = fetch_project_sprint_issues(project_id, active)
            log.info("    %d issues", len(issues_raw))

            # build_sprint_record expects group_encoded but for project mode
            # we use it with project-level issues (already scoped to one project)
            record = build_sprint_record(str(project_id), active, issues_raw)
            record["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
            current_sprint_path.write_text(json.dumps(record, indent=2))
            log.info("    Wrote %s", current_sprint_path)

            end_d = date.fromisoformat(active["end_date"])
            path = month_file_path(end_d, group_slug, project_slug)
            upsert_sprint_in_month_file(path, record)
            log.info("    Upserted into %s", path)
        else:
            log.info("  No active sprint")
            current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
            current_sprint_path.write_text("null")
            log.info("    Wrote empty %s", current_sprint_path)

        # --- Process recently closed sprints ---
        for sprint in recent_closed:
            log.info(
                "  Updating closed sprint: %s  (%s → %s)",
                sprint["title"], sprint["start_date"], sprint["end_date"],
            )
            issues_raw = fetch_project_sprint_issues(project_id, sprint)
            log.info("    %d issues", len(issues_raw))
            record = build_sprint_record(str(project_id), sprint, issues_raw)

            end_d = date.fromisoformat(sprint["end_date"])
            path = month_file_path(end_d, group_slug, project_slug)
            upsert_sprint_in_month_file(path, record)
            log.info("    Upserted into %s", path)

        seen_projects.add((project_id, project_name))

    # Collect milestone data for releases page (all projects)
    if seen_projects:
        log.info("Collecting milestone data for %d projects", len(seen_projects))
        collect_milestone_data(group_slug, seen_projects)


# ---------------------------------------------------------------------------
# Jira-sourced groups (active + recent closed sprints)
# ---------------------------------------------------------------------------
def process_jira_group(group):
    """Update a Jira-sourced group: active sprint + 2 most recent closed sprints.

    Delegates Jira fetch/record-building to jira_provider, then reuses this
    script's own current-sprint.json + month-file helpers so the output layout
    matches the GitLab path exactly (data/{group}/current-sprint.json + fy files).
    """
    from jira_provider import make_client, get_target_sprints, build_sprint_record

    group_slug = group["slug"]
    group_name = group["name"]
    board_id = group.get("jira_board_id")
    if not board_id:
        log.warning("Jira group %s has no jira_board_id configured; skipping", group_name)
        return

    client = make_client()
    active, recent_closed = get_target_sprints(client, board_id)

    current_sprint_path = DATA_DIR / group_slug / "current-sprint.json"
    if active:
        log.info(
            "Active sprint: %s  (%s → %s)",
            active["title"], active["start_date"], active["end_date"],
        )
        record = build_sprint_record(client, group, active)
        record["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
        current_sprint_path.write_text(json.dumps(record, indent=2))
        log.info("Wrote %s", current_sprint_path)

        end_d = date.fromisoformat(active["end_date"])
        path = month_file_path(end_d, group_slug)
        upsert_sprint_in_month_file(path, record)
        log.info("Upserted active sprint into %s", path)
    else:
        log.info("No active sprint found for %s", group_name)
        current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
        current_sprint_path.write_text("null")
        log.info("Wrote empty %s", current_sprint_path)

    for sprint in recent_closed:
        log.info(
            "Updating closed sprint: %s  (%s → %s)",
            sprint["title"], sprint["start_date"], sprint["end_date"],
        )
        record = build_sprint_record(client, group, sprint)
        end_d = date.fromisoformat(sprint["end_date"])
        path = month_file_path(end_d, group_slug)
        upsert_sprint_in_month_file(path, record)
        log.info("Upserted into %s", path)


# ---------------------------------------------------------------------------
# Milestone data collection
# ---------------------------------------------------------------------------
def slugify(text):
    """Convert milestone title to filesystem-safe slug."""
    if not text:
        return None
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s.\-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def collect_milestone_data(group_slug, projects):
    """Fetch project-level milestones and their issues (with descriptions).

    Discovers milestones per project, fetches associated issues including
    the description field, and writes:
      - Individual milestone files: milestones/{project-slug}/{milestone-slug}.json
      - Index file: milestones/index.json
    """
    if not projects:
        return

    milestones_dir = DATA_DIR / group_slug / "milestones"
    index_projects = []

    for project_id, project_name in sorted(projects, key=lambda p: p[1]):
        log.info("Fetching milestones for project %s (ID: %s)", project_name, project_id)
        url = f"{API}/projects/{project_id}/milestones"
        try:
            milestones_raw = _get(url, {"state": "all"})
        except requests.HTTPError as e:
            log.warning("Could not fetch milestones for project %s: %s", project_name, e)
            continue

        if not milestones_raw:
            log.info("  No milestones found")
            continue

        log.info("  %d milestones found", len(milestones_raw))

        project_slug = slugify(project_name)
        project_dir = milestones_dir / project_slug
        project_dir.mkdir(parents=True, exist_ok=True)

        index_milestones = []

        for ms in milestones_raw:
            ms_title = ms.get("title")
            if not ms_title:
                continue

            ms_slug = slugify(ms_title)
            if not ms_slug:
                continue

            # Fetch all issues for this project milestone
            issues_url = f"{API}/projects/{project_id}/issues"
            try:
                issues_raw = _get(issues_url, {
                    "milestone": ms_title,
                    "scope": "all",
                    "state": "all",
                })
            except requests.HTTPError as e:
                log.warning("  Could not fetch issues for milestone %s: %s", ms_title, e)
                continue

            log.info("  Milestone '%s': %d issues", ms_title, len(issues_raw))

            issues = []
            for issue in issues_raw:
                web_url = issue.get("web_url", "")
                issues.append({
                    "id": issue["id"],
                    "iid": issue["iid"],
                    "title": issue["title"],
                    "weight": issue.get("weight") or 0,
                    "state": issue["state"],
                    "labels": issue.get("labels", []),
                    "description": issue.get("description") or "",
                    "web_url": web_url,
                })

            milestone_data = {
                "milestone_title": ms_title,
                "milestone_id": ms["id"],
                "slug": ms_slug,
                "project_id": project_id,
                "project_name": project_name,
                "group_slug": group_slug,
                "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "issues": sorted(issues, key=lambda i: i["iid"]),
            }

            path = project_dir / f"{ms_slug}.json"
            path.write_text(json.dumps(milestone_data, indent=2))

            index_milestones.append({
                "title": ms_title,
                "slug": ms_slug,
                "state": ms.get("state", ""),
                "due_date": ms.get("due_date"),
            })

        if index_milestones:
            index_projects.append({
                "project_id": project_id,
                "project_name": project_name,
                "project_slug": project_slug,
                "milestones": sorted(index_milestones, key=lambda m: m.get("due_date") or "", reverse=True),
            })

    # Write index file
    if index_projects:
        milestones_dir.mkdir(parents=True, exist_ok=True)
        index_data = {
            "group_slug": group_slug,
            "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "projects": sorted(index_projects, key=lambda p: p["project_name"]),
        }
        index_path = milestones_dir / "index.json"
        index_path.write_text(json.dumps(index_data, indent=2))
        log.info("Wrote milestone index: %s", index_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not GITLAB_TOKEN:
        sys.exit("Error: GITLAB_TOKEN environment variable is required")

    groups = load_groups()
    if not groups:
        sys.exit("Error: No groups configured (check groups.json or GITLAB_GROUP env var)")

    for group in groups:
        group_id = str(group["id"])
        group_slug = group["slug"]
        group_name = group["name"]
        group_mode = group.get("mode", "group")
        log.info("=" * 60)
        log.info("Processing group: %s (ID: %s, slug: %s, mode: %s)", group_name, group_id, group_slug, group_mode)
        log.info("=" * 60)

        if group.get("source", "gitlab") == "jira":
            process_jira_group(group)
            continue

        if group_mode == "projects":
            process_project_mode(group)
            continue

        group_encoded = urlquote(group_id, safe="")
        tier = detect_tier(group_encoded)

        active, recent_closed = get_target_sprints(group_encoded, tier)

        # Track projects seen in sprint issues for milestone collection
        seen_projects = set()

        # --- Process active sprint ---
        current_sprint_path = DATA_DIR / group_slug / "current-sprint.json"

        if active:
            log.info(
                "Active sprint: %s  (%s → %s)",
                active["title"], active["start_date"], active["end_date"],
            )
            issues_raw = fetch_sprint_issues(group_encoded, active)
            log.info("  %d issues", len(issues_raw))
            record = build_sprint_record(group_encoded, active, issues_raw)

            # Collect projects for milestone data
            for issue in record.get("issues", []):
                seen_projects.add((issue["project_id"], issue["project_name"]))

            # Add last_updated timestamp for current sprint display (UTC)
            record["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            # Write current-sprint.json in group subdirectory
            current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
            current_sprint_path.write_text(json.dumps(record, indent=2))
            log.info("Wrote %s", current_sprint_path)

            # Also upsert into its month file
            end_d = date.fromisoformat(active["end_date"])
            upsert_sprint_in_month_file(month_file_path(end_d, group_slug), record)
            log.info("Upserted active sprint into %s", month_file_path(end_d, group_slug))
        else:
            log.info("No active sprint found for %s", group_name)
            current_sprint_path.parent.mkdir(parents=True, exist_ok=True)
            current_sprint_path.write_text("null")
            log.info("Wrote empty %s", current_sprint_path)

        # --- Process recently closed sprints ---
        for sprint in recent_closed:
            log.info(
                "Updating closed sprint: %s  (%s → %s)",
                sprint["title"], sprint["start_date"], sprint["end_date"],
            )
            issues_raw = fetch_sprint_issues(group_encoded, sprint)
            log.info("  %d issues", len(issues_raw))
            record = build_sprint_record(group_encoded, sprint, issues_raw)

            # Collect projects for milestone data
            for issue in record.get("issues", []):
                seen_projects.add((issue["project_id"], issue["project_name"]))

            end_d = date.fromisoformat(sprint["end_date"])
            path = month_file_path(end_d, group_slug)
            upsert_sprint_in_month_file(path, record)
            log.info("Upserted into %s", path)

        # --- Collect milestone data for projects seen in sprint issues ---
        if seen_projects:
            log.info("Collecting milestone data for %d projects", len(seen_projects))
            collect_milestone_data(group_slug, seen_projects)

    log.info("Nightly update complete for all groups.")


if __name__ == "__main__":
    main()
