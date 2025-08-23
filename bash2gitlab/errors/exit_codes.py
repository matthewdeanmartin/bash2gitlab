from __future__ import annotations

from enum import IntEnum
from subprocess import CalledProcessError  # nosec

from bash2gitlab.commands.best_effort_runner import GitlabRunnerError
from bash2gitlab.commands.compile_bash_reader import PragmaError, SourceSecurityError
from bash2gitlab.errors.exceptions import (
    Bash2GitlabError,
    CompileError,
    ConfigInvalid,
    NetworkIssue,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)


class ExitCode(IntEnum):
    OK = 0
    USAGE = 2  # argparse-like
    NOT_FOUND = 3
    CONFIG_ERROR = 4
    PERMISSION_DENIED = 6
    NETWORK_ERROR = 5
    VALIDATION_ERROR = 7
    UNINSTALLED_DEPENDENCIES = 8

    # Bash2Gitlab domain errors
    COMMAND_ERROR = 30
    PRAGMA_ERROR = 31
    SOURCE_SECURITY_ERROR = 32
    GITLAB_RUNNER_ERROR = 33
    COMPILE_ERROR = 34

    # Generic python
    FILE_EXISTS = (80,)
    EXTERNAL_COMMAND_ERROR = 81

    INTERRUPTED = 130  # 128 + SIGINT
    UNEXPECTED = 70  # similar to sysexits EX_SOFTWARE


ERROR_CODE_MAP: dict[type[BaseException], ExitCode] = {
    NotFound: ExitCode.NOT_FOUND,
    ConfigInvalid: ExitCode.CONFIG_ERROR,
    PermissionDenied: ExitCode.PERMISSION_DENIED,
    NetworkIssue: ExitCode.NETWORK_ERROR,
    ValidationFailed: ExitCode.VALIDATION_ERROR,
    GitlabRunnerError: ExitCode.GITLAB_RUNNER_ERROR,
    SourceSecurityError: ExitCode.SOURCE_SECURITY_ERROR,
    PragmaError: ExitCode.PRAGMA_ERROR,
    CompileError: ExitCode.COMPILE_ERROR,
    # You can add Python built-ins too if you want:
    FileNotFoundError: ExitCode.NOT_FOUND,
    PermissionError: ExitCode.PERMISSION_DENIED,
    FileExistsError: ExitCode.FILE_EXISTS,
    CalledProcessError: ExitCode.EXTERNAL_COMMAND_ERROR,
    ConnectionError: ExitCode.NETWORK_ERROR,
}


def resolve_exit_code(exc: BaseException) -> ExitCode:
    """
    Find the first matching mapping by walking the exception's MRO.
    This lets subclass relationships work naturally.
    """
    for cls in type(exc).mro():
        if cls in ERROR_CODE_MAP:
            return ERROR_CODE_MAP[cls]
    # Domain "expected" but unmapped → treat as runtime error bucket
    if isinstance(exc, Bash2GitlabError):
        return ExitCode.COMMAND_ERROR
    return ExitCode.UNEXPECTED
