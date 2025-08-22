"""
Super limited local pipeline runner.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union

from ruamel.yaml import YAML

BASE_ENV = os.environ.copy()


def merge_env(env=None):
    """
    Merge os.environ and an env dict into a new dict.
    Values from env override os.environ on conflict.

    Args:
        env: Optional dict of environment variables.

    Returns:
        A merged dict suitable for subprocess calls.
    """
    if env:
        return {**BASE_ENV, **env}
    return BASE_ENV


# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"

# Disable colors if NO_COLOR is set
if os.getenv("NO_COLOR"):
    GREEN = RED = RESET = ""


def run_colored(script: str, env=None, cwd=None) -> int:
    env = merge_env(env)

    # Disable colors if NO_COLOR is set
    if os.getenv("NO_COLOR"):
        g, r, reset = "", "", ""
    else:
        g, r, reset = GREEN, RED, RESET
    if os.name == "nt":
        bash = r"C:\Program Files\Git\bin\bash.exe"
    else:
        bash = "bash"
    process = subprocess.Popen(  # nosec
        # , "-l"  # -l loads .bashrc and make it really, really slow.
        [bash],  # bash reads script from stdin
        env=env,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,  # to prevent \r
        bufsize=1,  # line-buffered
    )

    def stream(pipe, color, target):
        for line in iter(pipe.readline, ""):  # text mode here, so sentinel is ""
            if not line:
                break
            target.write(f"{color}{line}{reset}")
            target.flush()
        pipe.close()

    # Start threads to stream stdout and stderr in parallel
    threads = [
        threading.Thread(target=stream, args=(process.stdout, g, sys.stdout)),
        threading.Thread(target=stream, args=(process.stderr, r, sys.stderr)),
    ]
    for t in threads:
        t.start()

    # Feed the script and close stdin

    if os.name == "nt":
        script = script.replace("\r\n", "\n")

    if process.stdin:
        process.stdin.write(script)
        process.stdin.close()

    # Wait for process to finish
    process.wait()
    for t in threads:
        t.join()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, script)

    return process.returncode


@dataclass
class JobConfig:
    """Configuration for a single job."""

    name: str
    stage: str = "test"
    script: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    before_script: list[str] = field(default_factory=list)
    after_script: list[str] = field(default_factory=list)


@dataclass
class DefaultConfig:
    """Default configuration that can be inherited by jobs."""

    before_script: list[str] = field(default_factory=list)
    after_script: list[str] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""

    stages: list[str] = field(default_factory=lambda: ["test"])
    variables: dict[str, str] = field(default_factory=dict)
    default: DefaultConfig = field(default_factory=DefaultConfig)
    jobs: list[JobConfig] = field(default_factory=list)


class GitLabCIError(Exception):
    """Base exception for GitLab CI runner errors."""


class JobExecutionError(GitLabCIError):
    """Raised when a job fails to execute successfully."""


class ConfigurationLoader:
    """Loads and processes GitLab CI configuration files."""

    def __init__(self, base_path: Path | None = None):
        if not base_path:
            self.base_path = Path.cwd()
        else:
            self.base_path = base_path
        self.yaml = YAML(typ="safe")

    def load_config(self, config_path: Path | None = None) -> dict[str, Any]:
        """Load the main configuration file and process includes."""
        if config_path is None:
            config_path = self.base_path / ".gitlab-ci.yml"

        if not config_path.exists():
            raise GitLabCIError(f"Configuration file not found: {config_path}")

        config = self._load_yaml_file(config_path)
        config = self._process_includes(config, config_path.parent)

        return config

    def _load_yaml_file(self, file_path: Path) -> dict[str, Any]:
        """Load a single YAML file."""
        try:
            with open(file_path) as f:
                return self.yaml.load(f) or {}
        except Exception as e:
            raise GitLabCIError(f"Failed to load YAML file {file_path}: {e}") from e

    def _process_includes(self, config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
        """Process include directives for local files only."""
        includes = config.pop("include", [])
        if not includes:
            return config

        if isinstance(includes, (str, dict)):
            includes = [includes]

        for include_item in includes:
            if isinstance(include_item, str):
                # Simple local file include
                include_path = base_dir / include_item
                included_config = self._load_yaml_file(include_path)
                config = self._merge_configs(config, included_config)
            elif isinstance(include_item, dict) and "local" in include_item:
                # Local file with explicit local key
                include_path = base_dir / include_item["local"]
                included_config = self._load_yaml_file(include_path)
                config = self._merge_configs(config, included_config)

        return config

    def _merge_configs(self, base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        """Merge two configuration dictionaries."""
        result = base.copy()
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result


class PipelineProcessor:
    """Processes raw configuration into structured pipeline configuration."""

    RESERVED_KEYWORDS = {
        "stages",
        "variables",
        "default",
        "include",
        "image",
        "services",
        "before_script",
        "after_script",
        "cache",
        "artifacts",
    }

    def process_config(self, raw_config: dict[str, Any]) -> PipelineConfig:
        """Process raw configuration into structured pipeline config."""
        # Extract global configuration
        stages = raw_config.get("stages", ["test"])
        global_variables = raw_config.get("variables", {})
        default_config = self._process_default_config(raw_config.get("default", {}))

        # Process jobs
        jobs = []
        for name, job_data in raw_config.items():
            if name not in self.RESERVED_KEYWORDS and isinstance(job_data, dict):
                job = self._process_job(name, job_data, default_config, global_variables)
                jobs.append(job)

        return PipelineConfig(stages=stages, variables=global_variables, default=default_config, jobs=jobs)

    def _process_default_config(self, default_data: dict[str, Any]) -> DefaultConfig:
        """Process default configuration block."""
        return DefaultConfig(
            before_script=self._ensure_list(default_data.get("before_script", [])),
            after_script=self._ensure_list(default_data.get("after_script", [])),
            variables=default_data.get("variables", {}),
        )

    def _process_job(
        self, name: str, job_data: dict[str, Any], default: DefaultConfig, global_vars: dict[str, str]
    ) -> JobConfig:
        """Process a single job configuration."""
        # Merge variables with precedence: job > global > default
        variables = {}
        variables.update(default.variables)
        variables.update(global_vars)
        variables.update(job_data.get("variables", {}))

        # Merge scripts with default
        before_script = default.before_script + self._ensure_list(job_data.get("before_script", []))
        after_script = self._ensure_list(job_data.get("after_script", [])) + default.after_script

        return JobConfig(
            name=name,
            stage=job_data.get("stage", "test"),
            script=self._ensure_list(job_data.get("script", [])),
            variables=variables,
            before_script=before_script,
            after_script=after_script,
        )

    def _ensure_list(self, value: Union[str, list[str]]) -> list[str]:
        """Ensure a value is a list of strings."""
        if isinstance(value, str):
            return [value]
        elif isinstance(value, list):
            return value
        return []


class VariableManager:
    """Manages variable substitution and environment preparation."""

    def __init__(self, base_variables: dict[str, str] | None = None):
        self.base_variables = base_variables or {}
        self.gitlab_ci_vars = self._get_gitlab_ci_variables()

    def _get_gitlab_ci_variables(self) -> dict[str, str]:
        """Get GitLab CI built-in variables that we can simulate."""
        return {
            "CI": "true",
            "CI_PROJECT_DIR": str(Path.cwd()),
            "CI_PROJECT_NAME": Path.cwd().name,
            "CI_JOB_STAGE": "",  # Will be set per job
        }

    def prepare_environment(self, job: JobConfig) -> dict[str, str]:
        """Prepare environment variables for job execution."""
        env = os.environ.copy()

        # Apply variables in order: built-in -> base -> job
        env.update(self.gitlab_ci_vars)
        env.update(self.base_variables)
        env.update(job.variables)

        # Set job-specific variables
        env["CI_JOB_STAGE"] = job.stage
        env["CI_JOB_NAME"] = job.name

        return env

    def substitute_variables(self, text: str, variables: dict[str, str]) -> str:
        """Perform basic variable substitution in text."""
        # Simple substitution - replace $VAR and ${VAR} patterns

        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            return variables.get(var_name, match.group(0))

        # Match $VAR or ${VAR}
        pattern = r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)"
        return re.sub(pattern, replace_var, text)


class JobExecutor:
    """Executes individual jobs."""

    def __init__(self, variable_manager: VariableManager):
        self.variable_manager = variable_manager

    def execute_job(self, job: JobConfig) -> None:
        """Execute a single job."""
        print(f"🔧 Running job: {job.name} (stage: {job.stage})")

        env = self.variable_manager.prepare_environment(job)

        try:
            # Execute before_script
            if job.before_script:
                print("  📋 Running before_script...")
                self._execute_scripts(job.before_script, env)

            # Execute main script
            if job.script:
                print("  🚀 Running script...")
                self._execute_scripts(job.script, env)

            # Execute after_script
            if job.after_script:
                print("  📋 Running after_script...")
                self._execute_scripts(job.after_script, env)

            print(f"✅ Job {job.name} completed successfully")

        except subprocess.CalledProcessError as e:
            raise JobExecutionError(f"Job {job.name} failed with exit code {e.returncode}") from e

    def _execute_scripts(self, scripts: list[str], env: dict[str, str]) -> None:
        """Execute a list of script commands."""
        for script in scripts:
            if not isinstance(script, str):
                raise Exception(f"{script} is not a string")
            if not script.strip():
                continue

            # Substitute variables in the script
            script = self.variable_manager.substitute_variables(script, env)

            print(f"    $ {script}")

            # Execute using bash
            # command = ['"/c/Program Files/Git/bin/bash.exe"', '-c', shlex.quote(script).strip('\'')]
            # command = shlex.split(script)

            returncode = run_colored(
                script,
                env=env,
                cwd=Path.cwd(),
            )

            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, script)


class StageOrchestrator:
    """Orchestrates job execution by stages."""

    def __init__(self, job_executor: JobExecutor):
        self.job_executor = job_executor

    def execute_pipeline(self, pipeline: PipelineConfig) -> None:
        """Execute all jobs in the pipeline, organized by stages."""
        print("🚀 Starting GitLab CI pipeline execution")
        print(f"📋 Stages: {', '.join(pipeline.stages)}")

        jobs_by_stage = self._organize_jobs_by_stage(pipeline)

        for stage in pipeline.stages:
            stage_jobs = jobs_by_stage.get(stage, [])
            if not stage_jobs:
                print(f"⏭️  Skipping empty stage: {stage}")
                continue

            print(f"\n🎯 Executing stage: {stage}")

            for job in stage_jobs:
                self.job_executor.execute_job(job)

        print("\n🎉 Pipeline completed successfully!")

    def _organize_jobs_by_stage(self, pipeline: PipelineConfig) -> dict[str, list[JobConfig]]:
        """Organize jobs by their stages."""
        jobs_by_stage: dict[str, Any] = {}

        for job in pipeline.jobs:
            stage = job.stage
            if stage not in jobs_by_stage:
                jobs_by_stage[stage] = []
            jobs_by_stage[stage].append(job)

        return jobs_by_stage


class LocalGitLabRunner:
    """Main runner class that orchestrates the entire pipeline execution."""

    def __init__(self, base_path: Path | None = None):
        if not base_path:
            self.base_path = Path.cwd()
        else:
            self.base_path = base_path
        self.loader = ConfigurationLoader(base_path)
        self.processor = PipelineProcessor()

    def run_pipeline(self, config_path: Path | None = None) -> int:
        """Run the complete pipeline."""
        try:
            # Load and process configuration
            raw_config = self.loader.load_config(config_path)
            pipeline = self.processor.process_config(raw_config)

            # Set up execution components
            variable_manager = VariableManager(pipeline.variables)
            job_executor = JobExecutor(variable_manager)
            orchestrator = StageOrchestrator(job_executor)

            # Execute pipeline
            orchestrator.execute_pipeline(pipeline)

        except GitLabCIError as e:
            print(f"❌ GitLab CI Error: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            sys.exit(1)
        return 0


def best_efforts_run(config_path: Path) -> int:
    """Main entry point for the best-efforts-run command."""
    runner = LocalGitLabRunner()
    return runner.run_pipeline(config_path)


if __name__ == "__main__":

    def run() -> None:
        print(sys.argv)
        config = str(sys.argv[-1:][0])
        print(f"Running {config} ...")
        best_efforts_run(Path(config))

    run()
