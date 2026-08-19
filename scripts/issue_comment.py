#!/usr/bin/env python3
"""
Add a comment (note) to a GitLab issue.

Usage:
    # Interactive mode
    python3 scripts/issue_comment.py [project_id] <issue_iid>

    # Non-interactive mode
    python3 scripts/issue_comment.py [project_id] <issue_iid> --body "Comment text"

Examples:
    # Using GITLAB_PROJECT env var (default: 99001)
    python3 scripts/issue_comment.py 1183 --body "Implementation complete, testing locally"
    python3 scripts/issue_comment.py 1183  # Interactive mode

    # Explicit project override
    python3 scripts/issue_comment.py 91001 1183 --body "Different project comment"

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
    """Prompt for multi-line input (end with Ctrl+D or two empty lines)."""
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Add a comment to a GitLab issue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (using default project)
  %(prog)s 1183

  # Non-interactive mode
  %(prog)s 1183 --body "Implementation complete, testing locally"

  # Explicit project override
  %(prog)s 91001 1183 --body "Different project comment"

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
    parser.add_argument("issue_iid", type=int, help="Issue IID (internal ID)")
    parser.add_argument("--body", help="Comment text (supports markdown)")

    args = parser.parse_args()

    # Validate project_id is available
    if not args.project_id:
        parser.error("project_id required: provide as argument or set GITLAB_PROJECT environment variable")

    try:
        # Initialize client
        client = GitLabClient(token=issue_token())

        # Fetch issue (to verify it exists and get context)
        log.info("Fetching issue #%d from project %s", args.issue_iid, args.project_id)
        issue = client.get_issue(args.project_id, args.issue_iid)

        print(f"\nIssue #{issue['iid']}: {issue['title']}")
        print(f"State: {issue['state']}")
        print()

        # Get comment body
        if args.body:
            body = args.body
        else:
            # Interactive mode
            body = prompt_multiline("Comment text (markdown supported)")

        if not body:
            log.error("Comment body cannot be empty")
            sys.exit(1)

        # Add comment
        log.info("Adding comment to issue #%d", args.issue_iid)
        note = client.add_comment(args.project_id, args.issue_iid, body)

        # Display confirmation
        print("=" * 80)
        print("✓ Comment added successfully!")
        print("=" * 80)
        print(f"\nComment ID: {note['id']}")
        print(f"Author: @{note['author']['username']}")
        print(f"Issue: {issue['web_url']}#note_{note['id']}")
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
