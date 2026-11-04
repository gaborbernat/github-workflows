Add `check.yaml`, a reusable workflow that runs a tox matrix for a Python library. Each row sets its Python and runner.
The tox install follows the upload cutoff, and Ubuntu packages and coverage data are optional; a caller job merges the
coverage data.
