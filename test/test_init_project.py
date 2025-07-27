from __future__ import annotations

from pathlib import Path

from bash2gitlab.init_project import DEFAULT_CONFIG, DEFAULT_FLAGS, TOML_TEMPLATE, create_config_file, prompt_for_config


def test_prompt_for_config_defaults(monkeypatch):
    """
    Tests that prompt_for_config returns all default values when the user provides no input.
    """
    # Simulate the user pressing Enter for every prompt
    monkeypatch.setattr("builtins.input", lambda _: "")

    # Run the function
    config = prompt_for_config()

    # Check that the returned config matches the defaults
    expected_config = {**DEFAULT_CONFIG, **DEFAULT_FLAGS}
    assert config == expected_config


def test_prompt_for_config_custom_values(monkeypatch):
    """
    Tests that prompt_for_config correctly processes custom user input.
    """
    # Simulate custom user inputs for each prompt
    user_inputs = [
        "my_src",  # input_dir
        "my_out",  # output_dir
        "my_scripts",  # scripts_dir
        "",  # templates_in (default)
        "my_out/tpl",  # templates_out
        "y",  # format
        "n",  # verbose
        "yes",  # quiet
    ]
    # Use an iterator to provide one value per call to input()
    input_iterator = iter(user_inputs)
    monkeypatch.setattr("builtins.input", lambda _: next(input_iterator))

    # Run the function
    config = prompt_for_config()

    # Check that the returned config matches the custom inputs
    expected_config = {
        "input_dir": "my_src",
        "output_dir": "my_out",
        "scripts_dir": "my_scripts",
        "templates_in": "templates",  # Default value
        "templates_out": "my_out/tpl",
        "format": True,
        "verbose": False,
        "quiet": True,
    }
    assert config == expected_config


def test_create_config_file_standard_run(tmp_path: Path):
    """
    Tests that create_config_file correctly creates the toml file with the right content.
    """
    test_config = {
        **DEFAULT_CONFIG,
        "format": True,
        "verbose": False,
        "quiet": True,
    }

    # Run the function using the tmp_path fixture
    create_config_file(tmp_path, test_config)

    # Check if the file was created
    config_file = tmp_path / "bash2gitlab.toml"
    assert config_file.is_file()

    # Check the content of the file
    content = config_file.read_text()
    # Create a comparable config with lowercase bools for the template
    formatted_config = test_config.copy()
    formatted_config["format"] = "true"
    formatted_config["verbose"] = "false"
    formatted_config["quiet"] = "true"
    expected_content = TOML_TEMPLATE.format(**formatted_config)
    assert content == expected_content


def test_create_config_file_dry_run(tmp_path: Path):
    """
    Tests that create_config_file does not create any files when dry_run is True.
    """
    test_config = {**DEFAULT_CONFIG, **DEFAULT_FLAGS}

    # Run the function with dry_run=True
    create_config_file(tmp_path, test_config, dry_run=True)

    # Check that the file was NOT created
    config_file = tmp_path / "bash2gitlab.toml"
    assert not config_file.exists()
