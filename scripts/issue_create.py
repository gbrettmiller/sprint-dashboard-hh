#!/usr/bin/env python3
"""
Create a new GitLab issue interactively or via command-line arguments.

Usage:
    # Interactive mode
    python3 scripts/issue_create.py [project_id]

    # Non-interactive mode
    python3 scripts/issue_create.py [project_id] --title "Title" [options]

Examples:
    # Using GITLAB_PROJECT env var (default: 99001)
    python3 scripts/issue_create.py
    python3 scripts/issue_create.py --title "Fix bug" --description "Details" --labels "bug,critical" --weight 3

    # Explicit project override
    python3 scripts/issue_create.py 91001 --title "Different project issue"

Environment Variables:
    GITLAB_URL         - GitLab instance URL (default: https://gitlab.com)
    GITLAB_TOKEN       - API token with api scope (required)
    GITLAB_SSL_VERIFY  - Enable SSL verification (default: true)
    GITLAB_PROJECT     - Default project ID (default: 99001)
"""

import sys
import os
import argparse

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0])
from gitlab_api import GitLabClient, log, issue_token


def prompt_multiline(prompt_text):
    """Prompt for multi-line input (end with Ctrl+D or empty line)."""
    print(f"{prompt_text} (press Enter twice to finish):")
    lines = []
    empty_count = 0
    try:
        while True:
            line = input()
            if not line.strip():
                empty_count += 1
                if empty_count >= 2:
                    break
                lines.append(line)
            else:
                empty_count = 0
                lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines).strip()


def interactive_create(client, project_id):
    """Interactive issue creation."""
    print("\n=== Create New Issue ===\n")

    # Title (required)
    title = input("Title (required): ").strip()
    if not title:
        log.error("Title is required")
        sys.exit(1)

    # Description (optional)
    print()
    description = prompt_multiline("Description (optional)")

    # Labels (optional)
    print()
    labels_input = input("Labels (comma-separated, optional): ").strip()
    labels = labels_input if labels_input else None

    # Weight (optional)
    print()
    weight_input = input("Weight (optional): ").strip()
    weight = int(weight_input) if weight_input.isdigit() else None

    # Assignee (optional)
    print()
    assignee_input = input("Assignee username (optional): ").strip()

    # Iteration/Milestone (optional)
    print()
    iteration_input = input("Iteration/Milestone ID (optional): ").strip()
    iteration_id = int(iteration_input) if iteration_input.isdigit() else None

    # Build kwargs
    kwargs = {}
    if description:
        kwargs["description"] = description
    if labels:
        kwargs["labels"] = labels
    if weight is not None:
        kwargs["weight"] = weight
    if assignee_input:
        # Try to find user ID by username
        try:
            users = client.get(f"/users?username={assignee_input}")
            if users:
                kwargs["assignee_id"] = users[0]["id"]
            else:
                log.warning("User '%s' not found, skipping assignee", assignee_input)
        except Exception as e:
            log.warning("Failed to lookup user '%s': %s", assignee_input, e)
    if iteration_id is not None:
        kwargs["milestone_id"] = iteration_id  # GitLab API uses milestone_id for iterations

    # Create issue
    print("\nCreating issue...")
    return client.create_issue(project_id, title, **kwargs)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create a new GitLab issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (using default project)
  %(prog)s

  # Non-interactive mode
  %(prog)s --title "Fix bug" --description "Bug details" --labels "bug,critical" --weight 3

  # Explicit project override
  %(prog)s 91001 --title "Different project issue"

Environment Variables:
  GITLAB_URL         GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN       API token with api scope (required)
  GITLAB_SSL_VERIFY  Enable SSL verification (default: true)
  GITLAB_PROJECT     Default project ID (default: 99001)
        """
    )

    parser.add_argument(
        "project_id",
        nargs="?",
        default=os.environ.get("GITLAB_PROJECT"),
        help="GitLab project ID (default: GITLAB_PROJECT env var, numeric or path)"
    )
    parser.add_argument("--title", help="Issue title")
    parser.add_argument("--description", help="Issue description")
    parser.add_argument("--labels", help="Comma-separated labels")
    parser.add_argument("--weight", type=int, help="Issue weight")
    parser.add_argument("--assignee", help="Assignee username")
    parser.add_argument("--iteration", type=int, help="Iteration/milestone ID")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Verify project exists
        try:
            project = client.get_project(args.project_id)
            log.info("Creating issue in project: %s", project['name'])
        except Exception as e:
            log.error("Failed to access project %s: %s", args.project_id, e)
            sys.exit(1)

        # Interactive vs non-interactive
        if args.title:
            # Non-interactive mode
            kwargs = {}
            if args.description:
                kwargs["description"] = args.description
            if args.labels:
                kwargs["labels"] = args.labels
            if args.weight is not None:
                kwargs["weight"] = args.weight
            if args.assignee:
                # Lookup user ID
                try:
                    users = client.get(f"/users?username={args.assignee}")
                    if users:
                        kwargs["assignee_id"] = users[0]["id"]
                    else:
                        log.warning("User '%s' not found, skipping assignee", args.assignee)
                except Exception as e:
                    log.warning("Failed to lookup user '%s': %s", args.assignee, e)
            if args.iteration is not None:
                kwargs["milestone_id"] = args.iteration

            issue = client.create_issue(args.project_id, args.title, **kwargs)
        else:
            # Interactive mode
            issue = interactive_create(client, args.project_id)

        # Display result
        print("\n" + "=" * 80)
        print("✓ Issue created successfully!")
        print("=" * 80)
        print(f"\nIssue #{issue['iid']}: {issue['title']}")
        print(f"Project: {project['name']}")
        print(f"State: {issue['state']}")
        print(f"URL: {issue['web_url']}")
        if issue.get('labels'):
            print(f"Labels: {', '.join(issue['labels'])}")
        if issue.get('weight'):
            print(f"Weight: {issue['weight']}")
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
