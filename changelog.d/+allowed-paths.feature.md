Add an `allowed-paths` input to `validate-release-patch`. When it is set, the patch may change only the paths matching
those glob patterns, and the Towncrier configuration is no longer read. Without it, the Action checks the changelog and
fragment deletions as before.
