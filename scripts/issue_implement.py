#!/usr/bin/env python3
"""
Start implementation workflow for a GitLab issue.

Displays issue details, suggests branch name and commit message template,
and optionally assigns the issue to the current user.

Usage:
    python3 scripts/issue_implement.py [project_id] <issue_iid> [--assign-to-me]

Examples:
    # Using GITLAB_PROJECT env var (default: 99001)
    python3 scripts/issue_implement.py 1183
    python3 scripts/issue_implement.py 1183 --assign-to-me

    # Explicit project override
    python3 scripts/issue_implement.py 91001 1183

Environment Variables:
    GITLAB_URL         - GitLab instance URL (default: https://gitlab.com)
    GITLAB_TOKEN       - API token with api scope (required for assignment)
    GITLAB_SSL_VERIFY  - Enable SSL verification (default: true)
    GITLAB_PROJECT     - Default project ID (default: 99001)
    GITLAB_USERNAME    - Your GitLab username (for --assign-to-me)
"""

import sys
import os
import re
import argparse

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0])
from gitlab_api import GitLabClient, log


def slugify(text):
    """Convert text to slug format for branch names."""
    # Convert to lowercase
    text = text.lower()
    # Replace non-alphanumeric with hyphens
    text = re.sub(r'[^a-z0-9]+', '-', text)
    # Remove leading/trailing hyphens
    text = text.strip('-')
    # Limit length
    if len(text) > 50:
        text = text[:50].rstrip('-')
    return text


def infer_type_prefix(labels):
    """Infer commit type prefix from issue labels."""
    if not labels:
        return "feat"

    labels_lower = [l.lower() for l in labels]

    if any("bug" in l or "defect" in l for l in labels_lower):
        return "fix"
    elif any("doc" in l for l in labels_lower):
        return "docs"
    elif any("test" in l for l in labels_lower):
        return "test"
    elif any("refactor" in l for l in labels_lower):
        return "refactor"
    elif any("chore" in l or "maintenance" in l for l in labels_lower):
        return "chore"
    elif any("improvement" in l or "enhancement" in l for l in labels_lower):
        return "feat"
    elif any("feature" in l or "new" in l for l in labels_lower):
        return "feat"
    else:
        return "feat"


def format_user(user):
    """Format user dict as @username."""
    if not user:
        return "None"
    return f"@{user.get('username', 'unknown')}"


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Start implementation workflow for a GitLab issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using default project
  %(prog)s 1183
  %(prog)s 1183 --assign-to-me

  # Explicit project override
  %(prog)s 91001 1183

Environment Variables:
  GITLAB_URL         GitLab instance URL (default: https://gitlab.com)
  GITLAB_TOKEN       API token with api scope (required for assignment)
  GITLAB_SSL_VERIFY  Enable SSL verification (default: true)
  GITLAB_PROJECT     Default project ID (default: 99001)
  GITLAB_USERNAME    Your GitLab username (for --assign-to-me)
        """
    )

    parser.add_argument(
        "project_id",
        nargs="?",
        default=os.environ.get("GITLAB_PROJECT"),
        help="GitLab project ID (default: GITLAB_PROJECT env var, numeric or path)"
    )
    parser.add_argument("issue_iid", type=int, help="Issue IID (internal ID)")
    parser.add_argument("--assign-to-me", action="store_true",
                        help="Assign issue to you (requires GITLAB_USERNAME env var)")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    try:
        # Initialize client
        client = GitLabClient()

        # Fetch issue
        log.info("Fetching issue #%d from project %s", args.issue_iid, args.project_id)
        issue = client.get_issue(args.project_id, args.issue_iid)

        # Assign to me (if requested)
        if args.assign_to_me:
            username = os.environ.get("GITLAB_USERNAME")
            if not username:
                log.error("GITLAB_USERNAME environment variable is required for --assign-to-me")
                sys.exit(1)

            try:
                # Lookup user ID
                users = client.get(f"/users?username={username}")
                if users:
                    user_id = users[0]["id"]
                    log.info("Assigning issue to %s", username)
                    issue = client.update_issue(args.project_id, args.issue_iid, assignee_id=user_id)
                else:
                    log.error("User '%s' not found", username)
                    sys.exit(1)
            except Exception as e:
                log.error("Failed to assign issue: %s", e)
                sys.exit(1)

        # Generate suggestions
        branch_slug = slugify(issue['title'])
        branch_name = f"{issue['iid']}-{branch_slug}"

        type_prefix = infer_type_prefix(issue.get('labels'))
        title_brief = issue['title'][:72]  # Keep commit title under 72 chars

        # Print implementation plan
        print("\n" + "=" * 80)
        print(f"Implementation Plan for Issue #{issue['iid']}")
        print("=" * 80)

        print(f"\nIssue: #{issue['iid']} - {issue['title']}")
        project_ref = issue.get('references', {}).get('full') or f"Project {issue.get('project_id')}"
        print(f"Project: {project_ref}")
        print(f"State: {issue['state']}")

        labels = issue.get('labels', [])
        if labels:
            print(f"Labels: {', '.join(labels)}")

        weight = issue.get('weight')
        if weight:
            print(f"Weight: {weight}")

        assignee = issue.get('assignee')
        print(f"Assignee: {format_user(assignee)}")

        # Description
        description = issue.get('description', '').strip()
        if description:
            print(f"\nDescription:")
            print("─" * 80)
            # Truncate if too long
            if len(description) > 500:
                print(description[:500] + "\n\n[... truncated ...]")
            else:
                print(description)
            print("─" * 80)

        # Suggested branch
        print(f"\nSuggested Branch:")
        print(f"  git checkout -b {branch_name}")

        # Commit message template
        print(f"\nCommit Message Template:")
        print("─" * 80)
        print(f"{type_prefix}: {title_brief}")
        print(f"")
        print(f"Implements #{issue['iid']} - {issue['title']}")
        print(f"")
        print(f"Issue: {issue['web_url']}")
        print("─" * 80)

        # Next steps
        print(f"\nNext Steps:")
        print(f"  1. Create feature branch: git checkout -b {branch_name}")
        print(f"  2. Implement changes")
        print(f"  3. Reference issue in commits (e.g., 'Implements #{issue['iid']}')")
        print(f"  4. Update issue status during work (/update-issue)")
        print(f"  5. Add progress comments (/comment-issue)")
        print(f"  6. Close issue when complete (/close-issue)")

        # URL for reference
        print(f"\nIssue URL: {issue['web_url']}")
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
