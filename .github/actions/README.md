# Composite Action Structure

Keep composite actions as orchestration. Put non-trivial bash or PowerShell in
scripts next to the action so it can be linted and tested directly.

Recommended layout:

```text
.github/actions/<action-name>/
  action.yml
  scripts/
    <focused-step>.sh
    <focused-step>.ps1
```

Use small, named composite steps that call those scripts through
`$GITHUB_ACTION_PATH`. Avoid composing sibling local actions from a published
remote action because relative `uses:` paths are resolved from the caller's
checkout.

Each action should include focused checks for its implementation scripts:

- YAML validation through actionlint.
- Bash validation through shellcheck.
- PowerShell parser validation for `.ps1` files.
- Contract tests for action-specific expectations that are easy to break while
  refactoring.

Actions that install tools should also expose debuggable outputs such as the
selected distribution, resolved version, executable name, executable path, and
related command paths. Tests should assert those outputs exist so consumers can
rely on them in follow-up workflow steps.
