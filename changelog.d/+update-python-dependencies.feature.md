Add `update-python-dependencies.yaml`, a reusable workflow that bumps Python dependency floors, regenerates
`pylock.toml`, and opens one dependency pull request. Bumps wait out a seven-day cooldown by default, and `expedite`
lifts it for named packages in one run. With `kind: library`, the `fresh-groups` take their newest release at once, and
the other groups wait.
