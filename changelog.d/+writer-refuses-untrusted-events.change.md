The writer jobs in `open-maintenance-pr.yaml`, `prepare-release-creator.yaml`, `prepare-towncrier-release.yaml`,
`github-release.yaml`, `publish-pre-commit-mirror.yaml`, and `latex-to-pages.yaml` refuse callers that run on
`pull_request`, `pull_request_target`, `workflow_run`, `issue_comment`, or `merge_group`. The job fails with an error
before it checks out the repository or uses a token. Callers that ran a writer on those events must trigger it on
`push`, `schedule`, `workflow_dispatch`, or `release` instead.
