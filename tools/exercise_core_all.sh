#!/usr/bin/env bash
set -eou pipefail

main() {
  declare package_name="${1:-myapp}"
  declare cli_command="${2:-some-basic-command}"
  declare venv_core=".venv-core"
  declare uv_expected_venv=".venv"
  declare venv_backup=""
  declare wheel_file=""
  declare wheel_filename=""
  declare wheel_version=""

  echo "📦 Building sdist/wheel for ${package_name}..."
  uv build

  echo "🧼 Creating clean venv: ${venv_core}"
  rm -rf "${venv_core}"
  uv venv --seed --python 3.11 "${venv_core}"

  wheel_file="$(find dist -type f -name "${package_name}-*.whl" | head -n1)"
  if [[ -z "$wheel_file" ]]; then
    echo "❌ Could not find wheel for ${package_name} in dist/"
    exit 1
  fi

  wheel_filename="${wheel_file##*/}"
  wheel_version="${wheel_filename#${package_name}-}"
  wheel_version="${wheel_version%%-*}"

  # Backup existing .venv if it exists
  if [[ -e "${uv_expected_venv}" ]]; then
    venv_backup=".venv.bak.$(date +%s)"
    echo "🛡️  Backing up existing ${uv_expected_venv} to ${venv_backup}"
    mv "${uv_expected_venv}" "${venv_backup}"
  fi

  echo "🔗 Temporarily making ${venv_core} available as ${uv_expected_venv}"
  if [[ "$OSTYPE" =~ ^(msys|cygwin|win32) ]]; then
    cp -r "${venv_core}" "${uv_expected_venv}"
  else
    ln -s "${venv_core}" "${uv_expected_venv}"
  fi

#  echo "📥 Installing ${package_name} v${wheel_version}..."
#  uv run -- pip install "$wheel_file"

  echo "🚬 Smoke test: '${package_name} --help'"
  uv run -- "$package_name" --help

  echo "🚬 Smoke test: '${package_name} ${cli_command}'"
  uv run -- "$package_name" $cli_command

  echo "✅ All tests passed"

  echo "🧹 Cleaning up .venv..."
  if [[ -L "${uv_expected_venv}" ]]; then
    rm "${uv_expected_venv}"
  else
    rm -rf "${uv_expected_venv}"
  fi

  if [[ -n "$venv_backup" && -e "$venv_backup" ]]; then
    echo "🔁 Restoring original .venv from ${venv_backup}"
    mv "$venv_backup" "${uv_expected_venv}"
  fi
}

main "$@"
