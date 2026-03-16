### 🚨 Critical Bugs & Crashes

**1. `tomllib` Parsing Crash (`utils/toml_reader.py`)**
If a user is on Python 3.11+ and doesn't have `rtoml` installed, your fallback `tomllib` backend will violently crash when attempting to parse a string.

```python
if BACKEND == "tomllib":
    return LOADER.loads(s.encode("utf-8"))  # type: ignore[attr-defined]

```

**The Bug:** Python's native `tomllib.loads()` explicitly takes a `str`, not `bytes`. Passing `.encode("utf-8")` will throw a `TypeError: expected str, got bytes`.

**2. Windows Path Logic Failure (`commands/compile_all.py`)**
In `process_script_list`, you check if a script path is relative:

```python
if script_path_str.strip().startswith("./") or script_path_str.strip().startswith("\\."):
    rel_path = script_path_str.strip()[2:]

```

**The Bug:** `\\.` checks for a backslash followed by a dot (e.g., `\.script.sh`). Standard Windows relative paths are a dot followed by a backslash (`.\script.ps1`). It should be `startswith(".\\")`.

**3. Hardcoded Windows Git Bash Path (`commands/best_effort_runner.py`)**

```python
if os.name == "nt":
    bash = [r"C:\Program Files\Git\bin\bash.exe"]

```

**The Bug:** If a user installed Git Bash to a custom drive, or used a package manager like Scoop/Winget (which puts it in `~/scoop/apps/git/...`), this completely crashes the runner. You should use `shutil.which("bash")` to find it safely.

**4. Misrouted Configuration Fallback (`__main__.py`)**
In the CLI argument merging block for the `decompile` command (around line 663):

```python
args.input_file = args_input_file or config.decompile_input_file
args.input_folder = args_input_folder or config.input_dir

```

**The Bug:** `args.input_folder` correctly falls back to `config`... but it falls back to the *global* `config.input_dir` instead of `config.decompile_input_folder`! The `decompile` specific folder setting is completely ignored.

**5. `best_effort_runner.py` Self-Execution Crash**

```python
def run() -> None:
    print(sys.argv)
    config = str(sys.argv[-1:][0])
    best_efforts_run(Path(config))

```

**The Bug:** If this file is executed directly with no arguments (`python best_effort_runner.py`), `sys.argv[-1:][0]` resolves to `"best_effort_runner.py"`. It will attempt to parse its own Python source code as a GitLab CI YAML file and crash.

---

### 🔍 Logical Inconsistencies

**2. Shared `User-Agent` Identity Crisis (`utils/urllib3_helper.py`)**
You set up a global singleton HTTP pool in `get_http_pool()` and hardcode the header:
`"User-Agent": "bash2gitlab-update-checker/2"`
This exact pool is reused in `commands/copy2local.py` to download repository ZIP archives. This means your tool requests source code from GitHub/GitLab while introducing itself as an "update checker".

**3. GUI/TUI Process Spawning (`gui.py` & `tui.py`)**
Both UI wrappers use `subprocess.Popen(["bash2gitlab", ...])` to run commands.
If the tool is run from source, or within an unactivated virtual environment via `python -m bash2gitlab.gui`, the OS won't find `bash2gitlab` in the system `PATH` and will throw a `FileNotFoundError`.
*Fix:* Use `[sys.executable, "-m", "bash2gitlab", ...]` to guarantee it leverages the current Python context.

**4. Artifact Pragma Parsing Gotcha (`commands/compile_artifacts.py`)**
The `ARTIFACT_PRAGMA_REGEX` is designed to look for: `^\s*-?\s*\#\s*Pragma: inline-artifact`.
Because `ruamel.yaml` parses standard `#` comments as *comment nodes* (not strings), this regex will completely miss standard YAML comments. For this to actually trigger, the user is forced to wrap the pragma in quotes in their YAML: ` - "# Pragma: inline-artifact ..."`. This is a massive UX gotcha.

(This is only a bug if we can think of a way that we could inline w/o a -, can you think of one?)
