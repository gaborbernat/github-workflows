Add `build-maturin-wheels.yaml`, a reusable workflow that builds a maturin extension's wheels and sdist from a JSON
build matrix and uploads them under the artifact names the caller's publisher expects. Wheels use the maturin version
from the caller's hash-checked `release-build` group, and the sdist uses its `build` group. Jobs hold read-only
permissions. The optional `pre-build-command` runs once before the source upload, and `post-build-command` runs in each
wheel job after maturin.
