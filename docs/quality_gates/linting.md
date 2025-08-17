# Linting

[shellcheck](https://github.com/koalaman/shellcheck) will lint bash and find possible bugs or risky code.

It wants a shebang or a special comment to indicate what shell is active.

```bash
#!/bin/bash
```

bash2gitlab strips off the shebang.

It might not resolve the location of you script with 
the same base folder you're using, so you can specify where
to find it. This allows it to look at sourced files.

```bash
# shellcheck source=src/util.sh
. "util.sh"
```

## Yamllint
[yamllint](https://pypi.org/project/yamllint/) is a python tool.

You should lint your input yaml, not the output yaml.