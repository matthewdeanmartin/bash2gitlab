import os
from contextlib import contextmanager


@contextmanager
def temporary_env_var(key: str, value: str):
    """
    Temporarily set an environment variable and revert it back after the block of code.

    Args:
        key(str): The environment variable key
        value(str): The value to set for the environment variable
    """
    original_value = os.environ.get(key)
    try:
        os.environ[key] = value
        yield
    finally:
        # Revert the environment variable to its original state
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value
