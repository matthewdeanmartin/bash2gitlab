import os

from bash2gitlab.utils.temp_env import temporary_env_var


def test_it():
    with temporary_env_var("ENV_VAR_NAME", "new_value"):
        assert os.environ["ENV_VAR_NAME"] == "new_value"
