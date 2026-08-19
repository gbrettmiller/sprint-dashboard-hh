Update fields on a GitLab issue.

Usage: /update-issue <issue_iid> [options] [project_id <iid>]

Options:
  --title "New title"
  --description "New description"
  --labels "replace,all"
  --add-labels "add,these"
  --remove-labels "remove,these"
  --state-event close|reopen
  --assignee username
  --weight N
  --iteration ID

Run the following, passing all arguments through:
```
python3 scripts/issue_update.py $ARGUMENTS
```

Confirm the update succeeded and display any changed fields. Default project is 12421; provide explicit project_id for other projects (e.g. 10324 for MIRARS).
