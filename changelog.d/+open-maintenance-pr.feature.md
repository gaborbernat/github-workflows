Add `open-maintenance-pr.yaml`, a reusable workflow that opens or updates a pull request from a read-only job's patch.
The patch must touch only the caller's `allowed-paths`, as regular non-executable files or deletions, and the App token
is minted only after that check.
