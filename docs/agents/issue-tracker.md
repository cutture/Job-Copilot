# Issue tracker

GitHub Issues on `cutture/Job-Copilot`, through the `gh` CLI. The map is the issue labelled `wayfinder:map`, currently "Job Copilot: route to a v1 spec" (number 1). Commit attribution comes from the session.

## Wayfinding operations

**Tickets and frontier.** List the map's child tickets with their blockers. The frontier is open tickets with no assignee and no open blockers.

```sh
gh api graphql -f query='{repository(owner:"cutture",name:"Job-Copilot"){issue(number:1){subIssues(first:50){nodes{number title state assignees(first:3){nodes{login}} labels(first:5){nodes{name}} blockedBy(first:20){nodes{title state}}}}}}}'
```

**Claim.** `gh issue edit <n> --repo cutture/Job-Copilot --add-assignee cutture`, before any other work.

**Create a ticket.** Create the issue with its `wayfinder:<type>` label and a `## Question` body, then attach it to the map:

```sh
gh api -X POST repos/cutture/Job-Copilot/issues/1/sub_issues -F sub_issue_id=$(gh api repos/cutture/Job-Copilot/issues/<n> --jq .id)
```

**Resolve.** Write the answer to a file, using the Write tool rather than a heredoc inside a long command, then run:

```sh
python scripts/wayfinder_resolve.py <n> <answer-file> "<one-line gist>"
```

It posts the comment, closes the ticket and adds the map line. Edit other map sections separately, re-reading the map just before writing because other sessions may have changed it.
