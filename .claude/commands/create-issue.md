Create a new GitLab issue with a Gherkin-formatted description.

Usage: /create-issue [project_id] [--labels "..."] [--weight N]

## Workflow

1. **Gather requirements conversationally.** Ask the user what the issue is about if not already clear. Clarify the role, goal, and benefit (for the user story) and the specific behaviors to test (for acceptance criteria).

2. **Ask for the issue type** before drafting. Present these options and wait for the user's selection:
   - **Bug** → label `type::Bug`
   - **Improvement** → label `type::Improvement`
   - **New Feature** → label `type::New Feature`
   - **Other** → no type label (issue created uncategorized)

3. **Draft the issue in Gherkin format** using this template:

```
## User Story

As a [role],
I want [feature/capability],
So that [benefit/value].

## Acceptance Criteria

**Scenario: [scenario name]**
- Given [precondition]
- When [action]
- Then [expected outcome]

**Scenario: [scenario name]**
- Given [precondition]
- When [action]
- Then [expected outcome]
```

   - Write at least one scenario per distinct behavior or edge case.
   - Keep scenarios atomic — one behavior per scenario.
   - Present the draft to the user and refine until confirmed.

4. **Create the issue** once the user approves the draft. Include the type label if one was selected:

```
python3 scripts/issue_create.py $ARGUMENTS --title "<title>" --description "<formatted description>" [--labels "type::<Type>"]
```

Omit `--labels` entirely if the user selected "Other".

Default project is 12421 (sprint-metrics-dashboard). Pass an explicit project_id as the first argument to target a different project (e.g. `10324` for MIRARS).

After creation, display the issue number and URL.
