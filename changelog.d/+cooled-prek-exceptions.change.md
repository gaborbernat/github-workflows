Admit the `[tool.nab]` per-package `uploaded-prior-to` exceptions in `cooled-prek` hook environments, so a hook
dependency pinned past the seven-day cutoff installs the same way as the release lock. Before, prepare failed on such a
pin.
