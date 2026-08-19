#!/usr/bin/env python3
"""
One-time script: Split group-level sprint data into project-scoped data files.

For each project configured in a "projects" mode group, reads the group's FY month
files, filters issues by project_id, recalculates metrics (initial_totals, completed,
type_breakdown, burndown), and writes project-scoped sprint data files.

Usage:
    python3 scripts/project_split.py

The script reads group configuration from public/data/groups.json and processes
only groups with mode == "projects". Original group-level files are not modified.
Can be run repeatedly (overwrites existing split files).
"""

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"
GROUPS_FILE = DATA_DIR / "groups.json"

TYPE_LABELS = {"type::bug", "type::improvement", "type::new-feature", "type::new feature"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
log = logging.getLogger("project_split")


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def recalculate_sprint_for_project(sprint, project_id):
    """Filter a sprint's issues to one project and recalculate all metrics."""
    project_issues = [i for i in sprint["issues"] if i["project_id"] == project_id]
    if not project_issues:
        return None

    s_start = date.fromisoformat(sprint["start_date"])
    s_end = date.fromisoformat(sprint["end_date"])

    # --- Type breakdown ---
    type_counts = {"bug": 0, "improvement": 0, "new_feature": 0, "other": 0}
    for issue in project_issues:
        label_set = {l.lower() for l in issue.get("labels", [])}
        matched = label_set & TYPE_LABELS
        if "type::bug" in matched:
            type_counts["bug"] += 1
        elif "type::improvement" in matched:
            type_counts["improvement"] += 1
        elif "type::new-feature" in matched or "type::new feature" in matched:
            type_counts["new_feature"] += 1
        else:
            type_counts["other"] += 1

    # --- Burndown recalculation ---
    initial_ids = set()
    daily_adds = {}
    daily_removes = {}
    daily_closes = {}

    for issue in project_issues:
        weight = issue.get("weight") or 0
        date_added = issue.get("date_added_to_sprint") or sprint["start_date"]
        added_d = date.fromisoformat(date_added)

        if added_d <= s_start:
            initial_ids.add(issue["id"])
        else:
            daily_adds.setdefault(added_d, []).append(weight)

        date_removed = issue.get("date_removed_from_sprint")
        if date_removed:
            removed_d = date.fromisoformat(date_removed)
            if removed_d <= s_end:
                daily_removes.setdefault(removed_d, []).append(weight)

        date_closed = issue.get("date_closed")
        if date_closed:
            closed_d = date.fromisoformat(date_closed)
            if s_start <= closed_d <= s_end:
                daily_closes.setdefault(closed_d, []).append(weight)

    initial_count = len(initial_ids)
    initial_weight = sum(
        (i.get("weight") or 0) for i in project_issues if i["id"] in initial_ids
    )

    remaining_count = initial_count
    remaining_weight = initial_weight
    burndown = []

    for d in daterange(s_start, s_end):
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

    # --- Completed totals ---
    completed_issues = [i for i in project_issues if i["state"] == "closed"]
    completed_count = len(completed_issues)
    completed_weight = sum(i.get("weight") or 0 for i in completed_issues)

    return {
        "id": sprint["id"],
        "title": sprint["title"],
        "start_date": sprint["start_date"],
        "end_date": sprint["end_date"],
        "state": sprint["state"],
        "source": sprint.get("source", "iteration"),
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
        "issues": project_issues,
    }


def fiscal_year(d: date) -> int:
    return d.year + 1 if d.month >= 10 else d.year


def main():
    if not GROUPS_FILE.exists():
        sys.exit("Error: groups.json not found at " + str(GROUPS_FILE))

    with open(GROUPS_FILE) as f:
        config = json.load(f)

    groups = config.get("groups", [])
    project_mode_groups = [g for g in groups if g.get("mode") == "projects"]

    if not project_mode_groups:
        log.info("No groups with mode='projects' found. Nothing to do.")
        return

    for group in project_mode_groups:
        group_slug = group["slug"]
        group_name = group["name"]
        projects = group.get("projects", [])
        project_ids = {p["id"]: p for p in projects}

        log.info("=" * 60)
        log.info("Splitting data for group: %s (slug: %s)", group_name, group_slug)
        log.info("  Configured projects: %s", ", ".join(p["name"] for p in projects))
        log.info("=" * 60)

        group_dir = DATA_DIR / group_slug

        # Find all FY directories
        fy_dirs = sorted(group_dir.glob("fy*"))
        if not fy_dirs:
            log.warning("  No FY directories found in %s", group_dir)
            continue

        # Track stats for summary
        total_sprints = 0
        total_project_sprints = 0

        for fy_dir in fy_dirs:
            if not fy_dir.is_dir():
                continue

            fy_name = fy_dir.name
            month_files = sorted(fy_dir.glob("*.json"))

            for month_file in month_files:
                month_data = json.loads(month_file.read_text())
                sprints = month_data.get("sprints", [])
                month_file_name = month_file.name

                for sprint in sprints:
                    total_sprints += 1
                    sprint_title = sprint.get("title", "untitled")

                    for project in projects:
                        pid = project["id"]
                        pslug = project["slug"]

                        record = recalculate_sprint_for_project(sprint, pid)
                        if record is None:
                            continue

                        total_project_sprints += 1
                        issue_count = len(record["issues"])
                        log.info(
                            "  %s / %s → %s: %d issues",
                            fy_name, sprint_title, project["name"], issue_count,
                        )

                        # Write to project-scoped FY directory
                        project_fy_dir = group_dir / pslug / fy_name
                        project_month_path = project_fy_dir / month_file_name

                        # Read existing file to merge sprints from same month
                        if project_month_path.exists():
                            existing = json.loads(project_month_path.read_text())
                        else:
                            end_d = date.fromisoformat(sprint["end_date"])
                            existing = {
                                "fiscal_year": fiscal_year(end_d),
                                "month": end_d.month,
                                "year": end_d.year,
                                "sprints": [],
                            }

                        # Upsert: replace by sprint ID or append
                        existing_sprints = existing["sprints"]
                        replaced = False
                        for i, s in enumerate(existing_sprints):
                            if s["id"] == record["id"]:
                                existing_sprints[i] = record
                                replaced = True
                                break
                        if not replaced:
                            existing_sprints.append(record)

                        existing_sprints.sort(key=lambda s: s["start_date"])

                        project_fy_dir.mkdir(parents=True, exist_ok=True)
                        project_month_path.write_text(json.dumps(existing, indent=2))

        log.info(
            "  Summary: %d group sprints → %d project sprint records",
            total_sprints, total_project_sprints,
        )

    log.info("Project split complete.")


if __name__ == "__main__":
    main()
