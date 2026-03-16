"""Exceptions shared across entire library"""


class Bash2YamlError(Exception):
    """Base error for all errors defined in bash2yaml"""


class NotFound(Bash2YamlError):
    """Requested resource or file does not exist."""


class ConfigInvalid(Bash2YamlError):
    """Configuration file is malformed or invalid."""


class PermissionDenied(Bash2YamlError):
    """Insufficient permissions to access resource."""


class NetworkIssue(Bash2YamlError):
    """Network error occurred during remote operation."""


class ValidationFailed(Bash2YamlError):
    """YAML or schema validation failed."""


class CompileError(Bash2YamlError):
    """Error occurred during compilation process."""


class CompilationNeeded(Bash2YamlError):
    """Detected uncompiled changes requiring compilation."""
