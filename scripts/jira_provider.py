#!/usr/bin/env python3
"""
Jira data provider: turns Jira Software sprints into the dashboard's standard
sprint-record dict — the exact shape produced by backfill.py / scheduled_update.py
build_sprint_record(). This lets a Jira-backed group (P2DS) render on the frontend
with no changes to the JS, which is entirely data-source-agnostic.

Responsibilities (Jira -> record only):
  - Select sprints from a Scrum board (active + recent closed, or a FY-floored set).
  - Fetch each sprint's issues with changelog.
  - Reconstruct daily burndown from the Sprint-field changelog + resolution dates.
  - Map Jira issue types -> `type::*` labels the frontend understands.

File I/O stays in the caller (scheduled_update.py / backfill.py) so each script
keeps using its own current-sprint / month-file helpers. This module performs no
writes and imports neither script, avoiding circular imports.

Config comes from the group dict in groups.json:
    {
      "source": "jira",
      "jira_board_id": 42,                       # required: numeric Scrum board id
      "jira_project_key": "P2DS",                # optional: for logging/validation
      "jira_story_points_field": "customfield_10016",  # optional: weight source
      "jira_type_map": { "story": "type::new-feature" }  # optional: overrides
    }
Secrets/URL come from the environment (see jira_api.py): JIRA_URL, JIRA_TOKEN.
"""

import logging
from datetime import date, timedelta

from jira_api import JiraClient

log = logging.getLogger("jira_provider")

# Type labels the frontend recognizes (mirrors backfill.py TYPE_LABELS).
TYPE_LABELS = {"type::bug", "type::improvement", "type::new-feature", "type::new feature"}

# Default Jira issue-type name (lowercased) -> type:: label. Overridable per group
# via "jira_type_map". Types not present here get no type label (frontend buckets
# them as "Uncategorized"/"Task"), matching how untyped GitLab issues behave.
DEFAULT_TYPE_MAP = {
    "bug": "type::bug",
    "defect": "type::bug",
    "improvement": "type::improvement",
    "enhancement": "type::improvement",
    "story": "type::new-feature",
    "new feature": "type::new-feature",
    "feature": "type::new-feature",
    "epic": "type::new-feature",
}

# Fields to request from the Jira search (keep the payload small).
_BASE_FIELDS = ["summary", "status", "issuetype", "labels", "project", "components",
                "resolutiondate", "fixVersions", "created"]


def make_client():
    """Construct a JiraClient from environment configuration."""
    return JiraClient()


# ---------------------------------------------------------------------------
# Sprint selection
# ---------------------------------------------------------------------------
def _date_only(value):
    """Return the YYYY-MM-DD prefix of an ISO datetime string, or None."""
    return value[:10] if value else None


def normalize_sprint(sprint):
    """Map a raw Agile sprint into the standard sprint dict used by record builders.

    Uses completeDate as the effective end for closed sprints when present
    (actual close), else the planned endDate.
    """
    state_raw = (sprint.get("state") or "").lower()
    state = {"active": "active", "closed": "closed", "future": "future"}.get(state_raw, state_raw)
    end = sprint.get("completeDate") or sprint.get("endDate")
    return {
        "id": sprint["id"],
        "title": sprint.get("name") or f"Sprint {sprint['id']}",
        "start_date": _date_only(sprint.get("startDate")),
        "end_date": _date_only(end),
        "state": state,
        "source": "jira",
        "description": sprint.get("goal") or None,
    }


def _usable(sprint):
    """A sprint is usable only if it has both a start and end date."""
    return bool(sprint.get("start_date") and sprint.get("end_date"))


def get_target_sprints(client, board_id, recent_closed=2):
    """Return (active_sprint_or_None, [most recently closed sprints]).

    Mirrors scheduled_update.get_target_sprints: one active sprint plus the N
    most recently completed sprints (by end date).
    """
    raw = client.board_sprints(board_id, state="active,closed")
    sprints = [normalize_sprint(s) for s in raw]
    sprints = [s for s in sprints if _usable(s)]

    active = next((s for s in sprints if s["state"] == "active"), None)
    closed = [s for s in sprints if s["state"] == "closed"]
    closed.sort(key=lambda s: s["end_date"], reverse=True)
    return active, closed[:recent_closed]


def get_backfill_sprints(client, board_id, earliest_date):
    """Return all usable sprints ending on/after earliest_date, plus the active one.

    earliest_date: "YYYY-MM-DD" floor (e.g. the FY2026 start "2025-10-01").
    Sorted by start_date ascending, matching backfill.py.
    """
    raw = client.board_sprints(board_id, state="active,closed")
    sprints = [normalize_sprint(s) for s in raw]
    sprints = [
        s for s in sprints
        if _usable(s) and (s["state"] == "active" or s["end_date"] >= earliest_date)
    ]
    sprints.sort(key=lambda s: s["start_date"])
    return sprints


# ---------------------------------------------------------------------------
# Issue mapping
# ---------------------------------------------------------------------------
def _iid_from_key(key):
    """P2DS-123 -> 123. Falls back to 0 if the key has no numeric suffix."""
    if key and "-" in key:
        tail = key.rsplit("-", 1)[-1]
        if tail.isdigit():
            return int(tail)
    return 0


def _coerce_weight(value):
    """Story points may arrive as float (3.0); return int when whole, else float/0."""
    if value is None:
        return 0
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else f


def _type_label(issuetype_name, type_map):
    """Map a Jira issue-type name to a type:: label, or None if unmapped."""
    if not issuetype_name:
        return None
    return type_map.get(issuetype_name.strip().lower())


def _sprint_membership_dates(changelog, sprint_id):
    """Reconstruct (date_added, date_removed) for sprint_id from an issue changelog.

    Scans Sprint-field changes chronologically. A change whose "to" contains the
    sprint id (but "from" does not) is an add; the reverse is a remove. Sprint
    field values are comma-separated id lists (an issue can span sprints).
    Returns (date_added|None, date_removed|None) as YYYY-MM-DD strings.
    """
    sid = str(sprint_id)
    date_added = None
    date_removed = None

    histories = sorted(
        changelog.get("histories", []),
        key=lambda h: h.get("created", ""),
    )
    for hist in histories:
        when = _date_only(hist.get("created"))
        for item in hist.get("items", []):
            if item.get("field") != "Sprint":
                continue
            from_ids = {p.strip() for p in (item.get("from") or "").split(",") if p.strip()}
            to_ids = {p.strip() for p in (item.get("to") or "").split(",") if p.strip()}
            if sid in to_ids and sid not in from_ids:
                date_added = when
            elif sid in from_ids and sid not in to_ids:
                date_removed = when
    return date_added, date_removed


def _map_issue(client, issue, sprint, story_points_field, type_map):
    """Map one raw Jira issue into the dashboard issue dict + resolved dates."""
    fields = issue.get("fields", {})
    key = issue.get("key", "")

    weight = _coerce_weight(fields.get(story_points_field) if story_points_field else None)

    # Labels: Jira labels plus a synthesized type:: label from the issue type.
    labels = list(fields.get("labels") or [])
    type_label = _type_label((fields.get("issuetype") or {}).get("name"), type_map)
    if type_label:
        labels.append(type_label)

    # State: statusCategory "done" -> closed, otherwise opened.
    status_cat = ((fields.get("status") or {}).get("statusCategory") or {}).get("key")
    state = "closed" if status_cat == "done" else "opened"

    # Sprint membership dates from changelog (fallback: present at sprint start).
    date_added, date_removed = _sprint_membership_dates(issue.get("changelog", {}), sprint["id"])
    if date_added is None:
        date_added = sprint["start_date"]

    date_closed = _date_only(fields.get("resolutiondate")) if state == "closed" else None

    project = fields.get("project") or {}
    project_id = project.get("id")
    try:
        project_id = int(project_id)
    except (TypeError, ValueError):
        pass

    # P2DS uses the Jira project like a group and its components like the
    # per-project split (mirrors GitLab standard-mode groups). Surface the
    # first component as project_name so the dashboard's project column,
    # filter chips, sort, and velocity all group by component.
    components = fields.get("components") or []
    component_name = components[0].get("name") if components else "No Component"

    fix_versions = fields.get("fixVersions") or []
    milestone = fix_versions[0].get("name") if fix_versions else None

    return {
        "id": int(issue["id"]) if str(issue.get("id", "")).isdigit() else issue.get("id"),
        "iid": _iid_from_key(key),
        "title": fields.get("summary") or "",
        "project_id": project_id,
        "project_name": component_name,
        "weight": weight,
        "state": state,
        "labels": labels,
        "milestone": milestone,
        "date_added_to_sprint": date_added,
        "date_closed": date_closed,
        "date_removed_from_sprint": date_removed,
        "web_url": f"{client.url}/browse/{key}" if key else "",
    }


# ---------------------------------------------------------------------------
# Record building (mirrors backfill.build_sprint_record output schema)
# ---------------------------------------------------------------------------
def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_sprint_record(client, group, sprint):
    """Fetch a sprint's issues and assemble the standard sprint-record dict.

    Output schema is identical to backfill/scheduled_update build_sprint_record:
    id, title, start_date, end_date, state, source, goal, initial_totals,
    burndown, type_breakdown, completed, issues.
    """
    story_points_field = group.get("jira_story_points_field")
    type_map = {**DEFAULT_TYPE_MAP, **{k.lower(): v for k, v in group.get("jira_type_map", {}).items()}}

    s_start = date.fromisoformat(sprint["start_date"])
    s_end = date.fromisoformat(sprint["end_date"])

    fields = list(_BASE_FIELDS)
    if story_points_field and story_points_field not in fields:
        fields.append(story_points_field)

    raw_issues = client.search(f"sprint = {sprint['id']}", fields=fields, expand="changelog")
    issues = [_map_issue(client, i, sprint, story_points_field, type_map) for i in raw_issues]

    # --- Type breakdown + daily add/remove/close tracking (mirrors backfill) ---
    type_counts = {"bug": 0, "improvement": 0, "new_feature": 0, "other": 0}
    initial_ids = set()
    daily_adds, daily_removes, daily_closes = {}, {}, {}

    for issue in issues:
        label_set = {l.lower() for l in issue["labels"]}
        matched = label_set & TYPE_LABELS
        if "type::bug" in matched:
            type_counts["bug"] += 1
        elif "type::improvement" in matched:
            type_counts["improvement"] += 1
        elif "type::new-feature" in matched or "type::new feature" in matched:
            type_counts["new_feature"] += 1
        else:
            type_counts["other"] += 1

        weight = issue["weight"] or 0
        added_d = date.fromisoformat(issue["date_added_to_sprint"])
        if added_d <= s_start:
            initial_ids.add(issue["id"])
        else:
            daily_adds.setdefault(added_d, []).append(weight)

        if issue["date_removed_from_sprint"]:
            removed_d = date.fromisoformat(issue["date_removed_from_sprint"])
            if removed_d <= s_end:
                daily_removes.setdefault(removed_d, []).append(weight)

        if issue["date_closed"]:
            closed_d = date.fromisoformat(issue["date_closed"])
            if s_start <= closed_d <= s_end:
                daily_closes.setdefault(closed_d, []).append(weight)

    initial_count = len(initial_ids)
    initial_weight = sum(i["weight"] or 0 for i in issues if i["id"] in initial_ids)

    # --- Burndown (only up to today for an in-progress sprint) ---
    remaining_count = initial_count
    remaining_weight = initial_weight
    burndown = []
    burn_end = min(s_end, date.today())
    for d in _daterange(s_start, burn_end):
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

    completed_issues = [i for i in issues if i["state"] == "closed"]
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
        "initial_totals": {"count": initial_count, "weight": initial_weight},
        "burndown": burndown,
        "type_breakdown": type_counts,
        "completed": {"count": completed_count, "weight": completed_weight},
        "issues": issues,
    }
