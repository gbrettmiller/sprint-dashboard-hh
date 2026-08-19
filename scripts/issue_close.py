#!/usr/bin/env python3
"""
Close a GitLab issue with optional closing note and label updates.

Usage:
    python3 scripts/issue_close.py [project_id] <issue_iid> [options]

Examples:
    # Using GITLAB_PROJECT env var (default: 12421)
    python3 scripts/issue_close.py 1183
    python3 scripts/issue_close.py 1183 --note "Implemented in commit abc123"
    python3 scripts/issue_close.py 1183 --note "Fixed and verified" --add-labels "status::done,verified"

    # Explicit project override
    python3 scripts/issue_close.py 10324 1183 --note "Different project issue closed"

Environment Variables:
    GITLAB_URL         - GitLab instance URL (default: https://gitlab.com)
    GITLAB_TOKEN       - API token with api scope (required)
    GITLAB_SSL_VERIFY  - Enable SSL verification (default: true)
    GITLAB_PROJECT     - Default project ID (default: 12421)
"""

import sys
import os
import argparse

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0])
from gitlab_api import GitLabClient, log, issue_token


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Close a GitLab issue with optional note",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Simple close (using default project)
  %(prog)s 1183

  # Close with note
  %(prog)s 1183 --note "Implemented in commit abc123"

  # Close with note and labels
  %(prog)s 1183 --note "Fixed and verified" --add-labels "status::done,verified"

  # Explicit project override
  %(prog)s 10324 1183 --note "Different project issue"

Environment Variables:
  GITLAB_URL         GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN       API token with api scope (required)
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
    parser.add_argument("issue_iid", type=int, help="Issue IID (internal ID)")
    parser.add_argument("--note", help="Closing comment (supports markdown)")
    parser.add_argument("--add-labels", help="Labels to add when closing (comma-separated)")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Fetch current issue
        log.info("Fetching issue #%d from project %s", args.issue_iid, args.project_id)
        issue = client.get_issue(args.project_id, args.issue_iid)

        print(f"\nIssue #{issue['iid']}: {issue['title']}")
        print(f"Current state: {issue['state']}")

        # Check if already closed
        if issue['state'] == 'closed':
            print("\n⚠ Issue is already closed.")
            response = input("Do you want to add a comment anyway? [y/N]: ").strip().lower()
            if response != 'y':
                print("Aborted.")
                sys.exit(0)

            # Just add comment if requested
            if args.note:
                log.info("Adding comment to closed issue")
                note = client.add_comment(args.project_id, args.issue_iid, args.note)
                print(f"\n✓ Comment added: {issue['web_url']}#note_{note['id']}")
            sys.exit(0)

        print()

        # Build fields for close operation
        fields = {}

        if args.add_labels:
            current_labels = set(issue.get('labels', []))
            new_labels = set(l.strip() for l in args.add_labels.split(','))
            combined = current_labels | new_labels
            fields["labels"] = ','.join(sorted(combined))

        # Close issue (with optional note and field updates)
        log.info("Closing issue #%d", args.issue_iid)
        closed_issue = client.close_issue(args.project_id, args.issue_iid, comment=args.note, **fields)

        # Display result
        print("=" * 80)
        print("✓ Issue closed successfully!")
        print("=" * 80)
        print(f"\nIssue #{closed_issue['iid']}: {closed_issue['title']}")
        print(f"State: {closed_issue['state']}")

        labels = closed_issue.get('labels', [])
        if labels:
            print(f"Labels: {', '.join(labels)}")

        if args.note:
            print(f"\nClosing note added.")

        print(f"\nURL: {closed_issue['web_url']}")
        print()

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
