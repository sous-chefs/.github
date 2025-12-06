# Description

Describe what this change achieves.

## Issues Resolved

List any existing issues this PR resolves.

## Check List

- [ ] All commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) format
  - **Required**: This triggers our automated CHANGELOG and release pipeline (release-please)
  - **Without conventional commits, your changes cannot be released**
  - Examples: `fix: resolve bug in resource`, `feat: add new property`, `docs: update README`
- [ ] New functionality includes testing
- [ ] New functionality has been documented in the README if applicable

## ⚠️ Important: Automated Release Workflow

**DO NOT manually edit these files:**

- ❌ `metadata.rb` version - Managed by release-please
- ❌ `CHANGELOG.md` - Auto-generated from conventional commits
- ❌ Version tags - Created automatically on release

**The release process:**

1. Merge PR with conventional commits → release-please creates a release PR
2. Merge release PR → automatic version bump, CHANGELOG update, and Supermarket publish
3. Your changes are released! 🎉

**Need help?** See [Conventional Commits guide](https://www.conventionalcommits.org/)
