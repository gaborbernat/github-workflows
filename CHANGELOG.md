# Changelog

<!-- towncrier release notes start -->

<a name="release-0-2-0"></a>

## 0.2.0 (2026-10-19)

<a name="release-0-2-0-added"></a>

### Added

- Support Towncrier fragment directories outside the repository root during version selection and PR linking.
  (fragment-directory)

<a name="release-0-2-0-documentation"></a>

### Documentation

- Put the Action setup and input reference in the repository README, with examples for each step. (readme)

<a name="release-0-1-0"></a>

## 0.1.0 (2026-10-19)

<a name="release-0-1-0-added"></a>

### Added

- Commit and atomically push a release tag with a repository-scoped GitHub App token
  ([#1](https://github.com/tox-dev/github-workflows/pull/1)) by [@gaborbernat](https://github.com/gaborbernat).
- Prepare a Towncrier release with version selection, fragment linking, formatting, and `prek` checks
  ([#1](https://github.com/tox-dev/github-workflows/pull/1)) by [@gaborbernat](https://github.com/gaborbernat).
- Validate a release patch against the exact source commit before granting write access
  ([#1](https://github.com/tox-dev/github-workflows/pull/1)) by [@gaborbernat](https://github.com/gaborbernat).

<a name="release-0-1-0-changes"></a>

### Changes

- Run release commands directly in named GitHub Actions steps ([#1](https://github.com/tox-dev/github-workflows/pull/1))
  by [@gaborbernat](https://github.com/gaborbernat).

<a name="release-0-1-0-documentation"></a>

### Documentation

- Document each Action's inputs, outputs, side effects, and release rehearsal
  ([#1](https://github.com/tox-dev/github-workflows/pull/1)) by [@gaborbernat](https://github.com/gaborbernat).
