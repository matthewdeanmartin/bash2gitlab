"""Exceptions shared across entire library"""


class Bash2GitlabError(Exception):
    """Base error for all errors defined in bash2gitlab"""


class NotFound(Bash2GitlabError):
    """Requested resource or file does not exist."""


class ConfigInvalid(Bash2GitlabError):
    """Configuration file is malformed or invalid."""


class PermissionDenied(Bash2GitlabError):
    """Insufficient permissions to access resource."""


class NetworkIssue(Bash2GitlabError):
    """Network error occurred during remote operation."""


class ValidationFailed(Bash2GitlabError):
    """YAML or schema validation failed."""


class CompileError(Bash2GitlabError):
    """Error occurred during compilation process."""


class CompilationNeeded(Bash2GitlabError):
    """Detected uncompiled changes requiring compilation."""
