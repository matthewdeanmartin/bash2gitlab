#!/usr/bin/env bash
set -Eeuo pipefail

# Orchestrates:
#  1) Prettier (format) on changed files it supports
#  2) Bash dry run (bash -n) on changed shell scripts
#  3) ShellCheck on changed shell scripts
#  4) Yamllint on changed YAML files
#
# Respects the same env as changed-files.sh:
#   CHANGED_MODE, BASE, HEAD
#
# Tool detection:
#  - Prettier: uses `prettier` if found, else `npx --yes prettier`
#  - ShellCheck / yamllint: required if corresponding file types are present

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  echo "Not inside a git repository." >&2
  exit 1
fi
cd "${repo_root}"

# Get changed files as NUL-delimited list
mapfile -d '' -t CHANGED < <(OUTPUT0=1 ./scripts/changed-files.sh)

if [[ "${#CHANGED[@]}" -eq 0 ]]; then
  echo "No changed files detected. Nothing to do."
  exit 0
fi

# Helpers ----------------------------------------------------------------------

lower_ext() {
  local f="${1##*/}"
  # Extract extension and lowercase it
  local ext="${f##*.}"
  printf '%s' "${ext,,}"
}

has_shebang_shell() {
  # Returns success if file's shebang references a shell (sh|bash|zsh|dash|ash)
  local f="$1"
  # Avoid huge reads: just the first line
  local first
  first="$(head -n 1 -- "$f" 2>/dev/null || true)"
  if [[ "$first" == "#!"* ]] && echo "$first" | grep -Eqi '/(ba)?sh|/zsh|/dash|/ash'; then
    return 0
  fi
  return 1
}

# Buckets ----------------------------------------------------------------------

PRETTIER_FILES=()
BASH_FILES=()
YAML_FILES=()

# Prettier core-supported extensions (keep broad but sane)
# (Prettier will also obey .prettierignore)
declare -A PRETTIER_EXTS=(
  [js]=1 [jsx]=1 [ts]=1 [tsx]=1
  [json]=1 [jsonc]=1
  [yaml]=1 [yml]=1
  [md]=1 [mdx]=1
  [css]=1 [scss]=1 [less]=1
  [html]=1 [htm]=1
  [gql]=1 [graphql]=1
  [vue]=1 [svelte]=1
  [toml]=1
)

for f in "${CHANGED[@]}"; do
  # Skip non-regular files defensively
  [[ -f "$f" ]] || continue

  ext="$(lower_ext "$f")"

  # Prettier bucket
  if [[ -n "${PRETTIER_EXTS[$ext]:-}" ]]; then
    PRETTIER_FILES+=("$f")
  fi

  # YAML bucket
  if [[ "$ext" == "yaml" || "$ext" == "yml" ]]; then
    YAML_FILES+=("$f")
  fi

  # Shell bucket: *.sh files OR files with shell shebang
  if [[ "$ext" == "sh" ]] || has_shebang_shell "$f"; then
    BASH_FILES+=("$f")
  fi
done

# 1) Prettier ------------------------------------------------------------------

if [[ "${#PRETTIER_FILES[@]}" -gt 0 ]]; then
  if command -v prettier >/dev/null 2>&1; then
    prettier_cmd=(prettier)
  else
    # Uses local devDependency if available, otherwise fetches
    prettier_cmd=(npx --yes prettier)
  fi

  echo "▶ Running Prettier on ${#PRETTIER_FILES[@]} file(s)..."
  # Use --ignore-unknown for safety; batch args to avoid E2BIG
  printf '%s\0' "${PRETTIER_FILES[@]}" \
    | xargs -0 -r -n 50 "${prettier_cmd[@]}" --loglevel warn --ignore-unknown --write --
fi

# 2) Bash dry run (syntax check) ----------------------------------------------

if [[ "${#BASH_FILES[@]}" -gt 0 ]]; then
  echo "▶ Bash dry run (bash -n) on ${#BASH_FILES[@]} file(s)..."
  # Validate each shell script
  printf '%s\0' "${BASH_FILES[@]}" \
    | xargs -0 -r -n 1 bash -n --
fi

# 3) ShellCheck ----------------------------------------------------------------

if [[ "${#BASH_FILES[@]}" -gt 0 ]]; then
  if ! command -v shellcheck >/dev/null 2>&1; then
    echo "ShellCheck not found. Please install it (e.g., 'brew install shellcheck' or your distro package manager)." >&2
    exit 2
  fi
  echo "▶ ShellCheck on ${#BASH_FILES[@]} file(s)..."
  # -x follows sources; -S style for helpful suggestions
  printf '%s\0' "${BASH_FILES[@]}" \
    | xargs -0 -r shellcheck -x -S style --
fi

# 4) Yamllint ------------------------------------------------------------------

if [[ "${#YAML_FILES[@]}" -gt 0 ]]; then
  if ! command -v yamllint >/dev/null 2>&1; then
    echo "yamllint not found. Please install it (e.g., 'pipx install yamllint' or distro package)." >&2
    exit 3
  fi
  echo "▶ Yamllint on ${#YAML_FILES[@]} file(s)..."
  # -s: stricter, treats warnings as errors on bad YAML syntax
  printf '%s\0' "${YAML_FILES[@]}" \
    | xargs -0 -r -n 50 yamllint -s --
fi

echo "✓ Done."
