# syntax=docker/dockerfile:1
FROM python:3.13-slim

# ---- Build-time pin (override with --build-arg) ----
ARG B2G_VERSION=0.9.8

# ---- Helpful envs ----
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:${PATH}"

# ---- OS deps ----
# - bash: some commands expect /bin/bash
# - git: useful for commands that pull templates/repos
# - graphviz: enables graph output from the tool’s graph features
# - tini: clean PID 1 signal handling in containers
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash git graphviz ca-certificates tini; \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
# Installs the CLI with the [all] extra
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install "bash2gitlab[all]==${B2G_VERSION}"

# Workspace; the wrapper sets -w /work and mounts PWD here
WORKDIR /work

# OCI labels (pulled from the PyPI page)
# title/description/license/version/url/source/docs
LABEL org.opencontainers.image.title="bash2gitlab" \
      org.opencontainers.image.description="Compile bash to GitLab pipeline YAML." \
      org.opencontainers.image.version="${B2G_VERSION}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.url="https://pypi.org/project/bash2gitlab/" \
      org.opencontainers.image.source="https://github.com/matthewdeanmartin/bash2gitlab" \
      org.opencontainers.image.documentation="https://bash2gitlab.readthedocs.io"

# Use tini for proper signal handling; default to the CLI
ENTRYPOINT ["/usr/bin/tini","--","bash2gitlab"]
CMD ["--help"]
