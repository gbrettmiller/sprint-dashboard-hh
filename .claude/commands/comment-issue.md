Add a comment to a GitLab issue.

Usage: /comment-issue <issue_iid> [--body "comment text"] [project_id <iid>]

Run the following, passing all arguments through:
```
python3 scripts/issue_comment.py $ARGUMENTS
```

If no `--body` is provided, prompt the user for the comment text before running. Default project is 99001; provide explicit project_id for other projects.
