#!/usr/bin/env python3
"""
List and filter GitLab issues from a project or group.

Usage:
    python3 scripts/issue_list.py [--group <id>] [--project <id>] [options]

Examples:
    python3 scripts/issue_list.py --project 91001 --state opened
    python3 scripts/issue_list.py --group 18274 --labels "type::bug,priority::high"
    python3 scripts/issue_list.py --project 91001 --milestone "v3.3.1.0" --state all
    python3 scripts/issue_list.py --group 18274 --iteration 2892 --state all
    python3 scripts/issue_list.py --project 91001 --format json --limit 10

Environment Variables:
    GITLAB_URL         - GitLab instance URL (default: https://gitlab.com)
    GITLAB_TOKEN       - API token with read_api scope (required)
    GITLAB_SSL_VERIFY  - Enable SSL verification (default: true)
    GITLAB_PROJECT     - Default project ID
    GITLAB_GROUP       - Default group ID
"""

import sys
import json
import argparse
import os

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0])
from gitlab_api import GitLabClient, log, issue_token


def format_labels_short(labels, max_width=40):
    """Format labels list with truncation."""
    if not labels:
        return ""
    label_str = ", ".join(labels)
    if len(label_str) > max_width:
        return label_str[:max_width-3] + "..."
    return label_str


def format_title_short(title, max_width=60):
    """Truncate title if too long."""
    if len(title) > max_width:
        return title[:max_width-3] + "..."
    return title


def print_table(issues):
    """Print issues in table format."""
    if not issues:
        print("No issues found.")
        return

    # Header
    print(f"\n{'IID':<6} {'Project':<20} {'Title':<60} {'State':<8} {'Wt':<4} {'Labels':<40}")
    print("=" * 140)

    # Rows
    for issue in issues:
        iid = f"#{issue['iid']}"
        project = issue.get('references', {}).get('short', f"{issue.get('project_id', '?')}")[:20]
        title = format_title_short(issue['title'], 60)
        state = issue['state']
        weight = str(issue.get('weight', '-'))
        labels = format_labels_short(issue.get('labels', []), 40)

        print(f"{iid:<6} {project:<20} {title:<60} {state:<8} {weight:<4} {labels:<40}")

    print(f"\nTotal: {len(issues)} issues")


def print_simple(issues):
    """Print issues in simple one-line format."""
    if not issues:
        print("No issues found.")
        return

    for issue in issues:
        iid = issue['iid']
        state_emoji = "✓" if issue['state'] == "closed" else "○"
        title = issue['title']
        weight = issue.get('weight', '-')
        print(f"{state_emoji} #{iid:<6} [W:{weight}] {title}")

    print(f"\nTotal: {len(issues)} issues")


def print_json(issues):
    """Print issues in JSON format."""
    output = {
        "total": len(issues),
        "issues": [
            {
                "iid": issue['iid'],
                "project_id": issue['project_id'],
                "title": issue['title'],
                "state": issue['state'],
                "labels": issue.get('labels', []),
                "weight": issue.get('weight'),
                "web_url": issue['web_url'],
                "created_at": issue.get('created_at'),
                "updated_at": issue.get('updated_at'),
            }
            for issue in issues
        ]
    }
    print(json.dumps(output, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="List and filter GitLab issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --project 91001 --state opened
  %(prog)s --group 18274 --labels "type::bug"
  %(prog)s --project 91001 --milestone "v3.3.1.0" --state all
  %(prog)s --group 18274 --iteration 2892 --state all
  %(prog)s --project 91001 --state all --format json --limit 20

Environment Variables:
  GITLAB_URL         GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN       API token with read_api scope (required)
  GITLAB_SSL_VERIFY  Enable SSL verification (default: true)
  GITLAB_PROJECT     Default project ID
  GITLAB_GROUP       Default group ID
        """
    )

    # Scope
    parser.add_argument("--project", help="Project ID (numeric or path)")
    parser.add_argument("--group", help="Group ID (numeric or path)")

    # Filters
    parser.add_argument("--state", choices=["opened", "closed", "all"], default="opened",
                        help="Issue state (default: opened)")
    parser.add_argument("--labels", help="Comma-separated labels (e.g., 'bug,critical')")
    parser.add_argument("--milestone", help="Milestone title (for project-level milestones, e.g. Cloud Services projects)")
    parser.add_argument("--iteration", help="Iteration ID (for group-level iterations, e.g. Service Management)")
    parser.add_argument("--assignee", help="Assignee username")
    parser.add_argument("--author", help="Author username")
    parser.add_argument("--search", help="Search query in title and description")

    # Output
    parser.add_argument("--format", choices=["table", "json", "simple"], default="table",
                        help="Output format (default: table)")
    parser.add_argument("--limit", type=int, help="Limit number of results")

    args = parser.parse_args()

    # Determine scope
    project_id = args.project or os.environ.get("GITLAB_PROJECT")
    group_id = args.group or os.environ.get("GITLAB_GROUP")

    if not project_id and not group_id:
        parser.error("Either --project or --group is required (or set GITLAB_PROJECT/GITLAB_GROUP env var)")

    if project_id and group_id:
        parser.error("Cannot specify both --project and --group")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Build filters
        filters = {"state": args.state}
        if args.labels:
            filters["labels"] = args.labels
        if args.milestone:
            filters["milestone"] = args.milestone
        if args.iteration:
            filters["iteration_id"] = args.iteration
        if args.assignee:
            filters["assignee_username"] = args.assignee
        if args.author:
            filters["author_username"] = args.author
        if args.search:
            filters["search"] = args.search

        # Fetch issues
        if project_id:
            log.info("Fetching issues from project %s", project_id)
            issues = client.list_issues(project_id=project_id, **filters)
        else:
            log.info("Fetching issues from group %s", group_id)
            issues = client.list_issues(group_id=group_id, **filters)

        # Apply limit
        if args.limit:
            issues = issues[:args.limit]

        # Display results
        if args.format == "table":
            print_table(issues)
        elif args.format == "json":
            print_json(issues)
        elif args.format == "simple":
            print_simple(issues)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(130)
    except Exception as e:
        log.error("Error: %s", e)
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            log.error("Response: %s", e.response.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
