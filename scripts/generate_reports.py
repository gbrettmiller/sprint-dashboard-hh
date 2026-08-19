#!/usr/bin/env python3
"""
generate_reports.py
Generate AI-assisted report CONTENT (test plans + sprint/monthly reports) as JSON
for completed sprints and past months.

The dashboard renders this JSON into MS Word documents client-side; this script
produces NO Word files. Release notes are built client-side from the existing
milestone JSON and are intentionally NOT generated here.

What it writes (JSON only, committed via scripts/api_commit.py in CI):
    Project-mode groups (Cloud Services):
        public/data/{group}/{project}/reports/sprints/{milestone-slug}.json
        public/data/{group}/{project}/reports/months/{YYYY-MM}.json
    Standard groups reading local sprint JSON — group-scoped, sprint report only:
        Jira-sourced (Data Services) and iteration groups opted in via "reports": true (Service Management).
        public/data/{group}/reports/sprints/{sprint-slug}.json
        public/data/{group}/reports/months/{YYYY-MM}.json

Scope:
    - Groups with mode == "projects" in public/data/groups.json. Each project's
      sprint milestones are those with start_date >= the group's transition_date;
      per-issue descriptions drive test plans + release notes.
    - Standard groups reading local sprint JSON (data/{group}/fy*/): those with
      source == "jira" (Data Services) and iteration groups opted in via "reports": true
      (Service Management). Sprint + monthly reports only. No test plan is generated here;
      Release Notes are built client-side from the sprint issues.
    A sprint is "completed" when its end/due date is in the past. Monthly reports
    are generated only for calendar months strictly before the current month.

Idempotent:
    Skips any sprint/month whose output JSON already exists (completed sprints and
    past months are immutable), keeping Anthropic usage near-zero on routine runs.
    Pass --force (or REPORTS_FORCE=1) to regenerate.

Environment (CI/CD variables — no hardcoded values; the script errors if unset):
    GITLAB_URL          GitLab instance URL
    GITLAB_TOKEN        API token with read_api scope
    ANTHROPIC_API_KEY   Anthropic-compatible API key (test steps + goals/summary).
                        On the internal network this is an Ask Sage key.
Optional:
    ANTHROPIC_BASE_URL  Anthropic-compatible endpoint. The CI runner has no public
                        internet egress, so set this to the Ask Sage gateway, e.g.
                        https://ai-gateway.example.com/server/anthropic. When unset the
                        SDK defaults to api.anthropic.com (unreachable from CI).
    ANTHROPIC_MODEL     Model id to use (default: claude-haiku-4-5-20251001). Override
                        if the gateway exposes Claude under a different id.
    GITLAB_SSL_VERIFY   "false" to disable SSL verification (default: true)
    REPORTS_FORCE       truthy → regenerate even if output exists

Usage:
    python3 scripts/generate_reports.py
    python3 scripts/generate_reports.py --group cass --force
    python3 scripts/generate_reports.py --dry-run   # plan only, no AI calls / no writes
"""

import argparse
import json
import logging
import os
import re
import sys
from calendar import monthrange
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from gitlab_api import GitLabClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "public" / "data"
GROUPS_FILE = DATA_DIR / "groups.json"

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# Earliest month a report may cover — matches the dashboard's FY2026 data cutoff
# (EARLIEST_DATE in public/js/services/api.js). A sprint window can start before
# this (e.g. a late-September sprint ending in October), but the dashboard never
# lists a pre-cutoff month, so a monthly rollup for it would be an orphan file.
EARLIEST_REPORT_MONTH = (2025, 10)

# Issues carrying these labels are excluded (mirrors the teammate prototype).
RELEASE_NOTES_EXCLUDE_LABEL = "release-notes::no"
TEST_PLAN_EXCLUDE_LABEL = "test-plan::no"

# Issue-type classification for metric breakdowns (matches gambo.py priority).
_TYPE_LABEL_PRIORITY = ["improvement", "bug", "feature", "enhancement"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger("reports")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(text):
    """Convert a milestone title to a filesystem-safe slug.

    MUST stay identical to scheduled_update.slugify so a sprint's report file
    lines up with its milestone JSON (milestones/{project}/{slug}.json).
    """
    if not text:
        return None
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s.\-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def load_groups():
    """Load group definitions from groups.json."""
    if not GROUPS_FILE.exists():
        sys.exit(f"Error: {GROUPS_FILE} not found")
    with open(GROUPS_FILE) as f:
        return json.load(f).get("groups", [])


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def issue_type(issue):
    """Classify an issue for the metric breakdown.

    Prefers this project's `type::*` labels (e.g. `type::new-feature` -> "New Feature"),
    matching the dashboard's own type breakdown, then GitLab's native Task type, then
    bare priority labels; otherwise "Other".
    """
    labels = [l.lower() for l in issue.get("labels", [])]
    for l in labels:
        if l.startswith("type::"):
            return l.split("::", 1)[1].replace("-", " ").strip().title()
    if (issue.get("issue_type") or "").lower() == "task":
        return "Task"
    for t in _TYPE_LABEL_PRIORITY:
        if t in labels:
            return t.capitalize()
    return "Other"


def format_breakdown(issues):
    """Return e.g. '4 Tasks, 9 Improvements, 1 Bug' (empty string if none)."""
    counts = Counter(issue_type(i) for i in issues)
    parts = []
    for t, n in counts.most_common():
        parts.append(f"{n} {t}{'s' if n != 1 else ''}")
    return ", ".join(parts)


def total_weight(issues):
    return sum((i.get("weight") or 0) for i in issues)


def build_metrics(issues):
    """Deterministic sprint metrics (no AI). 'initial' = all milestone issues."""
    completed = [i for i in issues if i.get("state") == "closed"]
    return {
        "initial_count": len(issues),
        "initial_weight": total_weight(issues),
        "completed_count": len(completed),
        "completed_weight": total_weight(completed),
        "initial_breakdown": format_breakdown(issues),
        "completed_breakdown": format_breakdown(completed),
    }


def is_excluded_from_test_plan(issue):
    labels = set(issue.get("labels", []))
    return RELEASE_NOTES_EXCLUDE_LABEL in labels or TEST_PLAN_EXCLUDE_LABEL in labels


# ---------------------------------------------------------------------------
# AI client factory (Anthropic by default, optional OpenAI-compatible path)
# ---------------------------------------------------------------------------
def make_ai_client(verify_ssl):
    """Return an AI client.

    If OPENAI_API_KEY is set, construct an OpenAI-compatible client (for
    example via AskSage's OpenAI gateway). Otherwise, fall back to the
    Anthropic client described in CLAUDE.md.
    """

    # httpx does not read REQUESTS_CA_BUNDLE; pass the CI cert bundle when
    # present so SSL-inspected networks still verify, matching the GitLab
    # client behavior.
    import httpx

    ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    verify = ca if (verify_ssl and ca) else verify_ssl

    # OpenAI/AskSage credentials use a separate set of environment
    # variables from the Anthropic path so each provider can be
    # configured independently.
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        from openai import OpenAI

        base_url = os.environ.get("OPENAI_BASE_URL")
        return OpenAI(
            api_key=openai_key,
            base_url=base_url or None,
            http_client=httpx.Client(verify=verify),
        )

    # Default: Anthropic client as originally implemented (for environments
    # that still route through a true Anthropic-compatible endpoint).
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable is required")

    kwargs = {"api_key": api_key, "http_client": httpx.Client(verify=verify)}
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return anthropic.Anthropic(**kwargs)


def get_test_steps(ai, issue):
    """Ask Claude/OpenAI for manual test steps; returns None when not QA-testable."""
    title = issue["title"]
    labels = ", ".join(issue.get("labels", []))
    description = (issue.get("description") or "").strip()

    # OpenAI-compatible clients expose chat.completions.create; Anthropic's
    # SDK uses messages.create. Dispatch based on available attributes so we
    # keep both paths working.
    if hasattr(ai, "chat") and hasattr(ai.chat, "completions"):
        resp = ai.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "You are generating a QA test plan for a software release.\n\n"
                    f"Issue: {title}\n"
                    f"Labels: {labels}\n"
                    f"Description:\n{description}\n\n"
                    "If this issue cannot be manually tested by a QA tester (e.g. infrastructure "
                    "upgrades, CI/CD pipeline changes, DevOps tasks, or purely backend data fixes "
                    "with no visible UI change), respond with exactly: SKIP\n\n"
                    "Otherwise, provide 2-5 concise test steps a QA tester should follow to verify "
                    "this issue. Extract steps from the description if they exist, otherwise generate "
                    "appropriate ones. Format as a markdown list using '- ' bullets. No preamble."
                ),
            }],
        )
        text = (resp.choices[0].message.content or "").strip()
    else:
        resp = ai.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "You are generating a QA test plan for a software release.\n\n"
                    f"Issue: {title}\n"
                    f"Labels: {labels}\n"
                    f"Description:\n{description}\n\n"
                    "If this issue cannot be manually tested by a QA tester (e.g. infrastructure "
                    "upgrades, CI/CD pipeline changes, DevOps tasks, or purely backend data fixes "
                    "with no visible UI change), respond with exactly: SKIP\n\n"
                    "Otherwise, provide 2-5 concise test steps a QA tester should follow to verify "
                    "this issue. Extract steps from the description if they exist, otherwise generate "
                    "appropriate ones. Format as a markdown list using '- ' bullets. No preamble."
                ),
            }],
        )
        text = resp.content[0].text.strip()

    return None if text == "SKIP" else text


def gen_goals_and_summary(ai, milestone_title, completed_titles):
    """Single Claude call → (goals, summary). Plain prose, no markdown."""
    if not completed_titles:
        return ("No completed work in this sprint.", "No issues were completed in this sprint.")

    titles_block = "\n".join(f"- {t}" for t in completed_titles)
    resp = ai.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": (
                "You are writing a leadership briefing for a completed software sprint.\n\n"
                f"Sprint: {milestone_title}\n"
                f"Completed issues:\n{titles_block}\n\n"
                "Produce TWO sections, each plain prose with no markdown, no bullets, no preamble.\n"
                "Do NOT lead with or emphasize unit testing — frame the work around the actual "
                "feature and bug-fix work.\n\n"
                "GOALS: 1-2 sentences stating what this sprint set out to accomplish, framed as objectives.\n"
                "SUMMARY: 2-4 sentences describing the work that was completed and its business value.\n\n"
                "Output format exactly:\n"
                "GOALS:\n<text>\n\nSUMMARY:\n<text>"
            ),
        }],
    )
    text = resp.content[0].text.strip()
    g = re.search(r"GOALS:\s*(.*?)(?=\n\s*SUMMARY:)", text, re.DOTALL | re.IGNORECASE)
    s = re.search(r"SUMMARY:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    goals = g.group(1).strip() if g else text
    summary = s.group(1).strip() if s else ""
    return goals, summary


# ---------------------------------------------------------------------------
# Milestone / sprint discovery
# ---------------------------------------------------------------------------
def fetch_sprint_milestones(client, project_id, transition_date):
    """Return milestones that qualify as sprints (have a window, on/after transition)."""
    raw = client.get(f"/projects/{project_id}/milestones", params={"state": "all"})
    sprints = []
    for m in raw:
        if m.get("start_date") and m.get("due_date") and m["start_date"] >= transition_date:
            sprints.append(m)
    return sprints


def fetch_milestone_issues(client, project_id, milestone_title):
    return client.get(
        f"/projects/{project_id}/issues",
        params={"milestone": milestone_title, "scope": "all", "state": "all"},
    )


def months_overlapped(start_iso, due_iso):
    """Yield (year, month) tuples for every calendar month the window touches."""
    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(due_iso)
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield (y, m)
        m += 1
        if m > 12:
            m, y = 1, y + 1


# ---------------------------------------------------------------------------
# Per-project processing
# ---------------------------------------------------------------------------
def process_project(client, get_ai, group, project, today, force, dry_run):
    group_slug = group["slug"]
    project_slug = project["slug"]
    project_id = project["id"]
    transition_date = group.get("transition_date", "1970-01-01")

    reports_dir = DATA_DIR / group_slug / project_slug / "reports"
    sprints_dir = reports_dir / "sprints"
    months_dir = reports_dir / "months"

    log.info("-" * 50)
    log.info("Project %s (id=%s)", project["name"], project_id)

    milestones = fetch_sprint_milestones(client, project_id, transition_date)
    completed = [m for m in milestones if date.fromisoformat(m["due_date"]) < today]
    log.info("  %d sprint milestone(s), %d completed", len(milestones), len(completed))

    written = []
    # ms_slug -> {title, start_date, end_date, sprint_report} for the monthly rollup
    sprint_cache = {}

    # --- Per-sprint reports (test plan + sprint report) ---
    for ms in sorted(completed, key=lambda m: m["due_date"]):
        ms_slug = slugify(ms["title"])
        if not ms_slug:
            continue
        out_path = sprints_dir / f"{ms_slug}.json"

        if out_path.exists() and not force:
            log.info("  skip (exists): sprints/%s.json", ms_slug)
            try:
                cached = json.loads(out_path.read_text())
                sprint_cache[ms_slug] = {
                    "title": cached["title"],
                    "start_date": cached["start_date"],
                    "end_date": cached["end_date"],
                    "sprint_report": cached["sprint_report"],
                }
            except (json.JSONDecodeError, KeyError, OSError):
                log.warning("  could not reuse existing sprints/%s.json", ms_slug)
            continue

        issues = fetch_milestone_issues(client, project_id, ms["title"])
        closed = [i for i in issues if i.get("state") == "closed"]
        log.info("  sprint '%s': %d issues (%d closed)", ms["title"], len(issues), len(closed))

        metrics = build_metrics(issues)
        sprint_report = {"goals": None, "summary": None, "metrics": metrics}
        test_plan = []

        if dry_run:
            log.info("    [dry-run] would generate test plan + goals/summary via Anthropic")
        else:
            ai = get_ai()
            goals, summary = gen_goals_and_summary(ai, ms["title"], [i["title"] for i in closed])
            sprint_report["goals"] = goals
            sprint_report["summary"] = summary
            for issue in sorted(closed, key=lambda i: i["iid"]):
                if is_excluded_from_test_plan(issue):
                    continue
                steps = get_test_steps(ai, issue)
                if steps is None:
                    continue
                test_plan.append({
                    "iid": issue["iid"],
                    "title": issue["title"],
                    "web_url": issue.get("web_url", ""),
                    "steps": steps,
                })

        record = {
            "group_slug": group_slug,
            "project_slug": project_slug,
            "milestone_slug": ms_slug,
            "title": ms["title"],
            "start_date": ms["start_date"],
            "end_date": ms["due_date"],
            "generated_at": now_iso(),
            "test_plan": test_plan,
            "sprint_report": sprint_report,
        }
        sprint_cache[ms_slug] = {
            "title": ms["title"],
            "start_date": ms["start_date"],
            "end_date": ms["due_date"],
            "sprint_report": sprint_report,
        }

        if dry_run:
            log.info("    [dry-run] would write sprints/%s.json", ms_slug)
        else:
            sprints_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(record, indent=2))
            written.append(str(out_path))
            log.info("    wrote sprints/%s.json", ms_slug)

    # --- Monthly reports (rollup of sprints overlapping each past month) ---
    written += write_monthly_reports(
        months_dir, sprint_cache, today, group_slug, project_slug, force, dry_run
    )
    return written


def write_monthly_reports(months_dir, sprint_cache, today, group_slug, project_slug, force, dry_run):
    """Roll completed sprints up into per-month reports (shared by all group types).

    sprint_cache maps slug -> {title, start_date, end_date, sprint_report}. Each
    sprint contributes to every past calendar month its window overlaps.
    """
    by_month = {}  # (y, m) -> [slug, ...]
    for slug, c in sprint_cache.items():
        for (y, m) in months_overlapped(c["start_date"], c["end_date"]):
            # Past months only, and never before the dashboard's data cutoff.
            if EARLIEST_REPORT_MONTH <= (y, m) < (today.year, today.month):
                by_month.setdefault((y, m), []).append(slug)

    written = []
    for (y, m), slugs in sorted(by_month.items()):
        month_key = f"{y}-{m:02d}"
        out_path = months_dir / f"{month_key}.json"
        if out_path.exists() and not force:
            log.info("  skip (exists): months/%s.json", month_key)
            continue

        # Order sprint blocks by start date for a readable report
        blocks = []
        for slug in sorted(set(slugs), key=lambda s: sprint_cache[s]["start_date"]):
            c = sprint_cache[slug]
            blocks.append({
                "title": c["title"],
                "start_date": c["start_date"],
                "end_date": c["end_date"],
                "goals": c["sprint_report"]["goals"],
                "summary": c["sprint_report"]["summary"],
                "metrics": c["sprint_report"]["metrics"],
            })

        record = {
            "group_slug": group_slug,
            "project_slug": project_slug,
            "month": month_key,
            "generated_at": now_iso(),
            "sprints": blocks,
        }

        if dry_run:
            log.info("  [dry-run] would write months/%s.json (%d sprint block(s))", month_key, len(blocks))
        else:
            months_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(record, indent=2))
            written.append(str(out_path))
            log.info("  wrote months/%s.json (%d sprint block(s))", month_key, len(blocks))

    return written


# ---------------------------------------------------------------------------
# Local-sprint processing (reads locally collected sprint JSON)
#
# Used by standard (non project-mode) groups that store their sprint metrics as
# local JSON: Jira-sourced groups (Data Services) and GitLab iteration groups opted in via
# `"reports": true` in groups.json (Service Management). Both share the identical output layout,
# group-scoped: data/{group}/reports/{sprints,months}/.
# ---------------------------------------------------------------------------
def load_local_sprints(group_slug):
    """Collect sprint records from data/{group}/fy*/*.json (deduped by id).

    Jira-sourced groups store their sprint metrics as local JSON (there is no
    GitLab milestone API to query), so report generation reads those files
    instead of hitting an API.
    """
    group_dir = DATA_DIR / group_slug
    sprints = {}
    for fy_dir in sorted(group_dir.glob("fy*")):
        if not fy_dir.is_dir():
            continue
        for f in sorted(fy_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                log.warning("  could not read %s", f)
                continue
            for s in data.get("sprints", []):
                if s.get("id") is not None:
                    sprints[s["id"]] = s
    return list(sprints.values())


def process_local_group(get_ai, group, today, force, dry_run):
    """Generate sprint + monthly reports for a standard group from local sprint JSON.

    Covers Jira-sourced groups (Data Services) and iteration-sourced GitLab groups opted in
    via `"reports": true` (Service Management). Sources completed-issue titles + metrics from the
    locally collected sprint JSON. No test plan is generated here (Release Notes are
    built client-side from the sprint issues; see js/core/reports.js). Output layout
    mirrors project-mode groups but is group-scoped: data/{group}/reports/{sprints,months}/.
    """
    group_slug = group["slug"]
    reports_dir = DATA_DIR / group_slug / "reports"
    sprints_dir = reports_dir / "sprints"
    months_dir = reports_dir / "months"

    log.info("-" * 50)
    log.info("Local-sprint group %s (source=%s)", group["name"], group.get("source", "gitlab"))

    all_sprints = load_local_sprints(group_slug)
    completed = [
        s for s in all_sprints
        if s.get("end_date") and date.fromisoformat(s["end_date"]) < today
    ]
    log.info("  %d sprint(s), %d completed", len(all_sprints), len(completed))

    written = []
    sprint_cache = {}  # slug -> {title, start_date, end_date, sprint_report}

    # --- Per-sprint reports (sprint report only; no test plan for Jira) ---
    for s in sorted(completed, key=lambda s: s["end_date"]):
        slug = slugify(s["title"])
        if not slug:
            continue
        out_path = sprints_dir / f"{slug}.json"

        if out_path.exists() and not force:
            log.info("  skip (exists): sprints/%s.json", slug)
            try:
                cached = json.loads(out_path.read_text())
                sprint_cache[slug] = {
                    "title": cached["title"],
                    "start_date": cached["start_date"],
                    "end_date": cached["end_date"],
                    "sprint_report": cached["sprint_report"],
                }
            except (json.JSONDecodeError, KeyError, OSError):
                log.warning("  could not reuse existing sprints/%s.json", slug)
            continue

        issues = s.get("issues", [])
        closed = [i for i in issues if i.get("state") == "closed"]
        log.info("  sprint '%s': %d issues (%d closed)", s["title"], len(issues), len(closed))

        metrics = build_metrics(issues)
        sprint_report = {"goals": None, "summary": None, "metrics": metrics}

        if dry_run:
            log.info("    [dry-run] would generate goals/summary via Anthropic")
        else:
            ai = get_ai()
            goals, summary = gen_goals_and_summary(ai, s["title"], [i["title"] for i in closed])
            sprint_report["goals"] = goals
            sprint_report["summary"] = summary

        record = {
            "group_slug": group_slug,
            "project_slug": None,
            "milestone_slug": slug,
            "title": s["title"],
            "start_date": s["start_date"],
            "end_date": s["end_date"],
            "generated_at": now_iso(),
            "test_plan": [],
            "sprint_report": sprint_report,
        }
        sprint_cache[slug] = {
            "title": s["title"],
            "start_date": s["start_date"],
            "end_date": s["end_date"],
            "sprint_report": sprint_report,
        }

        if dry_run:
            log.info("    [dry-run] would write sprints/%s.json", slug)
        else:
            sprints_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(record, indent=2))
            written.append(str(out_path))
            log.info("    wrote sprints/%s.json", slug)

    # --- Monthly reports (shared rollup) ---
    written += write_monthly_reports(
        months_dir, sprint_cache, today, group_slug, None, force, dry_run
    )
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate AI report JSON for completed sprints / past months.")
    parser.add_argument("--group", help="Limit to a single group slug (default: all report-eligible groups)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if output JSON exists")
    parser.add_argument("--dry-run", action="store_true", help="Log planned work; no AI calls, no writes")
    args = parser.parse_args()

    force = args.force or os.environ.get("REPORTS_FORCE", "").lower() in ("1", "true", "yes")

    if not os.environ.get("GITLAB_TOKEN"):
        sys.exit("Error: GITLAB_TOKEN environment variable is required")

    verify_ssl = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")
    client = GitLabClient()  # reads GITLAB_URL / GITLAB_TOKEN / GITLAB_SSL_VERIFY

    # Lazily build the Anthropic client only when a sprint/month actually needs
    # generating, so idle runs (nothing new completed) need no ANTHROPIC_API_KEY
    # and never fail. When work exists but the key is missing, it errors clearly.
    _ai = {}

    def get_ai():
        if "client" not in _ai:
            _ai["client"] = make_ai_client(verify_ssl)
        return _ai["client"]

    groups = load_groups()
    if args.group:
        groups = [g for g in groups if g.get("slug") == args.group]
        if not groups:
            sys.exit(f"Error: group '{args.group}' not found in groups.json")

    today = date.today()
    written = []

    for group in groups:
        if group.get("mode") == "projects":
            log.info("=" * 60)
            log.info("Group %s", group["name"])
            for project in group.get("projects", []):
                written += process_project(client, get_ai, group, project, today, force, args.dry_run)
        elif group.get("source") == "jira" or group.get("reports"):
            # Jira-sourced groups (Data Services) and iteration groups opted in via
            # "reports": true (Service Management) both read local sprint JSON.
            log.info("=" * 60)
            log.info("Group %s", group["name"])
            written += process_local_group(get_ai, group, today, force, args.dry_run)
        else:
            log.info("Skipping group %s (no report support)", group.get("slug"))
            continue

    log.info("=" * 60)
    if args.dry_run:
        log.info("Dry run complete — no files written.")
    else:
        log.info("Done. %d report file(s) written.", len(written))


if __name__ == "__main__":
    main()
