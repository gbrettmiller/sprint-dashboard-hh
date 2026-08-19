Close a GitLab issue with an optional note and label updates.

Usage: /close-issue <issue_iid> [--note "closing note"] [--add-labels "label1,label2"] [project_id <iid>]

Run the following, passing all arguments through:
```
python3 scripts/issue_close.py $ARGUMENTS
```

Confirm the issue was closed and display the final state. Default project is 12421; provide explicit project_id for other projects (e.g. 10324 for MIRARS).
