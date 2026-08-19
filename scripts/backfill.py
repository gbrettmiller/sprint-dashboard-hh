#!/usr/bin/env python3
"""
Backfill script: Fetches all historical sprints from GitLab and organizes
them into JSON files by fiscal year (Oct-Sep) and month based on sprint end date.

Detects FREE (milestones) vs PREMIUM (iterations) automatically.

Usage:
    export GITLAB_TOKEN=glpat-...
    export GITLAB_URL=https://gitlab.com        # optional, defaults to https://gitlab.com
    export GITLAB_GROUP=engineering-team2841005  # fallback if no groups.json
    python3 scripts/backfill.py

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
log = logging.getLogger("backfill")

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
VERIFY_SSL = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")

session = requests.Session()
session.headers.update(HEADERS)
session.verify = VERIFY_SSL

def _get(url, params=None):
    """GET with pagination, rate-limit handling, and retries."""
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
            return data  # single-object endpoint

        # Pagination via Link header
        page_url = None
        params = {}  # params are baked into the next URL
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
    """Return 'iterations' if Premium+ group iterations are available, else 'milestones'."""
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
def fetch_iterations(group_encoded):
    url = f"{API}/groups/{group_encoded}/iterations"
    raw = _get(url, {"state": "all", "include_ancestors": "false"})
    sprints = []
    for it in raw:
        if not it.get("title"):
            log.debug("Skipping iteration %s (no title – unused cadence placeholder)", it["id"])
            continue
        sprints.append({
            "id": it["id"],
            "iid": it.get("iid"),
            "title": it["title"],
            "start_date": it["start_date"],
            "end_date": it["due_date"],
            "state": it["state"],
            "source": "iteration",
        })
    return sprints


def fetch_milestones(group_encoded):
    url = f"{API}/groups/{group_encoded}/milestones"
    raw = _get(url, {"state": "all"})
    sprints = []
    for ms in raw:
        if not ms.get("start_date") or not ms.get("due_date"):
            continue  # skip milestones without date range
        sprints.append({
            "id": ms["id"],
            "iid": ms.get("iid"),
            "title": ms["title"],
            "start_date": ms["start_date"],
            "end_date": ms["due_date"],
            "state": ms["state"],
            "source": "milestone",
        })
    return sprints


# ---------------------------------------------------------------------------
# Fetch issues for a sprint
# ---------------------------------------------------------------------------
def fetch_sprint_issues(group_encoded, sprint):
    """Return list of issues for the given sprint."""
    if sprint["source"] == "iteration":
        params = {"iteration_id": sprint["id"]}
    else:
        params = {"milestone": sprint["title"]}

    url = f"{API}/groups/{group_encoded}/issues"
    params["scope"] = "all"
    params["state"] = "all"
    issues = _get(url, params)
    return issues


# ---------------------------------------------------------------------------
# Resource events – when was issue added/removed from sprint
# ---------------------------------------------------------------------------
def get_milestone_events(project_id, issue_iid):
    """Get resource_milestone_events for an issue."""
    url = f"{API}/projects/{project_id}/issues/{issue_iid}/resource_milestone_events"
    try:
        return _get(url)
    except Exception:
        return []


def get_iteration_events(project_id, issue_iid):
    """Get resource_iteration_events for an issue (Premium)."""
    url = f"{API}/projects/{project_id}/issues/{issue_iid}/resource_iteration_events"
    try:
        return _get(url)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Build sprint data
# ---------------------------------------------------------------------------
def daterange(start: date, end: date):
    """Yield dates from start to end inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_sprint_record(group_encoded, sprint, issues_raw):
    """Build the full data record for one sprint."""
    s_start = date.fromisoformat(sprint["start_date"])
    s_end = date.fromisoformat(sprint["end_date"])

    # --- Process issues ---
    issues_table = []
    type_counts = {"bug": 0, "improvement": 0, "new_feature": 0, "other": 0}
    total_weight = 0
    initial_ids = set()  # issues present on day 1

    # Track daily adds/removes/closes for burndown
    daily_adds = {}      # date -> list of (weight,)
    daily_removes = {}   # date -> list of (weight,)
    daily_closes = {}    # date -> list of (weight,)

    for issue in issues_raw:
        iid = issue["iid"]
        project_id = issue["project_id"]
        weight = issue.get("weight") or 0
        total_weight += weight

        labels = [l for l in issue.get("labels", [])]
        label_set_normalized = {l.lower() for l in labels}

        # Type classification
        matched = label_set_normalized & TYPE_LABELS
        if "type::bug" in matched:
            type_counts["bug"] += 1
        elif "type::improvement" in matched:
            type_counts["improvement"] += 1
        elif "type::new-feature" in matched or "type::new feature" in matched:
            type_counts["new_feature"] += 1
        else:
            type_counts["other"] += 1

        # Determine date_added, date_removed via resource events
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

        # Fallback: if no add event found, assume issue was there at start
        if date_added is None:
            date_added = sprint["start_date"]

        added_d = date.fromisoformat(date_added)
        if added_d <= s_start:
            initial_ids.add(issue["id"])
        else:
            daily_adds.setdefault(added_d, []).append(weight)

        # Removed before sprint end?
        if date_removed:
            removed_d = date.fromisoformat(date_removed)
            if removed_d <= s_end:
                daily_removes.setdefault(removed_d, []).append(weight)

        # Closed date
        date_closed = None
        if issue.get("closed_at"):
            date_closed = issue["closed_at"][:10]
            closed_d = date.fromisoformat(date_closed)
            if s_start <= closed_d <= s_end:
                daily_closes.setdefault(closed_d, []).append(weight)

        # Project name from web_url: .../project-name/-/issues/...
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

    # --- Initial totals (day 1) ---
    initial_count = len(initial_ids)
    initial_weight = sum(
        i.get("weight") or 0 for i in issues_raw if i["id"] in initial_ids
    )

    # --- Build burndown ---
    # Running count/weight of *remaining open* issues in the sprint
    remaining_count = initial_count
    remaining_weight = initial_weight
    burndown = []

    for d in daterange(s_start, s_end):
        # Add issues that entered the sprint on this day
        for w in daily_adds.get(d, []):
            remaining_count += 1
            remaining_weight += w
        # Remove issues pulled out of sprint
        for w in daily_removes.get(d, []):
            remaining_count -= 1
            remaining_weight -= w
        # Close events reduce remaining
        for w in daily_closes.get(d, []):
            remaining_count -= 1
            remaining_weight -= w

        burndown.append({
            "date": d.isoformat(),
            "remaining_count": max(remaining_count, 0),
            "remaining_weight": max(remaining_weight, 0),
        })

    # --- Completed totals (for velocity) ---
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
# Fiscal year / month bucketing
# ---------------------------------------------------------------------------
def fiscal_year(d: date) -> int:
    """FY starts in October. FY2025 = Oct 2024 – Sep 2025."""
    return d.year + 1 if d.month >= 10 else d.year


def output_path(end_date: date, group_slug: str, project_slug: str = None) -> Path:
    fy = fiscal_year(end_date)
    month_str = f"{end_date.month:02d}-{MONTH_NAMES[end_date.month]}-{end_date.year}"
    if project_slug:
        return DATA_DIR / group_slug / project_slug / f"fy{fy}" / f"{month_str}.json"
    return DATA_DIR / group_slug / f"fy{fy}" / f"{month_str}.json"


# ---------------------------------------------------------------------------
# Project-mode backfill (milestones as sprints per project)
# ---------------------------------------------------------------------------
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


def fetch_project_sprint_issues(project_id, sprint):
    """Fetch issues for a project-level milestone sprint."""
    url = f"{API}/projects/{project_id}/issues"
    return _get(url, {
        "milestone": sprint["title"],
        "scope": "all",
        "state": "all",
    })


def process_project_mode_backfill(group):
    """Backfill a group where each project has its own sprint milestones.

    For project-mode groups, this:
    1. Runs the project_split logic to split historical iteration data
    2. Fetches all milestone-based sprints (start_date >= transition_date) per project
    """
    group_slug = group["slug"]
    group_name = group["name"]
    transition_date = group.get("transition_date", "1970-01-01")
    projects = group.get("projects", [])
    seen_projects = set()

    # Step 1: Split historical group-level data into per-project files
    log.info("Running historical data split for %s...", group_name)
    try:
        from project_split import main as split_main
        split_main()
    except Exception as e:
        log.warning("Could not run project_split: %s (continuing with milestone backfill)", e)

    # Step 2: Backfill milestone-based sprints per project
    for project in projects:
        project_id = project["id"]
        project_slug = project["slug"]
        project_name = project["name"]

        log.info("-" * 40)
        log.info("Project: %s (ID: %s)", project_name, project_id)

        # Fetch all project milestones
        url = f"{API}/projects/{project_id}/milestones"
        try:
            all_milestones_raw = _get(url, {"state": "all"})
        except Exception as e:
            log.warning("Could not fetch milestones for %s: %s", project_name, e)
            continue

        # Filter to sprint milestones
        sprint_milestones = [
            normalize_milestone(m) for m in all_milestones_raw
            if m.get("start_date") and m.get("due_date")
            and m["start_date"] >= transition_date
        ]

        sprint_milestones.sort(key=lambda s: s["start_date"])
        log.info("  %d sprint milestones (after transition date)", len(sprint_milestones))

        # Bucket by month file
        buckets: dict[str, list] = {}

        for i, sprint in enumerate(sprint_milestones):
            log.info(
                "  [%d/%d] %s  (%s → %s)",
                i + 1, len(sprint_milestones), sprint["title"],
                sprint["start_date"], sprint["end_date"],
            )
            issues_raw = fetch_project_sprint_issues(project_id, sprint)
            log.info("    %d issues", len(issues_raw))

            record = build_sprint_record(str(project_id), sprint, issues_raw)
            end_d = date.fromisoformat(sprint["end_date"])
            path = output_path(end_d, group_slug, project_slug)
            key = str(path)
            buckets.setdefault(key, []).append(record)

        # Write/merge files
        for path_str, records in buckets.items():
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)

            # Read existing file (may have historical split data)
            if p.exists():
                month_data = json.loads(p.read_text())
            else:
                end_d = date.fromisoformat(records[0]["end_date"])
                month_data = {
                    "fiscal_year": fiscal_year(end_d),
                    "month": end_d.month,
                    "year": end_d.year,
                    "sprints": [],
                }

            # Upsert each record
            for record in records:
                existing = month_data["sprints"]
                replaced = False
                for j, s in enumerate(existing):
                    if s["id"] == record["id"]:
                        existing[j] = record
                        replaced = True
                        break
                if not replaced:
                    existing.append(record)

            month_data["sprints"].sort(key=lambda s: s["start_date"])
            p.write_text(json.dumps(month_data, indent=2))
            log.info("  Wrote %s  (%d sprints)", p, len(month_data["sprints"]))

        seen_projects.add((project_id, project_name))

    # Collect milestone data for releases page
    if seen_projects:
        log.info("Collecting milestone data for %d projects", len(seen_projects))
        collect_milestone_data(group_slug, seen_projects)


# ---------------------------------------------------------------------------
# Jira-sourced groups (FY-floored backfill)
# ---------------------------------------------------------------------------
# Backfill floor for Jira groups — matches the dashboard's FY2026 data cutoff
# (EARLIEST_FY / EARLIEST_DATE in public/js/services/api.js).
JIRA_BACKFILL_EARLIEST = "2025-10-01"


def process_jira_backfill(group, earliest_date=JIRA_BACKFILL_EARLIEST):
    """Backfill a Jira-sourced group from earliest_date to present.

    Fetches all sprints ending on/after earliest_date (plus the active one),
    builds standard sprint records via jira_provider, and writes them into the
    same fy{YYYY}/{MM}-{mon}-{YYYY}.json month files as the GitLab path. Upserts
    by sprint id so re-runs are safe.
    """
    from jira_provider import make_client, get_backfill_sprints, build_sprint_record

    group_slug = group["slug"]
    group_name = group["name"]
    board_id = group.get("jira_board_id")
    if not board_id:
        log.warning("Jira group %s has no jira_board_id configured; skipping", group_name)
        return

    client = make_client()
    sprints = get_backfill_sprints(client, board_id, earliest_date)
    log.info("Found %d Jira sprints (end >= %s) for %s", len(sprints), earliest_date, group_name)

    buckets: dict[str, list] = {}
    for i, sprint in enumerate(sprints):
        log.info(
            "[%d/%d] Processing %s  (%s → %s)",
            i + 1, len(sprints), sprint["title"],
            sprint["start_date"], sprint["end_date"],
        )
        record = build_sprint_record(client, group, sprint)
        end_d = date.fromisoformat(sprint["end_date"])
        buckets.setdefault(str(output_path(end_d, group_slug)), []).append(record)

    for path_str, records in buckets.items():
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)

        if p.exists():
            month_data = json.loads(p.read_text())
        else:
            end_d = date.fromisoformat(records[0]["end_date"])
            month_data = {
                "fiscal_year": fiscal_year(end_d),
                "month": end_d.month,
                "year": end_d.year,
                "sprints": [],
            }

        for record in records:
            existing = month_data["sprints"]
            replaced = False
            for j, s in enumerate(existing):
                if s["id"] == record["id"]:
                    existing[j] = record
                    replaced = True
                    break
            if not replaced:
                existing.append(record)

        month_data["sprints"].sort(key=lambda s: s["start_date"])
        p.write_text(json.dumps(month_data, indent=2))
        log.info("Wrote %s  (%d sprints)", p, len(month_data["sprints"]))


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
        log.info("Backfilling group: %s (ID: %s, slug: %s, mode: %s)", group_name, group_id, group_slug, group_mode)
        log.info("=" * 60)

        if group.get("source", "gitlab") == "jira":
            process_jira_backfill(group)
            continue

        if group_mode == "projects":
            process_project_mode_backfill(group)
            continue

        group_encoded = urlquote(group_id, safe="")
        tier = detect_tier(group_encoded)

        log.info("Fetching sprints for group %s …", group_name)
        if tier == "iterations":
            sprints = fetch_iterations(group_encoded)
        else:
            sprints = fetch_milestones(group_encoded)

        sprints.sort(key=lambda s: s["start_date"])
        log.info("Found %d sprints for %s", len(sprints), group_name)

        # Bucket: path -> list of sprint records
        buckets: dict[str, list] = {}
        seen_projects = set()

        for i, sprint in enumerate(sprints):
            log.info(
                "[%d/%d] Processing %s  (%s → %s)",
                i + 1, len(sprints), sprint["title"],
                sprint["start_date"], sprint["end_date"],
            )
            issues_raw = fetch_sprint_issues(group_encoded, sprint)
            log.info("  %d issues", len(issues_raw))

            record = build_sprint_record(group_encoded, sprint, issues_raw)

            # Collect projects for milestone data
            for issue in record.get("issues", []):
                seen_projects.add((issue["project_id"], issue["project_name"]))

            end_d = date.fromisoformat(sprint["end_date"])
            path = output_path(end_d, group_slug)
            key = str(path)
            buckets.setdefault(key, []).append(record)

        # Write files
        for path_str, records in buckets.items():
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)

            end_d = date.fromisoformat(records[0]["end_date"])
            month_data = {
                "fiscal_year": fiscal_year(end_d),
                "month": end_d.month,
                "year": end_d.year,
                "sprints": sorted(records, key=lambda r: r["start_date"]),
            }
            p.write_text(json.dumps(month_data, indent=2))
            log.info("Wrote %s  (%d sprints)", p, len(records))

        # --- Collect milestone data for projects seen in sprint issues ---
        if seen_projects:
            log.info("Collecting milestone data for %d projects", len(seen_projects))
            collect_milestone_data(group_slug, seen_projects)

    log.info("Backfill complete for all groups.")


if __name__ == "__main__":
    main()
