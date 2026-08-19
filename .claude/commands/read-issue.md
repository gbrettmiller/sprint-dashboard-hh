Read a GitLab issue and display its details.

Usage: /read-issue <issue_iid> [--show-comments] [project_id <iid>]

Run the following, passing all arguments through:
```
python3 scripts/issue_read.py $ARGUMENTS
```

Display the returned issue details clearly: title, state, description, labels, weight, milestone, and assignee. If `--show-comments` was passed, also display the comments thread.
