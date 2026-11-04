`release-notes.yaml` reads the Towncrier configuration only when the `changelog` input is empty, so a repository without
`[tool.towncrier]`, such as a multi-package workspace, can render its release notes when it passes `changelog`.
