#!/usr/bin/env python3
"""
Commits files to a GitLab repository using the Commits API, bypassing
push rules (signed commit requirements, protected branch restrictions).

Usage:
    python3 scripts/api_commit.py "commit message" file1 file2 ...

Reads files relative to the current working directory and commits them
to the branch specified by CI_COMMIT_REF_NAME (or 'master' by default).

Required environment variables:
    CI_PUSH_TOKEN   - GitLab token with api scope
    CI_SERVER_URL   - e.g. https://code.cdso.army.mil
    CI_PROJECT_ID   - numeric project ID (set automatically by GitLab CI)

Optional:
    CI_COMMIT_REF_NAME - branch to commit to (default: master)
    GITLAB_SSL_VERIFY  - set to 'false' to disable SSL verification
"""

import os
import sys
import json
import base64
import logging

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
log = logging.getLogger("api_commit")

VERIFY_SSL = os.environ.get("GITLAB_SSL_VERIFY", "true").lower() not in ("0", "false", "no")

def main():
    if len(sys.argv) < 3:
        sys.exit(f"Usage: {sys.argv[0]} 'commit message' file1 [file2 ...]")

    commit_message = sys.argv[1]
    file_paths = sys.argv[2:]

    token = os.environ.get("CI_PUSH_TOKEN", "")
    server_url = os.environ.get("CI_SERVER_URL", "").rstrip("/")
    project_id = os.environ.get("CI_PROJECT_ID", "")
    branch = os.environ.get("CI_COMMIT_REF_NAME", "master")

    if not token:
        sys.exit("Error: CI_PUSH_TOKEN is required")
    if not server_url:
        sys.exit("Error: CI_SERVER_URL is required")
    if not project_id:
        sys.exit("Error: CI_PROJECT_ID is required")

    api_url = f"{server_url}/api/v4/projects/{project_id}/repository/commits"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}

    # Build actions list — check if file exists in repo to decide create vs update
    session = requests.Session()
    session.headers.update({"PRIVATE-TOKEN": token})
    session.verify = VERIFY_SSL

    actions = []
    for fpath in file_paths:
        if not os.path.exists(fpath):
            log.warning("File not found, skipping: %s", fpath)
            continue

        with open(fpath, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")

        # Check if file already exists in the repo
        check_url = f"{server_url}/api/v4/projects/{project_id}/repository/files/{requests.utils.quote(fpath, safe='')}"
        resp = session.head(check_url, params={"ref": branch})
        action = "update" if resp.status_code == 200 else "create"

        actions.append({
            "action": action,
            "file_path": fpath,
            "content": content,
            "encoding": "base64",
        })

    if not actions:
        log.info("No files to commit.")
        return

    log.info("Committing %d file(s) to branch '%s'", len(actions), branch)

    payload = {
        "branch": branch,
        "commit_message": commit_message,
        "actions": actions,
    }

    resp = session.post(api_url, json=payload)

    if resp.status_code == 201:
        result = resp.json()
        log.info("Commit created: %s", result.get("id", "")[:12])
    else:
        log.error("API error %d: %s", resp.status_code, resp.text)
        sys.exit(1)


if __name__ == "__main__":
    main()
