# TODO: haha, this should be a static resources. The function to enerate an invocation should be just a few lines and  Path logic


def generate_bash_clone_and_execute() -> str:
    """
    Generates a Bash function that clones a Git repository over HTTPS using basic authentication,
    locates a specified script file within a subfolder at the root of the cloned repository,
    and executes it using bash while preserving the current working directory.

    This function addresses the challenge of integrating scripts from a templates repository
    in GitLab CI/CD pipelines, where 'include' is limited to YAML files. By cloning into a
    temporary directory and executing the script with an absolute path, it avoids interfering
    with the local filesystem or changing the working directory, ensuring the script runs
    in the context of the project root if it relies on relative paths.

    The generated Bash code includes a urlencode helper to properly encode the username and
    password for the clone URL, handling special characters. The repo_url should be provided
    without the 'https://' prefix or '.git' suffix. The function takes parameters as arguments
    for flexibility, allowing sensitive values like username and password to be passed via
    environment variables in CI environments.

    Returns:
        str: The string containing the Bash function definitions, ready to be included in a script or pipeline.
    """
    bash_code = """
urlencode() {
    # Usage: urlencode <string>
    # URL-encodes the input string to handle special characters in usernames or passwords.
    old_lc_collate=$LC_COLLATE
    LC_COLLATE=C
    local length="${#1}"
    for (( i = 0; i < length; i++ )); do
        local c="${1:$i:1}"
        case $c in
            [a-zA-Z0-9.~_-]) printf '%s' "$c" ;;
            *) printf '%%%02X' "'$c" ;;
        esac
    done
    LC_COLLATE=$old_lc_collate
}

clone_and_execute() {
    # Usage: clone_and_execute <repo_url> <username> <password> <filename> [<subfolder>]
    # Clones the repo into a temp directory, finds the script in the subfolder (default: 'src'),
    # executes it from the current working directory, and cleans up.
    #
    # Args:
    #   repo_url: HTTPS URL of the repo without 'https://' or '.git' (e.g., 'gitlab.com/group/templates')
    #   username: Username for basic auth
    #   password: Password or token for basic auth
    #   filename: Name of the script to execute (e.g., 'script.sh')
    #   subfolder: Optional subfolder where the script is located (default: 'src')
    local repo_url="$1"
    local username="$2"
    local password="$3"
    local filename="$4"
    local subfolder="${5:-src}"

    # Create a temporary directory to clone into, avoiding conflicts with the local filesystem
    local temp_dir=$(mktemp -d)

    # URL-encode username and password to handle special characters
    local user_enc=$(urlencode "$username")
    local pass_enc=$(urlencode "$password")

    # Construct the authenticated clone URL, appending '.git'
    local host_path="${repo_url#https://}"  # Remove 'https://' if present
    local clone_url="https://${user_enc}:${pass_enc}@${host_path}.git"

    # Clone the repository to the temp directory
    git clone "$clone_url" "$temp_dir" || { echo "Git clone failed"; rm -rf "$temp_dir"; return 1; }

    # Build the full path to the script
    local script_path="${temp_dir}/${subfolder}/${filename}"

    # Verify the script exists
    if [ ! -f "$script_path" ]; then
        echo "Script file '${filename}' not found in '${subfolder}' subfolder."
        rm -rf "$temp_dir"
        return 1
    fi

    # Ensure the script is executable
    chmod +x "$script_path"

    # Execute the script using bash; the CWD remains the caller's directory, solving path issues
    bash "$script_path" || { local exit_code=$?; echo "Script execution failed with code ${exit_code}"; rm -rf "$temp_dir"; return $exit_code; }

    # Clean up the temporary directory
    rm -rf "$temp_dir"
}
"""
    return bash_code
