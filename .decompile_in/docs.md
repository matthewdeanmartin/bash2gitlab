# GitLab CI Job Catalog

## `../../.decompile_in/.gitlab-ci.yml`

### Global Variables

| Name | Default Value | Description |
|---|---|---|
| `PACKAGE_DIR` | `bash2gitlab` | single module, no src |
| `PIP_DISABLE_PIP_VERSION_CHECK` | `1` | No need to check version if not interactive |
| `UV_CACHE_DIR` | `.uv` | common default |
| `UV_LINK_MODE` | `copy` | 'copy' is more docker friendly |
| `UV_PROJECT_ENVIRONMENT` | `.venv` | commonn default |

### Jobs

#### `bandit`

| Key | Value |
|---|---|
| Stage | `security` |
| Script lines | 1 |

#### `build_docs`

| Key | Value |
|---|---|
| Stage | `docs` |
| Artifacts | `docs/` |
| Script lines | 1 |

#### `build_package`

| Key | Value |
|---|---|
| Stage | `build` |
| Artifacts | `dist/` |
| Script lines | 2 |

#### `check_docs`

| Key | Value |
|---|---|
| Stage | `docs` |
| Script lines | 7 |

#### `lint`

| Key | Value |
|---|---|
| Stage | `test` |
| Script lines | 3 |

#### `mypy`

| Key | Value |
|---|---|
| Stage | `test` |
| Script lines | 1 |

#### `precommit`

| Key | Value |
|---|---|
| Stage | `test` |
| Script lines | 1 |

#### `publish_pypi`

| Key | Value |
|---|---|
| Stage | `release` |
| Needs | `build_package` |
| Script lines | 1 |
| Rules | when=`never`, 1 `if` |

#### `pytest`

| Key | Value |
|---|---|
| Stage | `test` |
| Needs | `lint` |
| Artifacts | `htmlcov/`, `coverage.xml` |
| Script lines | 2 |

---
