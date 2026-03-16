# Load in each .bats via: load './test_helper.bash'

setup_tmpdir() {
  TMPDIR="$(mktemp -d)"
  OUTDIR="$TMPDIR/out"
  SRCDIR="$TMPDIR/src"
  mkdir -p "$OUTDIR" "$SRCDIR"
}

teardown_tmpdir() {
  [[ -n "$TMPDIR" && -d "$TMPDIR" ]] && rm -rf "$TMPDIR"
}

run_cli() {
  # Prefer installed entrypoint; fall back to python -m for repo checkouts
  if command -v bash2yaml >/dev/null 2>&1; then
    run bash2yaml "$@"
  else
    run python -m bash2yaml "$@"
  fi
}
