Add `prepare-release-creator.yaml`, a reusable workflow that prepares releases for repositories that use
release-creator. Its assemble job selects the version from the tags and pending fragments, links fragments to their pull
requests, runs the caller's changelog command, and uploads a patch. Its push job checks the patch against the caller's
allowed paths and pushes the release commit and tag with the release App token.
