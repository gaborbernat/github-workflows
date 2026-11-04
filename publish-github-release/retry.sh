#!/usr/bin/env bash

retry() {
  local attempt
  for attempt in {1..6}; do
    if "$@"; then return 0; fi
    if ((attempt == 6)); then return 1; fi
    echo "Attempt $attempt of 6 failed, retrying in 2s"
    sleep 2
  done
}

# Retries a gh api call unless GitHub answered with a 4xx, which repeats itself. gh prints a non-JSON 5xx body as a
# parse error without the status, so the 4xx marker is the reliable test.
gh_api() {
  local attempt errors="$RUNNER_TEMP/gh-api-error.txt"
  for attempt in 1 2 3; do
    if gh api "$@" 2>"$errors"; then return 0; fi
    cat "$errors" >&2
    if ((attempt == 3)) || grep -q 'HTTP 4[0-9][0-9]' "$errors"; then return 1; fi
    echo "GitHub API call failed without a client error, attempt $attempt of 3, retrying in $((attempt * 5))s"
    sleep $((attempt * 5))
  done
}
