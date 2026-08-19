#!/usr/bin/env python3
"""
Shared GitLab API client for issue management skills.

Provides a centralized client with consistent error handling, pagination,
rate limiting, and retry logic extracted from existing scripts.

Usage:
    from gitlab_api import GitLabClient

    client = GitLabClient()
    issue = client.get_issue(project_id, issue_iid)
    issues = client.list_issues(project_id=project_id, state='opened')
"""

import os
import sys
import time
import logging
from urllib.parse import quote as urlquote

import requests
from dotenv import load_dotenv

# Loads .env from the repo root (walks up from this file) so GITLAB_URL/GITLAB_TOKEN/
# GITLAB_PROJECT persist across demo sessions without re-exporting each time. Never
# overrides variables already set in the shell environment.
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")
GITLAB_SSL_VERIFY = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")


def issue_token():
    """Return the token for issue metadata operations (read, list, create, comment, update, close).

    Prefers GITLAB_ISSUE_TOKEN when set (e.g. a Cloud Services group token that can access
    ORBIT, PULSE, etc.), falling back to GITLAB_TOKEN. Scripts that touch the repo
    (issue_implement.py, backfill.py, scheduled_update.py) bypass this and use
    GITLAB_TOKEN directly.
    """
    return os.environ.get("GITLAB_ISSUE_TOKEN") or GITLAB_TOKEN

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
log = logging.getLogger("gitlab_api")


# ---------------------------------------------------------------------------
# GitLab API Client
# ---------------------------------------------------------------------------
class GitLabClient:
    """Centralized GitLab API client with retry logic and pagination."""

    def __init__(self, url=None, token=None, verify_ssl=None):
        """
        Initialize GitLab API client.

        Args:
            url: GitLab instance URL (default: GITLAB_URL env var)
            token: API token (default: GITLAB_TOKEN env var)
            verify_ssl: Enable SSL verification (default: GITLAB_SSL_VERIFY env var)
        """
        self.url = (url or GITLAB_URL).rstrip("/")
        self.token = token or GITLAB_TOKEN
        self.verify_ssl = verify_ssl if verify_ssl is not None else GITLAB_SSL_VERIFY
        self.api_base = f"{self.url}/api/v4"

        if not self.token:
            log.error("GITLAB_TOKEN environment variable is required")
            sys.exit(1)

        # Create session with persistent settings
        self.session = requests.Session()
        self.session.headers.update({"PRIVATE-TOKEN": self.token})
        self.session.verify = self.verify_ssl

        log.debug("Initialized GitLab client: %s (SSL verify: %s)", self.url, self.verify_ssl)

    def get(self, path, params=None):
        """
        GET request with pagination, rate-limit handling, and retries.

        Args:
            path: API path (e.g., '/projects/123/issues' or full URL)
            params: Query parameters dict

        Returns:
            List of results (for paginated endpoints) or dict (for single-object endpoints)

        Raises:
            requests.HTTPError: On non-5xx errors after retries exhausted
        """
        results = []
        params = dict(params or {})
        params.setdefault("per_page", 100)

        # Support both relative paths and full URLs
        if path.startswith("http://") or path.startswith("https://"):
            page_url = path
        else:
            page_url = f"{self.api_base}{path}" if path.startswith("/") else f"{self.api_base}/{path}"

        while page_url:
            for attempt in range(5):
                resp = self.session.get(page_url, params=params)

                # Rate limiting (429)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    log.warning("Rate-limited, sleeping %ds", wait)
                    time.sleep(wait)
                    continue

                # Server errors (5xx) - retry with exponential backoff
                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    log.warning("Server error %d, retry %d/5 in %ds", resp.status_code, attempt + 1, wait)
                    time.sleep(wait)
                    continue

                # Other errors - raise immediately
                resp.raise_for_status()
                break
            else:
                # All retries exhausted
                resp.raise_for_status()

            data = resp.json()

            # Single-object endpoint
            if isinstance(data, dict):
                return data

            # List endpoint - accumulate results
            if isinstance(data, list):
                results.extend(data)

            # Check for next page via Link header
            page_url = None
            params = {}  # params are baked into the next URL
            link = resp.headers.get("Link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    page_url = part.split("<")[1].split(">")[0]
                    break

        return results

    def post(self, path, json=None):
        """
        POST request with rate-limit handling and retries.

        Args:
            path: API path (e.g., '/projects/123/issues')
            json: Request body as dict

        Returns:
            Response JSON as dict

        Raises:
            requests.HTTPError: On error after retries exhausted
        """
        url = f"{self.api_base}{path}" if path.startswith("/") else f"{self.api_base}/{path}"

        for attempt in range(5):
            resp = self.session.post(url, json=json)

            # Rate limiting (429)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning("Rate-limited, sleeping %ds", wait)
                time.sleep(wait)
                continue

            # Server errors (5xx) - retry with exponential backoff
            if resp.status_code >= 500:
                wait = 2 ** attempt
                log.warning("Server error %d, retry %d/5 in %ds", resp.status_code, attempt + 1, wait)
                time.sleep(wait)
                continue

            # Success or client error
            resp.raise_for_status()
            return resp.json()

        # All retries exhausted
        resp.raise_for_status()

    def put(self, path, json=None):
        """
        PUT request with rate-limit handling and retries.

        Args:
            path: API path (e.g., '/projects/123/issues/42')
            json: Request body as dict

        Returns:
            Response JSON as dict

        Raises:
            requests.HTTPError: On error after retries exhausted
        """
        url = f"{self.api_base}{path}" if path.startswith("/") else f"{self.api_base}/{path}"

        for attempt in range(5):
            resp = self.session.put(url, json=json)

            # Rate limiting (429)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning("Rate-limited, sleeping %ds", wait)
                time.sleep(wait)
                continue

            # Server errors (5xx) - retry with exponential backoff
            if resp.status_code >= 500:
                wait = 2 ** attempt
                log.warning("Server error %d, retry %d/5 in %ds", resp.status_code, attempt + 1, wait)
                time.sleep(wait)
                continue

            # Success or client error
            resp.raise_for_status()
            return resp.json()

        # All retries exhausted
        resp.raise_for_status()

    # -----------------------------------------------------------------------
    # High-level issue methods
    # -----------------------------------------------------------------------

    def get_issue(self, project_id, issue_iid):
        """
        Get a single issue by IID.

        Args:
            project_id: Project ID (numeric or path encoded)
            issue_iid: Issue IID (internal ID, not global ID)

        Returns:
            Issue dict
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}/issues/{issue_iid}"
        return self.get(path)

    def list_issues(self, project_id=None, group_id=None, **filters):
        """
        List issues from a project or group with optional filters.

        Args:
            project_id: Project ID (use this OR group_id, not both)
            group_id: Group ID (use this OR project_id, not both)
            **filters: Additional query parameters (state, labels, iteration_id, assignee_username, etc.)

        Returns:
            List of issue dicts

        Example:
            client.list_issues(project_id=123, state='opened', labels='bug,critical')
        """
        if project_id:
            project_encoded = urlquote(str(project_id), safe="")
            path = f"/projects/{project_encoded}/issues"
        elif group_id:
            group_encoded = urlquote(str(group_id), safe="")
            path = f"/groups/{group_encoded}/issues"
        else:
            raise ValueError("Either project_id or group_id must be provided")

        return self.get(path, params=filters)

    def create_issue(self, project_id, title, **kwargs):
        """
        Create a new issue.

        Args:
            project_id: Project ID
            title: Issue title
            **kwargs: Optional fields (description, labels, weight, assignee_id, iteration_id, etc.)

        Returns:
            Created issue dict

        Example:
            client.create_issue(123, "Fix bug", description="Bug details", labels="bug", weight=3)
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}/issues"

        payload = {"title": title}
        payload.update(kwargs)

        return self.post(path, json=payload)

    def update_issue(self, project_id, issue_iid, **fields):
        """
        Update an existing issue.

        Args:
            project_id: Project ID
            issue_iid: Issue IID
            **fields: Fields to update (title, description, labels, state_event, weight, etc.)

        Returns:
            Updated issue dict

        Example:
            client.update_issue(123, 42, state_event='close', labels='status::done')
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}/issues/{issue_iid}"

        return self.put(path, json=fields)

    def add_comment(self, project_id, issue_iid, body):
        """
        Add a comment (note) to an issue.

        Args:
            project_id: Project ID
            issue_iid: Issue IID
            body: Comment text (supports markdown)

        Returns:
            Created note dict
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}/issues/{issue_iid}/notes"

        return self.post(path, json={"body": body})

    def get_comments(self, project_id, issue_iid):
        """
        Get all comments (notes) for an issue.

        Args:
            project_id: Project ID
            issue_iid: Issue IID

        Returns:
            List of note dicts
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}/issues/{issue_iid}/notes"

        return self.get(path)

    def close_issue(self, project_id, issue_iid, comment=None, **fields):
        """
        Close an issue, optionally with a comment and label updates.

        Args:
            project_id: Project ID
            issue_iid: Issue IID
            comment: Optional closing comment
            **fields: Additional fields to update (labels, add_labels, remove_labels, etc.)

        Returns:
            Updated issue dict
        """
        # Add closing comment first (if provided)
        if comment:
            self.add_comment(project_id, issue_iid, comment)

        # Close the issue with any additional field updates
        update_fields = {"state_event": "close"}
        update_fields.update(fields)

        return self.update_issue(project_id, issue_iid, **update_fields)

    # -----------------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------------

    def get_project(self, project_id):
        """
        Get project details.

        Args:
            project_id: Project ID (numeric or path encoded)

        Returns:
            Project dict
        """
        project_encoded = urlquote(str(project_id), safe="")
        path = f"/projects/{project_encoded}"
        return self.get(path)

    def get_group(self, group_id):
        """
        Get group details.

        Args:
            group_id: Group ID (numeric or path encoded)

        Returns:
            Group dict
        """
        group_encoded = urlquote(str(group_id), safe="")
        path = f"/groups/{group_encoded}"
        return self.get(path)

    def get_current_user(self):
        """
        Get current authenticated user.

        Returns:
            User dict
        """
        return self.get("/user")

    def detect_tier(self, group_id):
        """
        Detect if group has Premium features (iterations) or Free tier (milestones only).

        Args:
            group_id: Group ID

        Returns:
            'iterations' if Premium+, 'milestones' if Free tier
        """
        try:
            group_encoded = urlquote(str(group_id), safe="")
            path = f"/groups/{group_encoded}/iterations"
            resp = self.session.get(f"{self.api_base}{path}", params={"per_page": 1})

            if resp.status_code == 200:
                log.info("Premium detected – using Group Iterations API")
                return "iterations"
        except Exception:
            pass

        log.info("Free tier detected – using Group Milestones API")
        return "milestones"


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    """Test the API client with current credentials."""
    try:
        client = GitLabClient()
        user = client.get_current_user()
        print(f"✓ Authenticated as: {user['username']} ({user['name']})")
        print(f"  Email: {user.get('email', 'N/A')}")
        print(f"  GitLab URL: {client.url}")
        print(f"  SSL Verification: {client.verify_ssl}")
    except requests.HTTPError as e:
        print(f"✗ API Error: {e.response.status_code} - {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
