# Evalstone GitHub Action

Run an Evalstone suite on every pull request, get the report as a job summary
and as a PR comment (updated in place on each push), and fail the check when the
gate does not pass.

```yaml
# .github/workflows/evals.yml
name: Evals
on: { pull_request: {} }
permissions: { contents: read, pull-requests: write }
jobs:
  evals:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: marceloribeiro/evalstone/action@main
        with:
          suite: nightly
          working-directory: evals          # where evalstone.yaml lives
          install: "evalstone[anthropic]"   # pip spec; judges need a key:
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

| Input | Default | Meaning |
| --- | --- | --- |
| `suite` | — | suite name from `evalstone.yaml` (required) |
| `working-directory` | `.` | directory holding `evalstone.yaml` |
| `config` | `evalstone.yaml` | config path, relative to the working directory |
| `install` | `evalstone` | pip install spec (extras, a version pin, or a path for monorepos — relative to the working directory) |
| `python-version` | `3.12` | |
| `baseline` | | a saved JSON report to gate regressions against: absolute (a previous run's `report` output), or relative to the working directory |
| `report` | | where the JSON report is written, relative to the working directory; by default a file under the runner's temp directory, so the checkout stays clean |
| `failures` | `10` | failing results shown (`0`: none) |
| `comment` | `true` | post/update the PR comment (needs `pull-requests: write`); skipped on pull requests from forks, whose token cannot comment |
| `comment-id` | | set to a matrix value when the same suite runs in several jobs, so each keeps its own comment |
| `github-token` | `github.token` | token for the comment |
| `fail-on-gate` | `true` | fail the step when the gate does not pass |

Outputs: `report` (absolute path) and `passed` (`true` / `false` / `none`).
Inputs reach the shell through environment variables, never by interpolation,
so a suite name or path taken from the event payload cannot run commands.

The comment is rendered by `evalstone show <report> --markdown`, so the same
text is available locally.
