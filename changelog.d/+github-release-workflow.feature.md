Add `github-release.yaml`, a reusable workflow that verifies the PyPI files and publishes the GitHub Release in a job
that runs in the caller's `release` environment. It replaces the reconcile and publish steps that callers otherwise
copy.
