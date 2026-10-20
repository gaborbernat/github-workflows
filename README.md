# GitHub workflows

Composite Actions check PR news, prepare a Towncrier release, verify its patch, push an App-authored commit and tag,
build a Python wheel and sdist, and render GitHub Release notes. They run as steps in the caller's workflow. Each
repository keeps its dispatch form, publisher, GitHub environment, and required check names.

## Check pull request news

`validate-news` reads `tool.towncrier` from `pyproject.toml`. It checks every added or modified fragment in the
configured directory against the configured categories, filename format, and nonempty content. A valid fragment runs
`towncrier check` against the PR base. A human PR without a fragment needs `skip news`; a bot PR without a fragment does
not. A bot's supplied fragment is checked and included in the normal release flow. The Action reads repository files and
Git history; it does not add labels or write to GitHub.

Keep the caller's existing `changelog` job name and full checkout. Install Towncrier from the caller's release lock
before calling the Action:

```yaml
changelog:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-26.04
  permissions:
    contents: read
  steps:
    - uses: actions/checkout@CHECKOUT_SHA
      with:
        fetch-depth: 0
        persist-credentials: false
    - uses: astral-sh/setup-uv@SETUP_UV_SHA
      with:
        python-version: "3.15"
    - run: |
        uv venv --python 3.15 "$RUNNER_TEMP/release-tools"
        uv pip sync --preview-features pylock --python "$RUNNER_TEMP/release-tools/bin/python" --group release pylock.toml
        echo "$RUNNER_TEMP/release-tools/bin" >>"$GITHUB_PATH"
    - uses: tox-dev/github-workflows/validate-news@SHA
```

Set `config` if Towncrier is configured in another Python project file. The Action expects a pull request base ref and a
Markdown or reStructuredText changelog. The caller should also run on `labeled` and `unlabeled` events, so a label added
after opening the PR updates the required check.

`label-bot-news` adds `skip news` to a bot PR with no fragment and removes it when the bot adds one. It reads the PR
file list through GitHub's API and never checks out PR code. Keep it in a separate `pull_request_target` workflow so the
read-only changelog job does not receive Issues write access. The
[caller in this repository](.github/workflows/label-bot-news.yaml) shows the permissions and events. Set `fragments` and
`extension` for an RST repository:

```yaml
- uses: tox-dev/github-workflows/label-bot-news@SHA
  with:
    fragments: docs/changelog
    extension: rst
```

## Start with a caller

The [release preparation workflow](.github/workflows/prepare-release.yaml) in this repository is a complete caller. Its
`assemble` job creates a patch without a write credential. Its `push` job applies and checks that patch before minting a
repository-scoped App token. Copy those jobs, then set the changelog path, fragment directory, commit message, and tag
style. Replace this repository's relative `uses: $/…` references with a full release commit SHA. In the examples below,
`SHA` means that release commit and `TOKEN_ACTION_SHA` means the pinned token Action commit in the linked workflow.

Both jobs need a full checkout (`fetch-depth: 0`, `persist-credentials: false`) and `release-creator`, Towncrier, and
`prek` installed from the caller's checked-in `pylock.toml`. Preparation needs `contents: read` and
`pull-requests: read` to resolve PR authors. The `push` job uses the `release-auth` environment with
`RELEASE_APP_PRIVATE_KEY` and the repository variable `RELEASE_APP_CLIENT_ID`. Install the App on that repository only,
with Contents write and Metadata read. Give it the necessary branch and tag ruleset bypass.

```text
main + fragments
       │
       ▼
prepare-towncrier ── version + patch ──► upload artifact
                                             │
                                       download artifact
                                             │
                                             ▼
                                   validate-release-patch
                                             │
                                       mint App token
                                             │
                                             ▼
                                      commit-and-tag ──► main + tag
```

The tag starts the caller's publisher. Keep PyPI trusted publishing in that top-level workflow, in a separate job with
`id-token: write`:
[PyPI does not support trusted publishing inside reusable workflows](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github).
Run `prek` on the tagged source before publication. Repositories with the standard `uv` wheel and sdist build can use
`build-python-distribution` in both the tag publisher and the PR rehearsal. The
[self-release workflow](.github/workflows/release.yaml) shows the GitHub Release path; callers keep their ecosystem
uploads. The [read-only validation workflow](.github/workflows/validate-release.yaml) is called from both this
repository's PR check and tag release. It builds a local candidate for PRs, checks the tagged source, and renders the
Release body. The tag caller alone has a Contents write job that creates the GitHub Release.

## Validate a Python release in both workflows

`validate-python-release.yaml` runs the shared Towncrier, package build, and note-rendering path from an exact PR head
or an existing tag. A PR run squashes the proposed changes onto its base, adds named and numbered bug-fix fragments, and
creates a commit and tag in the runner. It prepares and checks the changelog patch, runs `prek` on the candidate, builds
the wheel and sdist, and checks both entries' links and author credits. It also checks rejection of unsupported or
missing fragments, a dirty checkout, an existing release tag, a stale release branch, a patch with an unrelated file, an
invalid tag, and a missing changelog. The local commit and tag never leave the runner. The same tagged-source rendering
step runs on the local PR tag and on a real tag; the PR also renders a separate copy with its contributor fixture.

Call the same pinned workflow from the PR check and the tag publisher's build job:

```yaml
release-dry-run:
  if: github.event_name == 'pull_request'
  uses: >-
    tox-dev/github-workflows/.github/workflows/validate-python-release.yaml@SHA
  permissions:
    contents: read
    pull-requests: read
  with:
    changelog: CHANGELOG.md
    fragments: changelog.d
    format: markdown
    artifact-base-url: https://pypi.org/project/example/
```

```yaml
build:
  uses: >-
    tox-dev/github-workflows/.github/workflows/validate-python-release.yaml@SHA
  permissions:
    contents: read
    pull-requests: read
  with:
    changelog: CHANGELOG.md
    fragments: changelog.d
    format: markdown
    artifact-base-url: https://pypi.org/project/example/
```

The inputs must match in both callers. `changelog` and `fragments` are the paths in `tool.towncrier`; `format` is
`markdown` when the caller's `mdformat` hook formats its assembled changelog and `none` otherwise. `artifact-base-url`
ends just before the version; the workflow appends `1.2.3/` for tag `1.2.3`. Set it to the package's actual PyPI project
path. `artifact-label` changes the link text from `PyPI release`; `issue-role` selects whether reStructuredText
`:issue:` references link to issues or pull requests. `lock` defaults to `pylock.toml` and must have a `release` group
with `release-creator`, Towncrier, and `prek`. `python-version` defaults to `3.15`; `source` defaults to the repository
root for `uv build`. `artifact-prefix` defaults to empty; set it while comparing this workflow with an existing PR
rehearsal so the two jobs use distinct artifact names.

The PR caller may also expose `workflow_dispatch` on a non-main branch. In that event the workflow finds the open PR for
the branch, uses its base and author metadata, and performs the same local rehearsal. It fails when the branch has no
open PR.

On a tag, it validates the changelog and notes before building, matching the existing caller order. The job uploads
`python-package-distributions` with the wheel and sdist, and `release-validation-notes` with the body rendered from the
tagged source. On a PR it also uploads `release-dry-run` with the patch, assembled changelog, notes, contributor
fixture, no-metadata tag preview, and distribution hashes. A tag run has no fixture, so its notes lack GitHub
contributor metadata. The tag-only GitHub Release job must fetch generated notes with Contents write, rerender with
`render-release-notes`, and create the Release after the ecosystem upload. PyPI OIDC stays in the caller's separate
`release` environment job:
[PyPI does not support trusted publishing inside reusable workflows](https://docs.pypi.org/trusted-publishers/troubleshooting/#reusable-workflows-on-github).

## Prepare Towncrier release

`prepare-towncrier` reads a clean checkout, chooses the next version, links fragments to their squash PRs, runs
Towncrier and `prek`, and writes a binary Git patch. It does not commit or push. It fails if version selection, notes
rendering, formatting, or checks fail, or if preparation creates untracked files or no patch.

```yaml
  - id: prepare
    uses: tox-dev/github-workflows/prepare-towncrier@SHA
    with:
      bump: ${{ inputs.bump }}
      changelog: docs/changelog.md
      fragments: docs/changelog.d
      format: markdown
      patch: ${{ runner.temp }}/release.patch
```

- `bump`: `auto` (default), `major`, `minor`, `patch`, or `calver`. Passed to `release-creator tags --next`; `auto` uses
  the pending fragments. The caller's dispatch form decides which choices to expose.
- `version`: Explicit version for a caller with its own version selector. It takes precedence over `bump`; the Action
  still checks that it is newer than existing tags.
- `changelog` **(required)**: Tracked file Towncrier writes, such as `CHANGELOG.md` or `docs/changelog.rst`. This must
  match `tool.towncrier.filename` in the caller's `pyproject.toml`.
- `fragments`: Fragment directory relative to the checkout root; default `changelog.d`. Set this to the caller's
  `tool.towncrier.directory`. Version selection and PR linking both read this directory.
- `format`: `none` (default) or `markdown`. `markdown` runs the caller's `mdformat` prek hook on the assembled
  changelog. Use `none` for RST or when that hook does not exist. The full `prek` suite runs in either case.
- `link-fragments`: `true` (default) resolves named fragments and authors through GitHub; `false` skips that step for a
  caller whose fragments already contain release links and credits.
- `patch` **(required)**: Writable path to the Git patch, usually under `runner.temp`. Upload this exact file as an
  artifact for the validation job.

**Output:** `version` is the selected tag string. Use `steps.prepare.outputs.version` as a job output and pass it to
both later Actions. **Working-tree effect:** Towncrier changes the changelog and consumes fragments; the patch records
those changes. The checkout must be clean before this Action starts.

## Validate release patch

`validate-release-patch` starts from a fresh checkout of the original branch commit. It rejects a branch that moved,
applies the uploaded patch, checks its changed paths and version heading, and runs `prek`. It leaves the patch staged
for the commit Action. It does not need a write token.

```yaml
  - uses: tox-dev/github-workflows/validate-release-patch@SHA
    with:
      version: ${{ needs.assemble.outputs.version }}
      patch: ${{ runner.temp }}/release-patch/release.patch
      changelog: docs/changelog.md
      fragments: docs/changelog.d
```

- `version` **(required)**: Exact tag chosen by preparation. The changelog must contain a heading for it.
- `patch` **(required)**: Local path of the downloaded patch artifact, not an artifact name or URL.
- `changelog` **(required)**: Same tracked path passed to preparation. Only this file and files below `fragments` may
  change in the patch.
- `fragments` **(required)**: Same directory passed to preparation. Towncrier may consume or rename its files.
- `heading-prefix`: Text before the version in its heading; default `## `. For `Version 1.2.3 (date)`, use `Version `.
  The Action expects the version to be followed by ` (`.
- `branch`: Protected release branch; default `main`.
- `remote`: Git remote fetched for the freshness check; default `origin`.
- `expected-sha`: Commit that preparation checked out. By default the Action uses `GITHUB_SHA`; set this when
  preparation used another commit.

**Output:** No named output. **Working-tree effect:** Applies and stages the patch. A failed `prek` run, unexpected
path, or modification by `prek` fails the job before a write credential is minted.

## Commit and tag release

`commit-and-tag` accepts only a staged release patch in a clean working tree. It commits with the GitHub App bot
identity, creates the tag, and atomically pushes the branch and tag to `origin`. A rejected push leaves neither remote
ref updated. Mint the token after validation with `actions/create-github-app-token`, narrowed to this repository and
Contents write.

```yaml
  - id: token
    uses: actions/create-github-app-token@TOKEN_ACTION_SHA
    with:
      client-id: ${{ vars.RELEASE_APP_CLIENT_ID }}
      private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}
      owner: ${{ github.repository_owner }}
      repositories: ${{ github.event.repository.name }}
      permission-contents: write
  - uses: tox-dev/github-workflows/commit-and-tag@SHA
    with:
      version: ${{ needs.assemble.outputs.version }}
      token: ${{ steps.token.outputs.token }}
      app-slug: ${{ steps.token.outputs.app-slug }}
      message: release ${{ needs.assemble.outputs.version }}
```

- `version` **(required)**: Tag name to create, such as `1.2.3`.
- `token` **(required)**: Short-lived installation token from the repository-only App. The Action never reads the key.
- `app-slug` **(required)**: `app-slug` output from the token Action, used to resolve the bot's Git identity.
- `message` **(required)**: Commit message. It is also the annotated tag message when `annotated` is `true`.
- `branch`: Target branch; default `main`. The checkout must still be at its validated commit.
- `annotated`: `false` (default) creates a lightweight tag; `true` creates an annotated tag. Match the repository's
  existing release history.

**Output:** No named output. **Remote effect:** One new commit on `branch` and one tag at that commit. The App needs a
branch and tag ruleset bypass. A stale branch, invalid tag, or ruleset rejection fails the push.

## Build Python distribution

`build-python-distribution` installs the caller's release group from `pylock.toml`, runs `prek` on the tagged tree, then
builds a wheel and sdist with `uv`. Call it after `actions/checkout` and `astral-sh/setup-uv`. The caller verifies the
tag and changelog section before this Action. Use the same Action and inputs after the local tag in the PR rehearsal;
this executes the build steps used by the tag publisher without publishing the artifacts.

```yaml
  - uses: tox-dev/github-workflows/build-python-distribution@SHA
    with:
      lock: pylock.toml
      python-version: '3.15'
      source: .
      out-dir: dist
```

- `lock`: Path to the caller's `pylock.toml`; default `pylock.toml`. Its `release` group must contain `prek` and every
  package needed by the caller's hooks.
- `python-version`: Managed Python used for release tools and the build; default `3.15`.
- `source`: Source directory passed to `uv build`; default `.`.
- `out-dir`: Directory for the wheel and sdist; default `dist`. The caller uploads files from this directory.

**Output:** No named output. **Working-tree effect:** Creates a release-tool environment under `runner.temp` and writes
a wheel and sdist to `out-dir`. The checkout must be clean before the Action starts; it fails if `prek` fails or changes
a tracked or untracked source file. Use a separate build path for repositories whose build command differs from
`uv build --sdist --wheel`.

## Render GitHub Release notes

`render-release-notes` checks the tag and its changelog section, finds the previous tag, and renders an unwrapped GitHub
Release body with `release-creator`. Call it on the local tag in a PR rehearsal and again on the actual tag. The
publisher still fetches GitHub's generated notes and creates the Release; this Action only writes a local Markdown file.

```yaml
  - uses: tox-dev/github-workflows/render-release-notes@SHA
    with:
      tag: ${{ github.ref_name }}
      changelog: CHANGELOG.md
      repository: ${{ github.repository }}
      artifact-url: https://pypi.org/project/example/${{ github.ref_name }}/
      generated-notes: ${{ runner.temp }}/generated-notes.md
      output: ${{ runner.temp }}/release-notes.md
```

- `tag` **(required)**: Release version, such as `1.2.3`. The checkout must contain its changelog section. A local PR
  rehearsal creates this tag without pushing it to GitHub.
- `changelog` **(required)**: Tracked Markdown or reStructuredText changelog in the format that `release-creator notes`
  parses, with exactly one section for the tag.
- `repository` **(required)**: GitHub `owner/repository` used in PR and comparison links.
- `artifact-url`: Ecosystem release URL, such as a PyPI version page. Omit it for a GitHub-only project.
- `artifact-label`: Link text for `artifact-url`; default `PyPI release`. Use `Zipapp` or another product name for a
  different artifact.
- `issue-role`: For reStructuredText, whether `:issue:` links target GitHub issues (default) or pull requests.
- `generated-notes`: Path to GitHub's generated-notes body. The tag publisher fetches it after PyPI publication; a PR
  rehearsal supplies a small fixture with its actual PR author and URL. This preserves New Contributors and fills any
  missing `by @handle` credit. Omit it when the release has no GitHub-generated contributor metadata.
- `output` **(required)**: Writable path for the GitHub Release body. Pass it to `gh release create --notes-file` only
  after the ecosystem publisher succeeds.

**Output:** `previous` is the nearest earlier version tag, or empty for the first release. **Working-tree effect:** The
Action writes only `output`. It rejects an invalid tag, a missing heading, an empty body, or a missing comparison link
when an earlier tag exists. It neither fetches generated notes nor writes a GitHub Release, so a PR job needs only read
permissions. Fetching generated notes uses GitHub's release endpoint and needs Contents write in the tag publisher.

## Check a caller before switching

The [Actions test suite](tests) executes each inline `run:` block in temporary Git repositories. The
[`release-dry-run` job](.github/workflows/check.yaml) invokes the composite Actions on a GitHub runner against a local
bare remote. It cannot prove that another repository's Towncrier template, release hooks, package build, or publisher
works. Run that caller's prepare and validation path at its PR head without pushing a GitHub ref or publishing an
artifact. Inspect the version, patch, changelog, notes, and built package before changing its live release workflow.

This repository releases its own Actions with the same prepare and tag path. See [Contributing](CONTRIBUTING.md) for
local checks and news fragments, and [Changelog](CHANGELOG.md) for released changes.
