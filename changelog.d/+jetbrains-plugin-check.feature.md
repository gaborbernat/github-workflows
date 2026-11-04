Add `jetbrains-plugin-check.yaml`, a reusable workflow that builds the plugin ZIP and records its SHA256, runs
`verifyPlugin` for each entry of the `verify-matrix` input, runs the Xvfb UI tests with a configurable timeout for the
test IDE, and requires all of them to pass. A release caller passes the tag as `plugin-version` and signs the ZIP from
the recorded digest.
