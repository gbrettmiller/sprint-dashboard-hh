#!/usr/bin/env python3
"""
Update fields of an existing GitLab issue.

Supports partial updates - only specified fields are modified.

Usage:
    python3 scripts/issue_update.py [project_id] <issue_iid> [options]

Examples:
    # Using GITLAB_PROJECT env var (default: 12421)
    python3 scripts/issue_update.py 1183 --add-labels "status::in-progress"
    python3 scripts/issue_update.py 1183 --state-event close
    python3 scripts/issue_update.py 1183 --weight 5 --assignee username
    python3 scripts/issue_update.py 1183 --remove-labels "status::todo" --add-labels "status::done"

    # Explicit project override
    python3 scripts/issue_update.py 10324 1183 --add-labels "priority::high"

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
        description="Update fields of a GitLab issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update labels (using default project)
  %(prog)s 1183 --add-labels "status::in-progress"
  %(prog)s 1183 --remove-labels "status::todo" --add-labels "status::done"
  %(prog)s 1183 --labels "bug,critical,priority::high"

  # Change state
  %(prog)s 1183 --state-event close
  %(prog)s 1183 --state-event reopen

  # Update other fields
  %(prog)s 1183 --weight 5 --assignee username
  %(prog)s 1183 --title "New title" --description "New description"

  # Explicit project override
  %(prog)s 10324 1183 --add-labels "priority::high"

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

    # Basic fields
    parser.add_argument("--title", help="New title")
    parser.add_argument("--description", help="New description")

    # Label management
    parser.add_argument("--labels", help="Replace all labels (comma-separated)")
    parser.add_argument("--add-labels", help="Add labels (comma-separated)")
    parser.add_argument("--remove-labels", help="Remove labels (comma-separated)")

    # State
    parser.add_argument("--state-event", choices=["close", "reopen"],
                        help="Change issue state")

    # Assignment
    parser.add_argument("--assignee", help="Assignee username (use 'none' to unassign)")

    # Other fields
    parser.add_argument("--weight", type=int, help="Issue weight")
    parser.add_argument("--iteration", type=int, help="Iteration/milestone ID")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    # Check that at least one field is being updated
    if not any([args.title, args.description, args.labels, args.add_labels,
                args.remove_labels, args.state_event, args.assignee, args.weight is not None,
                args.iteration is not None]):
        parser.error("At least one field must be specified for update")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Fetch current issue state
        log.info("Fetching issue #%d from project %s", args.issue_iid, args.project_id)
        issue = client.get_issue(args.project_id, args.issue_iid)

        print(f"\nIssue #{issue['iid']}: {issue['title']}")
        print(f"Current state: {issue['state']}")
        print(f"Current labels: {', '.join(issue.get('labels', [])) or 'None'}")
        print()

        # Build update payload
        fields = {}

        if args.title:
            fields["title"] = args.title

        if args.description:
            fields["description"] = args.description

        if args.labels:
            fields["labels"] = args.labels

        if args.add_labels:
            current_labels = set(issue.get('labels', []))
            new_labels = set(l.strip() for l in args.add_labels.split(','))
            combined = current_labels | new_labels
            fields["labels"] = ','.join(sorted(combined))

        if args.remove_labels:
            current_labels = set(issue.get('labels', []))
            remove_labels = set(l.strip() for l in args.remove_labels.split(','))
            remaining = current_labels - remove_labels
            fields["labels"] = ','.join(sorted(remaining))

        if args.state_event:
            fields["state_event"] = args.state_event

        if args.assignee:
            if args.assignee.lower() == 'none':
                fields["assignee_ids"] = [0]  # Unassign
            else:
                # Lookup user ID
                try:
                    users = client.get(f"/users?username={args.assignee}")
                    if users:
                        fields["assignee_id"] = users[0]["id"]
                    else:
                        log.error("User '%s' not found", args.assignee)
                        sys.exit(1)
                except Exception as e:
                    log.error("Failed to lookup user '%s': %s", args.assignee, e)
                    sys.exit(1)

        if args.weight is not None:
            fields["weight"] = args.weight

        if args.iteration is not None:
            fields["milestone_id"] = args.iteration

        # Update issue
        log.info("Updating issue #%d", args.issue_iid)
        updated_issue = client.update_issue(args.project_id, args.issue_iid, **fields)

        # Display result
        print("=" * 80)
        print("✓ Issue updated successfully!")
        print("=" * 80)
        print(f"\nIssue #{updated_issue['iid']}: {updated_issue['title']}")
        print(f"State: {updated_issue['state']}")

        labels = updated_issue.get('labels', [])
        if labels:
            print(f"Labels: {', '.join(labels)}")
        else:
            print(f"Labels: None")

        weight = updated_issue.get('weight')
        if weight:
            print(f"Weight: {weight}")

        assignee = updated_issue.get('assignee')
        if assignee:
            print(f"Assignee: @{assignee['username']}")
        else:
            print(f"Assignee: None")

        print(f"\nURL: {updated_issue['web_url']}")
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
