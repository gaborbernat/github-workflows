Actions and the `check` workflow no longer fail with `unbound variable` on macOS runners when an input leaves an array
empty, such as the `targets` input of `install-locked-tools`. macOS runs `shell: bash` steps with Bash 3.2, which
rejects `"${array[@]}"` on an empty array under `set -u`.
