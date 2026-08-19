List and filter GitLab issues.

Usage: /list-issues [--group <id>] [--project <id>] [--state opened|closed|all] [--labels label1,label2] [--format table|json|simple] [--limit N] [--assignee username] [--iteration ID]

Run the following, passing all arguments through:
```
python3 scripts/issue_list.py $ARGUMENTS
```

Display the results in a clear, readable format. Default project is 12421 (sprint-metrics-dashboard); use `--project` or `--group` to query other projects/groups.
