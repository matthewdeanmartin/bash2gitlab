from pathlib import Path

from ruamel.yaml import YAML


def run() -> None:
    # --- 1. Setup: Create a dummy script file to include ---
    script_content = "echo 'Hello from the included script!'"
    script_path = Path("my_script.sh")
    script_path.write_text(script_content)

    print(f"Created a dummy script at: '{script_path}'\n")

    # --- 2. Define the source YAML with the custom !include tag ---
    yaml_string = """
    job:
      name: my-first-job
      script:
        - !include my_script.sh
        - echo "This is another command."
    """

    # --- 3. Define the custom constructor function ---
    # This function tells the parser what to do when it sees "!include"
    def include_constructor(loader, node):
        """
        Reads the content of the file specified in the node.
        The value of the node is the filename (e.g., 'my_script.sh').
        """
        file_path = Path(node.value)
        if not file_path.is_file():
            # You could raise an error or handle it as needed
            return f"ERROR: File not found at {file_path}"
        return file_path.read_text()

    # --- 4. Initialize the parser and register the custom tag ---
    yaml = YAML()
    # Teach the parser about our new "!include" tag
    yaml.constructor.add_constructor("!include", include_constructor)

    print("--- Source YAML ---")
    print(yaml_string)

    # --- 5. Load the YAML and see the result ---
    data = yaml.load(yaml_string)

    print("\n--- Parsed Python Object (YAML structure) ---")
    print(data)

    print("\n--- Resulting script commands ---")
    for command in data["job"]["script"]:
        print(f"- {command.strip()}")

    # --- 6. Clean up the dummy file ---
    script_path.unlink()
    print(f"\nCleaned up (deleted) '{script_path}'")


if __name__ == "__main__":
    run()
