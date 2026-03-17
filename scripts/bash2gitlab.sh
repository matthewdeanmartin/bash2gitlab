#!/usr/bin/env bash
set -euo pipefail

# Constants
readonly B2G_IMAGE_NAME="docker.io/matthewdeanmartin/bash2gitlab"
readonly B2G_VERSION="0.9.1"
readonly B2G_IMAGE="${B2G_IMAGE_NAME}:${B2G_VERSION}"

# @desc Build the container image if not present
# @noargs
docker_b2g::build_image() {
  if ! docker image inspect "${B2G_IMAGE}" >/dev/null 2>&1; then
    docker build --build-arg "B2G_VERSION=${B2G_VERSION}" -t "${B2G_IMAGE}" .
  fi
}

# @desc Run the container with current dir mounted and env configured
# @args Any arguments passed to the container
docker_b2g::run_container() {
  docker run --rm -it \
    --user "$(id -u):$(id -g)" \
    -v "${PWD}:/work" \
    -w /work \
    -e HOME=/tmp \
    "${B2G_IMAGE}" "$@"
}

main() {
  # docker_b2g::build_image
  docker_b2g::run_container "$@"
}

main "$@"
