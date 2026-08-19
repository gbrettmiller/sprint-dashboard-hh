Implement a GitLab issue end-to-end: read requirements, branch, code, track status, and close.

Usage: /implement-issue <issue_iid> [--assign-to-me] [project_id <iid>]

Default project is 99001 (sprint-metrics-dashboard). Pass an explicit project_id as the first positional argument to target another project (e.g. `91001` for ORBIT).

## Workflow

### Step 1 — Read the issue

Run `issue_implement.py` to fetch full issue details and surface branch/commit guidance:

```
python3 scripts/issue_implement.py $ARGUMENTS
```

Display the returned issue title, description, acceptance criteria, suggested branch name, and commit message template.

### Step 2 — Create a feature branch

Check current branch. If on `master`, create and switch to the suggested branch from Step 1:

```
git checkout -b <suggested-branch-name>
```

Never implement directly on master.

### Step 3 — Mark in-progress

Update the issue labels before writing any code:

```
python3 scripts/issue_update.py <issue_iid> --add-labels "status::in-progress"
```

### Step 4 — Implement

Make the code changes collaboratively with the user. Follow the project's four-layer architecture (Core → Services → UI). Reference the acceptance criteria from Step 1 as the definition of done.

Add progress comments when reaching meaningful milestones:

```
python3 scripts/issue_comment.py <issue_iid> --body "<progress note>"
```

### Step 5 — Close when complete

Once implementation is verified:

```
python3 scripts/issue_close.py <issue_iid> \
  --note "Implemented in <commit-hash>. <brief summary of what was done.>" \
  --add-labels "status::done"
```

Display the closed issue URL.
