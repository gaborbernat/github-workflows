Add `release-notes.yaml`, a reusable workflow that renders the GitHub Release body in a read-only job and uploads it as
an artifact. Callers need not repeat the tool install, previous-tag selection, and upload steps.
