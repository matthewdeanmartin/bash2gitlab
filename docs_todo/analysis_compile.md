# Bash2GitLab Analysis and Design Document

## Executive Summary

Bash2GitLab is a sophisticated Python tool designed to solve a critical limitation in GitLab CI/CD pipelines: the
inability to reference external script files directly in pipeline definitions. The tool automatically inlines shell
scripts and other interpreter-based scripts directly into GitLab CI YAML files, creating self-contained pipeline
definitions that can be executed in any GitLab runner environment.

## Problem Statement

GitLab CI/CD pipelines are defined using YAML files that specify jobs, scripts, and execution environments. However,
these pipelines cannot directly reference external script files from the repository, forcing developers to either:

1. Embed all script logic directly in YAML (reducing maintainability)
2. Use complex workarounds with artifacts or include mechanisms
3. Maintain duplicate script logic across multiple files

This tool addresses these limitations by automatically inlining script content while preserving the original source
structure for development.

## Architecture Overview

### Core Components

#### 1. Main Compilation Engine (`compile_all.py`)

- **Purpose**: Orchestrates the entire compilation process
- **Key Functions**:
    - `run_compile_all()`: Main entry point for batch processing
    - `inline_gitlab_scripts()`: Core YAML processing and script inlining
    - `process_script_list()`: Handles individual script blocks with YAML feature preservation
    - `write_compiled_file()`: Safe file writing with collision detection

#### 2. Bash Script Reader (`compile_bash_reader.py`)

- **Purpose**: Recursively processes bash scripts and handles `source` commands
- **Key Features**:
    - Recursive script inlining with cycle detection
    - Security controls to prevent directory traversal attacks
    - Pragma-based control system for selective inlining
    - Shebang handling and content normalization

#### 3. Multi-Language Support (`compile_not_bash.py`)

- **Purpose**: Extends inlining support beyond bash to other interpreters
- **Supported Languages**: Python, Node.js, Ruby, PHP, Fish, PowerShell, Perl, Lua, Elixir, and more
- **Key Features**:
    - Pattern matching for interpreter invocations
    - Module resolution (e.g., `python -m package.module`)
    - Safety limits for payload size

### Data Flow Architecture

```
Input YAML Files → YAML Parser → Script Detection → Multi-Language Inliner → YAML Reconstruction → Output Files
     ↓                ↓              ↓                    ↓                      ↓                ↓
Uncompiled/       ruamel.yaml    Pattern Match     bash2gitlab readers    Preserve YAML      Compiled/
 ├── .yml          Parsing       Script blocks      ├── Bash scripts      Features          ├── .yml
 ├── scripts/                    (script:,          ├── Python modules    (tags, anchors,   ├── .hash
 └── variables.sh                before_script:,    └── Other interpreters comments)         └── ...
```

## Key Design Patterns

### 1. YAML Feature Preservation

The tool uses `ruamel.yaml` to maintain YAML semantics including:

- **Tags** (e.g., `!reference`)
- **Anchors and aliases**
- **Comments and formatting**
- **Sequence types** (`CommentedSeq` vs plain lists)

```python
def rebuild_seq_like(
        processed: list[Any],
        was_commented_seq: bool,
        original_seq: CommentedSeq | None,
) -> list[Any] | CommentedSeq:
    """Rebuild a sequence preserving ruamel type when appropriate."""
```

### 2. Safety-First File Handling

Implements a sophisticated collision detection system:

- **Hash-based tracking**: Maintains `.hash` files to detect manual edits
- **Diff generation**: Provides detailed diffs when conflicts occur
- **Graceful failure**: Refuses to overwrite manually edited files

### 3. Pragma-Driven Control

Bash scripts can control inlining behavior through embedded comments:

- `# Pragma: do-not-inline`: Skip current line
- `# Pragma: start-do-not-inline` / `# Pragma: end-do-not-inline`: Block regions
- `# Pragma: allow-outside-root`: Bypass security restrictions

### 4. Security-Conscious Path Resolution

```python
def secure_join(base_dir: Path, user_path: str, allowed_root: Path) -> Path:
    """Resolve paths while preventing directory traversal attacks."""
```

## Technical Implementation Details

### Type Safety and Modern Python

The codebase extensively uses Python type hints throughout:

```python
def process_script_list(
        script_list: list[TaggedScalar | str] | CommentedSeq | str,
        scripts_root: Path,
) -> list[Any] | CommentedSeq | LiteralScalarString:
```

### Parallel Processing Support

For large repositories, the tool supports parallel compilation:

```python
if total_files >= 5 and max_workers > 1 and parallelism:
    with multiprocessing.Pool(processes=max_workers) as pool:
        results = pool.starmap(compile_single_file, args_list)
```

### Smart Content Collapsing

The tool intelligently decides when to collapse script sequences into literal blocks:

```python
def compact_runs_to_literal(items: list[Any], *, min_lines: int = 2) -> list[Any]:
    """Merge consecutive plain strings into a single LiteralScalarString."""
```

## Configuration and Extensibility

### Environment Variables

- `BASH2GITLAB_SKIP_ROOT_CHECKS`: Disable path security checks
- `BASH2GITLAB_MAX_INLINE_LEN`: Control maximum inline payload size
- `BASH2GITLAB_ALLOW_ANY_EXT`: Allow inlining regardless of file extension

### Plugin System Integration

The code references a plugin manager (`get_pm()`) suggesting extensibility through hooks:

```python
pm = get_pm()
script_path_str = pm.hook.extract_script_path(line=item) or None
```

## Security Considerations

### Path Traversal Prevention

- Resolves all paths against an allowed root directory
- Validates that resolved paths don't escape the project boundary
- Provides override mechanisms for legitimate use cases

### Content Validation

- File size limits to prevent resource exhaustion
- Extension validation for interpreter matching
- UTF-8 BOM and shebang handling

## Error Handling Strategy

### Graceful Degradation

- When scripts cannot be inlined, preserves original commands with warnings
- Continues processing other files even if individual files fail
- Provides detailed error messages with file paths and line numbers

### Validation and Feedback

- YAML syntax validation before and after processing
- Diff generation for changed content
- Comprehensive logging at multiple levels

## Performance Optimizations

### Intelligent Processing

- Skips files that haven't changed (hash comparison)
- Only processes known script-like keys in YAML
- Parallel processing for large repositories

### Memory Management

- Streaming YAML processing where possible
- Controlled recursion depth for script inlining
- Payload size limits to prevent memory exhaustion

## Integration Patterns

### GitLab CI Integration

The tool is designed to fit into GitLab CI/CD workflows:

- Processes entire directories of YAML templates
- Maintains separate compiled output directory
- Supports variable injection from shell files
- Preserves GitLab-specific YAML features

### Development Workflow

- Source files remain in `uncompiled/` directory
- Compiled files go to output directory
- Hash files track compilation state
- Dry-run mode for testing changes

## Quality Assurance Features

### Content Verification

- YAML syntax validation
- Hash-based change detection
- Manual edit prevention
- Comprehensive diff reporting

### Development Support

- Extensive debug logging
- Clear error messages with context
- Dry-run capabilities
- Parallel execution support

