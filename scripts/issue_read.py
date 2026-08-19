#!/usr/bin/env python3
"""
Read and display a single GitLab issue with all details.

Usage:
    python3 scripts/issue_read.py [project_id] <issue_iid> [--show-comments]

Examples:
    # Using GITLAB_PROJECT env var (default: 12421)
    python3 scripts/issue_read.py 1183
    python3 scripts/issue_read.py 1183 --show-comments

    # Explicit project override
    python3 scripts/issue_read.py 10324 1183

Environment Variables:
    GITLAB_URL         - GitLab instance URL (default: https://gitlab.com)
    GITLAB_TOKEN       - API token with read_api scope (required)
    GITLAB_SSL_VERIFY  - Enable SSL verification (default: true)
    GITLAB_PROJECT     - Default project ID (default: 12421)
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0])
from gitlab_api import GitLabClient, log, issue_token


def format_date(date_str):
    """Format ISO date string to readable format."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str


def format_labels(labels):
    """Format labels list as comma-separated string."""
    if not labels:
        return "None"
    if isinstance(labels, list):
        return ", ".join(labels)
    return str(labels)


def format_user(user):
    """Format user dict as @username."""
    if not user:
        return "None"
    return f"@{user.get('username', 'unknown')}"


def format_iteration(milestone):
    """Format iteration/milestone dict."""
    if not milestone:
        return "None"
    return f"{milestone.get('title', 'Unknown')} (#{milestone.get('id', 'N/A')})"


def print_issue(issue, show_comments=False, client=None):
    """Print formatted issue details."""

    # Header
    print(f"\nIssue #{issue['iid']}: {issue['title']}")
    print("=" * 80)

    # Basic metadata
    project = issue.get('references', {}).get('full', f"Project {issue.get('project_id', 'N/A')}")
    state = issue['state']
    state_emoji = "✓" if state == "closed" else "○"

    print(f"\nProject: {project}")
    print(f"State: {state_emoji} {state}")
    print(f"Type: {issue.get('type', 'issue')}")
    print(f"URL: {issue['web_url']}")

    # People
    print(f"\nAuthor: {format_user(issue.get('author'))}")
    print(f"Assignee: {format_user(issue.get('assignee'))}")

    # Categorization
    print(f"\nLabels: {format_labels(issue.get('labels'))}")
    print(f"Weight: {issue.get('weight', 'None')}")
    print(f"Iteration: {format_iteration(issue.get('milestone'))}")

    # Dates
    print(f"\nCreated: {format_date(issue.get('created_at'))}")
    print(f"Updated: {format_date(issue.get('updated_at'))}")
    if issue['state'] == 'closed':
        print(f"Closed: {format_date(issue.get('closed_at'))}")

    # Statistics
    print(f"\nUser Notes: {issue.get('user_notes_count', 0)}")
    print(f"Upvotes: {issue.get('upvotes', 0)} | Downvotes: {issue.get('downvotes', 0)}")

    # Description
    description = issue.get('description', '').strip()
    if description:
        print(f"\nDescription:")
        print("─" * 80)
        print(description)
        print("─" * 80)
    else:
        print(f"\nDescription: (empty)")

    # Comments (if requested)
    if show_comments and client:
        try:
            comments = client.get_comments(issue['project_id'], issue['iid'])
            # Filter out system notes
            user_comments = [c for c in comments if not c.get('system', False)]

            if user_comments:
                print(f"\nComments ({len(user_comments)}):")
                print("─" * 80)
                for idx, comment in enumerate(user_comments, 1):
                    author = format_user(comment.get('author'))
                    created = format_date(comment.get('created_at'))
                    body = comment.get('body', '').strip()
                    print(f"\n[{idx}] {author} at {created}:")
                    print(body)
                    if idx < len(user_comments):
                        print()
                print("─" * 80)
            else:
                print(f"\nComments: (none)")
        except Exception as e:
            log.warning("Failed to fetch comments: %s", e)
            print(f"\nComments: (failed to load)")

    print()  # Final newline


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Read and display a GitLab issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using default project (GITLAB_PROJECT env var)
  %(prog)s 1183
  %(prog)s 1183 --show-comments

  # Explicit project override
  %(prog)s 10324 1183

Environment Variables:
  GITLAB_URL         GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN       API token with read_api scope (required)
  GITLAB_SSL_VERIFY  Enable SSL verification (default: true)
  GITLAB_PROJECT     Default project ID (default: 12421)
        """
    )

    parser.add_argument(
        "project_id",
        nargs="?",
        default=os.environ.get("GITLAB_PROJECT"),
        help="GitLab project ID (default: GITLAB_PROJECT env var, numeric or path)"
    )
    parser.add_argument("issue_iid", type=int, help="Issue IID (internal ID, not global ID)")
    parser.add_argument("--show-comments", action="store_true", help="Include issue comments")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Fetch issue
        log.info("Fetching issue #%d from project %s", args.issue_iid, args.project_id)
        issue = client.get_issue(args.project_id, args.issue_iid)

        # Display issue
        print_issue(issue, show_comments=args.show_comments, client=client)

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
