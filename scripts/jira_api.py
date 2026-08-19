#!/usr/bin/env python3
"""
Shared Jira API client for the Data Services data source (Jira Server / Data Center).

Mirrors the structure and resilience of gitlab_api.py (rate-limit handling,
5xx exponential backoff, configurable SSL), but speaks the Jira REST v2 and
Agile v1 APIs and uses Personal Access Token bearer authentication.

Jira Server/DC paginates with startAt/maxResults + a total/isLast marker rather
than GitLab's Link headers, so pagination is handled explicitly here.

Usage:
    from jira_api import JiraClient

    client = JiraClient()
    server = client.server_info()
    sprints = client.board_sprints(board_id, state="active,closed")
    issues = client.search("sprint = 42", expand="changelog")

Configuration (environment variables):
    JIRA_URL         Base URL of the Jira instance (e.g. https://jira.example.com)
    JIRA_TOKEN       Personal Access Token (sent as: Authorization: Bearer <token>)
    JIRA_SSL_VERIFY  "false"/"0"/"no" to disable SSL verification (default: enabled)
"""

import os
import sys
import time
import logging

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JIRA_URL = os.environ.get("JIRA_URL", "").rstrip("/")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN", "")
JIRA_SSL_VERIFY = os.environ.get("JIRA_SSL_VERIFY", "true").lower() not in ("0", "false", "no")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
log = logging.getLogger("jira_api")


# ---------------------------------------------------------------------------
# Jira API Client
# ---------------------------------------------------------------------------
class JiraClient:
    """Jira Server/Data Center REST client with retry logic and pagination."""

    def __init__(self, url=None, token=None, verify_ssl=None):
        """
        Initialize the Jira API client.

        Args:
            url: Jira base URL (default: JIRA_URL env var)
            token: Personal Access Token (default: JIRA_TOKEN env var)
            verify_ssl: Enable SSL verification (default: JIRA_SSL_VERIFY env var)
        """
        self.url = (url or JIRA_URL).rstrip("/")
        self.token = token or JIRA_TOKEN
        self.verify_ssl = verify_ssl if verify_ssl is not None else JIRA_SSL_VERIFY

        if not self.url:
            log.error("JIRA_URL environment variable is required")
            sys.exit(1)
        if not self.token:
            log.error("JIRA_TOKEN environment variable is required")
            sys.exit(1)

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })
        self.session.verify = self.verify_ssl

        log.debug("Initialized Jira client: %s (SSL verify: %s)", self.url, self.verify_ssl)

    # -----------------------------------------------------------------------
    # Low-level request with retries
    # -----------------------------------------------------------------------
    def _request(self, path, params=None):
        """GET a single JSON object with rate-limit handling and 5xx retries.

        Args:
            path: API path beginning with "/" (e.g. "/rest/api/2/serverInfo")
                  or a full URL.
            params: Query parameters dict.

        Returns:
            Parsed JSON (dict or list).
        """
        url = path if path.startswith("http") else f"{self.url}{path}"

        for attempt in range(5):
            resp = self.session.get(url, params=params)

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

    def get(self, path, params=None):
        """GET a single (non-paginated) JSON object."""
        return self._request(path, params)

    def get_paged(self, path, params=None, values_key="values"):
        """GET all pages of a startAt/maxResults-paginated endpoint.

        Handles both the Agile API shape ({startAt, maxResults, total, isLast,
        values: [...]}) and the search shape ({startAt, maxResults, total,
        issues: [...]}). Set values_key accordingly ("values" or "issues").

        Args:
            path: API path (e.g. "/rest/agile/1.0/board/5/sprint").
            params: Query parameters dict (page markers are managed here).
            values_key: Key holding the result array in each page.

        Returns:
            Concatenated list of all items across pages.
        """
        results = []
        params = dict(params or {})
        start_at = int(params.get("startAt", 0))
        params.setdefault("maxResults", 50)

        while True:
            params["startAt"] = start_at
            page = self._request(path, params)

            batch = page.get(values_key, [])
            results.extend(batch)

            # Stop conditions: explicit isLast, empty batch, or reached total.
            if page.get("isLast") is True:
                break
            if not batch:
                break
            total = page.get("total")
            max_results = page.get("maxResults", params["maxResults"]) or len(batch)
            start_at += len(batch)
            if total is not None and start_at >= total:
                break
            # Guard against non-advancing pages.
            if len(batch) < max_results and total is None:
                break

        return results

    # -----------------------------------------------------------------------
    # High-level helpers
    # -----------------------------------------------------------------------
    def server_info(self):
        """Return server info (includes deploymentType: Server/DataCenter/Cloud)."""
        return self.get("/rest/api/2/serverInfo")

    def fields(self):
        """Return all fields, incl. custom fields (to locate the Story Points id)."""
        return self.get("/rest/api/2/field")

    def board_sprints(self, board_id, state=None):
        """Return all sprints for a Scrum board, optionally filtered by state.

        Args:
            board_id: Numeric Agile board id.
            state: Comma-separated states ("active", "closed", "future") or None.
        """
        params = {}
        if state:
            params["state"] = state
        return self.get_paged(
            f"/rest/agile/1.0/board/{board_id}/sprint", params, values_key="values"
        )

    def search(self, jql, fields=None, expand=None):
        """Run a JQL search, returning all matching issues (paginated).

        Args:
            jql: JQL query string.
            fields: List of field ids to return (None = default set).
            expand: Comma-separated expand options (e.g. "changelog").
        """
        params = {"jql": jql}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = expand
        return self.get_paged("/rest/api/2/search", params, values_key="issues")

    def get_current_user(self):
        """Return the authenticated user (myself)."""
        return self.get("/rest/api/2/myself")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    """Probe connectivity and print server + user info with current credentials."""
    try:
        client = JiraClient()
        info = client.server_info()
        user = client.get_current_user()
        print(f"✓ Connected to Jira: {client.url}")
        print(f"  Deployment: {info.get('deploymentType')}  Version: {info.get('version')}")
        print(f"  Authenticated as: {user.get('name')} ({user.get('displayName')})")
        print(f"  SSL Verification: {client.verify_ssl}")
    except requests.HTTPError as e:
        print(f"✗ API Error: {e.response.status_code} - {e.response.text[:300]}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
