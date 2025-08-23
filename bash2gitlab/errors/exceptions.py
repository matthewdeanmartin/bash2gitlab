"""Exceptions shared across entire library"""


class Bash2GitlabError(Exception):
    """Base error for all errors defined in bash2gitlab"""


class NotFound(Bash2GitlabError): ...


class ConfigInvalid(Bash2GitlabError): ...


class PermissionDenied(Bash2GitlabError): ...


class NetworkIssue(Bash2GitlabError): ...


class ValidationFailed(Bash2GitlabError): ...


class CompileError(Bash2GitlabError): ...
