# Test Coverage Analysis

This document analyses the current testing strategy for the `sous-chefs/.github` shared
configuration repository and proposes concrete improvements.

## Current State

The repository provides reusable GitHub Actions workflows and a custom composite action
for consuming Chef cookbook repositories across the Sous Chefs organisation. Current
quality gates are:

| Check | Tool | Trigger |
|---|---|---|
| Ruby/Chef unit tests | RSpec | PR + push |
| Chef code style | Cookstyle | PR + push |
| YAML syntax/style | yamllint | PR + push |
| Markdown style | markdownlint-cli2 | PR + push |
| Hyperlink validity | linkspector | PR + push |
| `metadata.rb` validity | check-chef-metadata-action | PR only |
| PR title format | action-semantic-pull-request | PR only |
| Workflow file changes | prevent-file-change-action | PR only |

## Gaps and Proposed Improvements

### 1. No workflow syntax validation (`actionlint`)

**Gap:** GitHub Actions workflow YAML can be syntactically valid YAML while still
containing semantic errors (invalid expressions, wrong action input names, type
mismatches, incorrect context references). None of the current checks catch these.

**Impact:** A broken workflow ships silently and fails only when a consuming cookbook
opens a PR — at that point, the error looks like a cookbook problem, not a
shared-workflow problem.

**Proposed fix:** Add an `actionlint` job to `lint-unit.yml`:

```yaml
check-workflows:
  runs-on: ubuntu-latest
  name: runner / actionlint
  steps:
    - uses: actions/checkout@v6
    - name: Run actionlint
      uses: raven-actions/actionlint@v2
```

`actionlint` understands GitHub Actions semantics — it type-checks expressions, validates
input/output names against the actions they reference, and catches common mistakes such as
`${{ env.VAR }}` used where `${{ inputs.VAR }}` was intended.

---

### 2. The `install-workstation` action is not tested in this repository

**Gap:** The custom `install-workstation` composite action is the critical dependency
for every consuming cookbook. It has no automated tests in this repository. A regression
(e.g., a broken install script URL, a missing `else` branch) will affect every cookbook
simultaneously.

**Impact:** Breakage is discovered only after it propagates to every consumer.

**Proposed fix:** Add a self-testing workflow that exercises the action on all three
supported platforms with multiple version inputs:

```yaml
# .github/workflows/test-install-workstation.yml
name: Test install-workstation action

on:
  pull_request:
    paths:
      - .github/actions/install-workstation/**

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        version: ["24", "latest"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v6
      - uses: ./.github/actions/install-workstation
        with:
          version: ${{ matrix.version }}
      - name: Verify chef command is available
        shell: bash
        run: chef --version
```

---

### 3. Windows installation is not verified

**Gap:** In `install-workstation/action.yml`, the Linux/macOS step ends with:

```yaml
cinc --version || chef --version
```

The Windows step has no equivalent verification. A failed Windows install produces no
immediate error; downstream steps fail with confusing messages instead.

**Proposed fix:** Add a verification step to the Windows branch of the composite action:

```yaml
- name: Verify Cinc Workstation (Windows)
  if: runner.os == 'Windows'
  shell: pwsh
  run: chef --version
```

---

### 4. macOS is listed as supported but never tested

**Gap:** The `install-workstation` action documents macOS support via the
`runner.os != 'Windows'` branch, but `lint-unit.yml` only accepts `ubuntu-latest` or
a Windows platform as inputs. macOS is never exercised by any workflow in this repo or
by any documented consumer pattern.

**Proposed fix:** Either document that macOS is unsupported (and remove the implicit
claim), or add a `macos-latest` matrix entry to the self-test workflow proposed in gap 2,
and optionally surface a `macos-latest` example in `CONTRIBUTING.md`.

---

### 5. `copilot-setup-steps.yml` uses a different (deprecated) install action

**Gap:** `copilot-setup-steps.yml` uses `actionshub/chef-install@6.0.0`, while all
other workflows use the custom `sous-chefs/.github/.github/actions/install-workstation`.
The custom action was created specifically to avoid checksum-mismatch failures in
`omnitruck.chef.io` — the old action is known to be unreliable.

**Impact:** Copilot setup sessions may silently fail for cookbook contributors.

**Proposed fix:** Update `copilot-setup-steps.yml` to use the custom action:

```yaml
- name: Install Cinc Workstation
  uses: sous-chefs/.github/.github/actions/install-workstation@main
```

---

### 6. `check-metadata` only runs on pull requests

**Gap:** The `check-metadata` job has `if: github.event_name == 'pull_request'`, so
pushes directly to the default branch (e.g., from `release-please`) bypass metadata
validation entirely.

**Proposed fix:** Remove the condition or broaden it:

```yaml
if: github.event_name == 'pull_request' || github.event_name == 'push'
```

---

### 7. No validation of `renovate.json`

**Gap:** The Renovate configuration is not linted. An invalid `renovate.json` causes
Renovate to silently skip the repository — automerge rules for patch updates would stop
working without any alert.

**Proposed fix:** Add a validation step using the Renovate config validator:

```yaml
check-renovate:
  runs-on: ubuntu-latest
  name: runner / Renovate config
  steps:
    - uses: actions/checkout@v6
    - uses: suzuki-shunsuke/github-action-renovate-config-validator@v1
```

Alternatively, Renovate's own `config:base` extension will surface a config error as a
Renovate dashboard issue, but explicit CI validation gives faster feedback.

---

### 8. No code coverage reporting for RSpec results

**Gap:** RSpec is run and its output is posted as a PR comment, but there is no
coverage metric collected or tracked over time. Coverage regressions in consuming
cookbooks cannot be detected automatically.

**Proposed fix:** Add SimpleCov to the recommended gem set and collect coverage in the
RSpec run. Update the workflow to upload coverage artifacts:

```yaml
- name: Run RSpec with coverage
  run: chef exec rspec -f j -o tmp/rspec_results.json -f p
  env:
    COVERAGE: "true"

- name: Upload coverage report
  uses: actions/upload-artifact@v7
  with:
    name: coverage
    path: coverage/
  if: always()
```

This requires consuming cookbooks to add SimpleCov to their `spec_helper.rb`, so this
is a lower-priority, opt-in improvement.

---

### 9. Action versions pinned to major tags, not SHAs

**Gap:** All third-party actions are pinned to mutable major-version tags
(e.g., `actions/checkout@v6`). A compromised or accidentally broken release within
that major version will affect every workflow run without any change being visible in
this repository's git history.

**Proposed fix:** Pin third-party actions to immutable commit SHAs with a comment
indicating the human-readable version:

```yaml
uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v6
```

Renovate can maintain these SHA pins automatically with the `"pinDigests": true` option
added to `renovate.json`.

---

### 10. `link-reporter` input is undocumented and unvalidated

**Gap:** The `link-reporter` input in `lint-unit.yml` accepts one of five values
(`local`, `github`, `pr-check`, `github-check`, `github-pr-review`) documented only
in a comment. No validation prevents callers from passing an invalid value, which would
cause a silent failure in the linkspector step.

**Proposed fix:** Add a validation step early in the `check-links` job:

```yaml
- name: Validate link-reporter input
  run: |
    valid_reporters="local github pr-check github-check github-pr-review"
    reporter="${{ inputs.link-reporter }}"
    if ! echo "$valid_reporters" | grep -qw "$reporter"; then
      echo "::error::Invalid link-reporter value: '$reporter'. Must be one of: $valid_reporters"
      exit 1
    fi
```

---

## Priority Summary

| Priority | Item | Effort |
|---|---|---|
| High | Add `actionlint` to `lint-unit.yml` | Low |
| High | Self-test `install-workstation` action | Medium |
| High | Add Windows install verification | Low |
| High | Fix `copilot-setup-steps.yml` to use custom action | Low |
| Medium | Test macOS platform support | Low |
| Medium | Run `check-metadata` on push, not only PRs | Low |
| Medium | Validate `renovate.json` in CI | Low |
| Low | Validate `link-reporter` input | Low |
| Low | Pin actions to SHA digests | Medium (Renovate automates) |
| Low | Add RSpec coverage reporting | High |
