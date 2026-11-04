`publish-github-release` retries a GitHub API call that fails without a client error, up to three attempts with backoff.
When the publish call fails, the Action reads the release again and succeeds if GitHub already published it with the
expected assets and notes, so a lost response no longer fails a release that is live. Draft creation is not retried.
