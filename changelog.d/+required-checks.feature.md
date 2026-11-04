Add `required-checks`, a composite action that fails unless every job in a `needs` context succeeded. Its
`allow-skipped` input names jobs that may end skipped. A gate calls it in place of an inline `jq` expression, and the
required check name stays with the caller.
