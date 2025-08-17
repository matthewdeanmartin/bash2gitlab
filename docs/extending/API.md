# Module bash2gitlab

## Sub-modules

- bash2gitlab.compile_all
- bash2gitlab.logging_config
- bash2gitlab.decompile_all

## Functions

`process_uncompiled_directory(uncompiled_path: Path, output_path: Path, scripts_path: Path, templates_dir: Path, output_templates_dir: Path, dry_run: bool = False) ‑> int`
: Main function to process a directory of uncompiled GitLab CI files.

```text
Args:
    uncompiled_path (Path): Path to the input .gitlab-ci.yml, other yaml and bash files.
    output_path (Path): Path to write the .gitlab-ci.yml file and other yaml.
    scripts_path (Path): Optionally put all bash files into a script folder.
    templates_dir (Path): Optionally put all yaml files into a template folder.
    dry_run (bool): If True, simulate the process without writing any files.

Returns:
    - The total number of jobs processed.
```

`decompile_gitlab_ci(input_yaml_path: Path, output_yaml_path: Path, scripts_output_path: Path, dry_run: bool = False) ‑> tuple[int, int]`
: Loads a GitLab CI YAML file, decompiles all script blocks into separate .sh files,
and saves the modified YAML.

```text
Args:
    input_yaml_path (Path): Path to the input .gitlab-ci.yml file.
    output_yaml_path (Path): Path to write the modified .gitlab-ci.yml file.
    scripts_output_path (Path): Directory to store the generated .sh files.
    dry_run (bool): If True, simulate the process without writing any files.

Returns:
    A tuple containing:
    - The total number of jobs processed.
    - The total number of script files created.
```
