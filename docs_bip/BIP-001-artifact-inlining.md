# BIP 001 – Artifact Inlining

```
BIP: 001
Title: Inline Artifacts (Zipped Files and Folders) in GitLab CI YAML
Author: bash2gitlab maintainers
Status: Draft
Type: Feature
Created: 2026-02-28
```

## Abstract

This BIP proposes extending bash2gitlab's inlining capabilities to support **artifact inlining**: the ability to inline
entire directory trees as compressed, YAML-safe encoded strings at compile time, with automatic extraction at runtime.
This addresses the same pain point that bash2gitlab solves for scripts—keeping reusable artifacts in a central
repository while including them in distributed GitLab CI pipelines without relying on GitLab's `include:` mechanism or
external dependencies.

## Motivation

### Current Problem

bash2gitlab currently solves the problem of inlining scripts (Bash, Python, PowerShell, etc.) from a central repository
into GitLab CI YAML files. However, many CI/CD workflows require not just scripts, but entire **directory trees** of
supporting files:

- Configuration file collections (e.g., `.editorconfig`, `.pylintrc`, linting rules)
- Template directories (e.g., Terraform modules, Ansible playbooks)
- Static assets or tooling bundles
- Multi-file application scaffolds

Currently, users have three unsatisfactory options:

1. **Git submodules** – Requires runner permissions, complicates CI, and is error-prone
2. **Base image bundling** – Couples artifacts to a specific Docker image, limiting flexibility
3. **Remote pipeline triggers** – Adds complexity and latency
4. **Manual copying** – Defeats the purpose of centralized templates

### Why This Matters

Just as bash2gitlab lets users develop scripts with full IDE support and then inline them into YAML, **artifact inlining
** would let users:

- Maintain artifact directories in a central repository with version control
- Develop and test artifacts locally with full tooling support
- Compile artifacts into self-contained YAML at build time
- Have GitLab runners automatically extract artifacts at runtime without external dependencies

This is a **compile-time inline + runtime extract** pattern, identical in spirit to how bash2gitlab currently handles
scripts.

## Specification

### 1. Pragma Syntax

Artifact inlining uses the **Pragma** comment syntax, consistent with existing bash2gitlab pragmas. The pragma must be a **quoted string** in YAML to be properly parsed as a list item:

```yaml
build-job:
  before_script:
    - "# Pragma: inline-artifact ./config-bundle --output=/tmp/config --format=zip"
```

**Syntax:**

```
- "# Pragma: inline-artifact <source_path> [--output=<extract_path>] [--format=<compression>] [--strip=<N>]"
```

**Why the quoted string format?**
- The `-` makes it a valid YAML list item
- The `"` quotes ensure YAML parses it as a string (not a comment)
- The `#` inside the string makes it a valid Bash comment when extracted
- This format ensures the source YAML is both valid GitLab CI YAML *and* will be treated as a Bash comment when executed

**Parameters:**

- `<source_path>` (required): Path to directory or file to inline (relative to input_dir)
- `--output=<path>` (optional): Where to extract at runtime (default: `./<dirname>`)
- `--format=<fmt>` (optional): Compression format (default: `zip`, options: `zip`, `tar.gz`, `tar.bz2`, `tar.xz`)
- `--strip=<N>` (optional): Strip N leading path components during extraction (default: 0)

**Notes:**
- Base64 encoding is **always** used (no option to disable)
- File permissions are **not** preserved (simplicity over features)
- Both single files and directories are supported; both are compressed into zip format

### 2. Compile-Time Behavior

When `bash2gitlab compile` processes a YAML file containing `# Pragma: inline-artifact`:

1. **Read source directory/file** from `<source_path>` (relative to `input_dir`)
2. **Compress** using specified format (default: zip)
3. **Encode** as base64 (YAML-safe, always enabled)
4. **Generate extraction shim** – A small Bash script that:
    - Decodes the base64 string
    - Extracts to the target path
    - Does NOT preserve file permissions
5. **Inline into YAML** – Replace the pragma with:
   ```yaml
   - |
     # >>> BEGIN inline-artifact: ./config-bundle (zip, 1.2KB compressed)
     __B2G_ARTIFACT='<base64-encoded-zip-data>'
     mkdir -p /tmp/config
     echo "$__B2G_ARTIFACT" | base64 -d | unzip -q -d /tmp/config -
     unset __B2G_ARTIFACT
     # <<< END inline-artifact
   ```

### 3. Runtime Behavior

At GitLab CI runtime, the inlined script:

1. Decodes the base64 artifact string
2. Pipes to the appropriate decompression tool (`unzip`, `tar`, etc.)
3. Extracts to the specified output directory
4. Cleans up the encoded variable

This happens **transparently** as part of the `before_script`, `script`, or `after_script` block.

### 4. Compression Format Support

| Format    | Tool Required  | Pros                          | Cons                  |
|-----------|----------------|-------------------------------|-----------------------|
| `zip`     | `unzip`        | Universal, Windows-compatible | Slightly larger       |
| `tar.gz`  | `tar`, `gzip`  | Ubiquitous on Linux           | Not native on Windows |
| `tar.bz2` | `tar`, `bzip2` | Better compression            | Slower                |
| `tar.xz`  | `tar`, `xz`    | Best compression              | Requires `xz-utils`   |

**Default:** `zip` for maximum compatibility.

### 5. Size Limits and Safety

- **Warning threshold:** 100 KB (compressed)
- **Hard limit (default):** 1 MB (compressed) – Configurable via `BASH2GITLAB_MAX_ARTIFACT_SIZE`
- **Rationale:**
    - Base64 encoding increases size by ~33%
    - YAML spec has no size limit, but readability and Git performance degrade
    - Large artifacts should use GitLab's native artifact system

### 6. Security Considerations

- **Path traversal protection:** Source paths must be within `input_dir` (existing bash2gitlab behavior)
- **Extraction safety:** Shim uses safe extraction flags to prevent zip bombs and path traversal
    - `unzip -q -d <dir> -` (safe: extracts to specific dir only)
    - `tar --no-same-owner -C <dir>` (safe: prevents ownership issues)
- **Pragma support:** Honor `# Pragma: do-not-inline` to skip artifact inlining

### 7. Configuration Options

**In `.bash2gitlab.toml`:**

```toml
[compile]
max_artifact_size_mb = 1  # Max compressed size before error
artifact_warn_size_kb = 100  # Warn threshold
default_artifact_format = "zip"  # Default compression
artifact_checksum_validation = false  # Add checksum check to shim (future)
```

**Environment Variables:**

- `BASH2GITLAB_MAX_ARTIFACT_SIZE` – Max size in bytes
- `BASH2GITLAB_ARTIFACT_FORMAT` – Default format

### 8. Decompile Behavior

When running `bash2gitlab decompile`:

- **Detect inlined artifacts** by looking for `# >>> BEGIN inline-artifact` markers
- **Extract base64 payload** and decode
- **Write to output directory** as `<name>.artifact.zip` (or appropriate extension)
- **Replace YAML block** with original pragma:
  ```yaml
  - "# Pragma: inline-artifact ./config-bundle --output=/tmp/config --format=zip"
  ```

### 9. Example Workflow

**Source YAML (`src/.gitlab-ci.yml`):**

```yaml
lint:
  image: python:3.11
  before_script:
    - "# Pragma: inline-artifact ./shared-configs --output=./configs --format=zip"
  script:
    - pylint --rcfile=./configs/.pylintrc myproject/
```

**Directory structure:**

```
src/
  .gitlab-ci.yml
  shared-configs/
    .pylintrc
    .editorconfig
    mypy.ini
```

**Compiled YAML (`dist/.gitlab-ci.yml`):**

```yaml
lint:
  image: python:3.11
  before_script:
    - |
      # >>> BEGIN inline-artifact: ./shared-configs (zip, 847 bytes)
      __B2G_ARTIFACT='UEsDBAoAAAAAAKJj2VgAAAAAAAAAAAAAAAAOABwAc2hhcmVkLWNvbmZpZ3MvVVQJAANIp...'
      mkdir -p ./configs
      echo "$__B2G_ARTIFACT" | base64 -d | unzip -q -d ./configs -
      unset __B2G_ARTIFACT
      # <<< END inline-artifact
  script:
    - pylint --rcfile=./configs/.pylintrc myproject/
```

## Backwards Compatibility

- **Fully backwards compatible** – Existing YAML without `# Pragma: inline-artifact` is unaffected
- No changes to existing script inlining behavior
- Pragma syntax ensures raw YAML is valid GitLab CI (as a comment list item) AND valid Bash (as a comment)

## Implementation Plan

### Phase 1: Core Implementation

1. Add `compile_artifacts.py` module (parallel to `compile_not_bash.py`)
2. Implement artifact detection via meta-command regex
3. Add compression/encoding logic (zip format only)
4. Generate extraction shim
5. Integrate into `compile_all.py` processing pipeline

### Phase 2: Format Support

1. Add `tar.gz` support
2. Add `tar.bz2` and `tar.xz` support
3. Add format auto-detection based on source file extension

### Phase 3: Decompile Support

1. Detect inlined artifacts in compiled YAML
2. Extract and decode payloads
3. Reconstruct meta-command syntax
4. Write extracted artifacts to output directory

### Phase 4: Polish

1. Add checksum validation option
2. Improve error messages
3. Add size warnings and progress indicators
4. Update documentation and examples
5. Add `doctor` command checks for common issues

## Testing Strategy

### Unit Tests

- Compression/decompression round-trip
- Base64 encoding/decoding
- Meta-command parsing
- Path validation and security checks
- Size limit enforcement

### Integration Tests

- Compile YAML with inlined artifacts
- Decompile and verify reconstruction
- Test all compression formats
- Test edge cases (empty dirs, symlinks, large files)

### CI/CD Tests

- Run compiled YAML in GitLab CI (if possible)
- Verify extraction works on different runner images
- Test with Alpine, Ubuntu, and Windows runners

## Alternatives Considered

### 1. **Use GitLab's Native Artifacts**

- **Rejected:** Requires separate jobs and pipeline complexity; defeats purpose of self-contained templates

### 2. **Git Submodules**

- **Rejected:** Already a poor user experience; bash2gitlab aims to eliminate this

### 3. **Inline as Plain Text (No Compression)**

- **Rejected:** Would bloat YAML files excessively; compression is essential

### 4. **Use `!include` Extension**

- **Rejected:** Not standard GitLab YAML; would break compatibility

## Open Questions

1. **Should we support single-file inlining, or only directories?**
    - **Decision: Support both** – Single files and directories; both get zipped

2. **How do we handle binary files in artifacts?**
    - **Decision: Compress and base64 encode** – Extraction handles binary automatically

3. **Should we support custom extraction commands?**
    - **Decision: Not in v1** – Keep simple and safe; standard tools only

4. **How do we handle symlinks?**
    - **Open:** Follow symlinks by default? Skip them? Error on symlinks? Add `--no-follow-symlinks` option?

5. **Should we support filtering (e.g., exclude `*.pyc` files)?**
    - **Open:** Not in v1; users can prepare clean source directories. Future: `.artifactignore` file?

6. **Should the extraction shim validate checksums?**
    - **Open:** Could add SHA256 validation to detect corruption. Performance vs. safety tradeoff.

7. **What happens if `unzip` or `tar` is not available on the runner?**
    - **Open:** Fail with clear error? Bundle a pure-Bash unzip implementation? Document minimum runner requirements?

8. **Should we support nested artifact inlining (artifacts containing artifacts)?**
    - **Open:** Probably not in v1. Could cause exponential bloat.

9. **How do we handle very large base64 strings in YAML?**
    - **Open:** Split across multiple YAML lines? Use folded scalars? Current plan: literal scalar block.

10. **Should we support `.zip` files as source (pass-through without re-compression)?**
    - **Open:** Could optimize by detecting pre-compressed archives and inlining directly.

11. **What happens if `--output` path conflicts with existing files at runtime?**
    - **Open:** Overwrite silently? Error? Add `--no-clobber` option? Default: overwrite (unzip default behavior).

12. **Should we add a `--dry-extract` option to test extraction without actually writing files?**
    - **Open:** Could be useful for debugging, but adds complexity.

13. **How do we handle empty directories?**
    - **Open:** Zip format doesn't always preserve empty dirs. Use `.gitkeep`-style approach?

14. **Should pragmas support multi-line syntax for readability?**
    - **Open:** Current: single line. Future: multi-line with `\` continuation?

15. **Should we track inlined artifact metadata in `.hash` files for drift detection?**
    - **Open:** Would allow `detect-drift` to catch manual artifact extraction. Useful or overkill?

## References

- PEP 1 – PEP Purpose and Guidelines (Python Enhancement Proposals)
- bash2gitlab existing script inlining: `compile_not_bash.py`
- bash2gitlab source inlining: `compile_bash_reader.py`
- GitLab CI YAML reference: https://docs.gitlab.com/ee/ci/yaml/

## Copyright

This document is placed in the public domain or under the CC0-1.0 license, whichever is more permissive.
