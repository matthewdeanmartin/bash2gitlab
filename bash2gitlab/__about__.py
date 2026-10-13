"""Metadata for bash2gitlab."""

__all__ = [
    "__credits__",
    "__dependencies__",
    "__description__",
    "__keywords__",
    "__license__",
    "__readme__",
    "__requires_python__",
    "__status__",
    "__title__",
    "__version__",
]

__title__ = "bash2gitlab"
__version__ = "0.10.1"
__description__ = "Compile bash to gitlab pipeline yaml"
__readme__ = "README.md"
__credits__ = [{"name": "Matthew Martin", "email": "matthewdeanmartin@gmail.com"}]
__keywords__ = ["bash", "gitlab"]
__license__ = "MIT"
__requires_python__ = ">=3.11"
__dependencies__ = [
    "ruamel.yaml>=0.18.14",
    "jsonschema>=4.23.0",
    "importlib_resources>=6.4.5",
    "toml>=0.10.2",
    "rtoml>=0.13.0; python_version == '3.14'",
    "rtoml>=0.14.0; python_version >= '3.15'",
    "rtoml>=0.5.0; python_version < '3.14'",
    "urllib3>=2.0.0",
    "orjson>=3.10.8",
    "certifi>=2025.8.3",
    "pluggy>=1.0.0",
    "python-gitlab>=1.0.0",
]
__status__ = "5 - Production/Stable"
