


#!/usr/bin/env bash
set -Eeuo pipefail

# Prints the repository-relative list of changed files.
# Default mode: "working" (union of unstaged, staged, and untracked).
# MODE=commit will diff commit range BASE...HEAD, picking a sane BASE if not provided.
#
# Env:
#   CHANGED_MODE   working|commit   (default: working; CI defaults to commit)
#   BASE           base ref for MODE=commit (e.g., origin/main). Optional.
#   HEAD           head ref (default: HEAD).
#   OUTPUT0        if set (non-empty), output NUL-delimited (print0)
#
# Exit non-zero if not in a git repo.

CHANGED_MODE="${CHANGED_MODE:-working}"
HEAD="${HEAD:-HEAD}"
OUTPUT0="${OUTPUT0:-}"

# In CI, default to commit mode unless explicitly overridden.
if [[ -n "${CI:-}" && "${CHANGED_MODE}" == "working" ]]; then
  CHANGED_MODE="commit"
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
cd "${repo_root}"

choose_base() {
  # If BASE is provided, use it.
  if [[ -n "${BASE:-}" ]]; then
    echo "${BASE}"
    return 0
  fi

  # Try origin/HEAD -> resolves to origin/main or origin/master
  if base_ref="$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || true)"; then
    # symbolic-ref returns something like "origin/main"
    if [[ -n "${base_ref}" ]]; then
      echo "${base_ref}"
      return 0
    fi
  fi

  # Fallbacks
  for candidate in origin/main origin/master main master; do
    if git rev-parse -q --verify "${candidate}^{commit}" >/dev/null 2>&1; then
      echo "${candidate}"
      return 0
    fi
  done

  # Last resort: previous commit
  echo "HEAD~1"
}

gather_working_changes() {
  # Unstaged, staged, and untracked (NUL-delimited)
  git diff --name-only -z                       || true
  git diff --name-only --cached -z              || true
  git ls-files --others --exclude-standard -z   || true
}

gather_commit_changes() {
  local base_ref basepoint
  base_ref="$(choose_base)"
  # Use merge-base so we diff from the common ancestor to HEAD
  if basepoint="$(git merge-base "${base_ref}" "${HEAD}" 2>/dev/null)"; then
    git diff --name-only -z --diff-filter=ACMRTUXB "${basepoint}...${HEAD}" || true
  else
    # As a fallback, diff directly from base_ref
    git diff --name-only -z --diff-filter=ACMRTUXB "${base_ref}...${HEAD}" || true
  fi
}

# Collect, de-dup, and filter to existing regular files.
declare -A seen
files=()

if [[ "${CHANGED_MODE}" == "commit" ]]; then
  src_stream="$(gather_commit_changes)"
else
  src_stream="$(gather_working_changes)"
fi

# Read NUL-delimited list from embedded command substitution safely:
# shellcheck disable=SC2034
while IFS= read -r -d '' f; do
  # Skip non-files (deleted, directories, etc.)
  if [[ -f "$f" && -z "${seen["$f"]+x}" ]]; then
    seen["$f"]=1
    files+=("$f")
  fi
done < <(printf "%s" "$src_stream")

if [[ -n "${OUTPUT0}" ]]; then
  # NUL-delimited
  printf "%s\0" "${files[@]}" || true
else
  # Newline-delimited
  printf "%s\n" "${files[@]}" || true
fi
