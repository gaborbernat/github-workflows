Add `prepare-jetbrains-post-release`, a composite action that commits the next `-dev` plugin version after a release
without an App token, so `publish-post-release-pr` can open the bump pull request.
