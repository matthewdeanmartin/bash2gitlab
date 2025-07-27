# Configuration

Precedence rules:

1. CLI Switches
2. Env Vars
3. TOML file

## Toml based

pyproject.toml example
```toml
[tool.bash2gitlab]
input_file = "my_ci.yml"
scripts_out = "shredded_scripts/"
dry_run = false
```

bash2gitlab.toml example
```
input_dir = "/path/from/toml"
output_dir = "output/toml"
verbose = false
```

## Environment Variable Based

Prefix any switch with BASH2GITLAB
```bash
export BASH2GITLAB_OUTPUT_FILE=out.yml
export BASH2GITLAB_QUIET=1
```