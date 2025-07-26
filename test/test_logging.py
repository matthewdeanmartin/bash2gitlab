from bash2gitlab.logging_config import generate_config


def test_generate_config():
    assert generate_config()
    assert generate_config(level="INFO")
