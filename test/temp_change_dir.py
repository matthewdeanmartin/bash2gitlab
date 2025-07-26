from __future__ import annotations

import os
from contextlib import contextmanager


@contextmanager
def chdir_to_file_dir(file_path):
    """
    A context manager that changes the current working directory to the
    directory of the specified file and then changes it back after the
    context is exited.

    Args:
        file_path (str): The path to the file whose directory should be
                         used as the temporary working directory.
                         Typically, this will be `__file__`.

    Example:
        # In your test file (e.g., test_my_module.py)
        # Assuming test_data.txt is in the same directory as test_my_module.py

        import os
        import unittest

        class MyTest(unittest.TestCase):
            def test_read_data_file(self):
                with chdir_to_file_dir(__file__):
                    # Now, the current working directory is the directory of test_my_module.py
                    # You can access test_data.txt directly
                    with open("test_data.txt", "r") as f:
                        content = f.read()
                        self.assertIn("expected content", content)
                # After exiting the 'with' block, the original working directory is restored
                print(f"Current working directory after context: {os.getcwd()}")
    """
    original_cwd = os.getcwd()  # Store the original current working directory
    file_directory = os.path.dirname(os.path.abspath(file_path))  # Get the absolute path of the file's directory

    try:
        os.chdir(file_directory)  # Change to the file's directory
        print(f"Changed directory to: {os.getcwd()}")
        yield  # Yield control to the 'with' block
    finally:
        os.chdir(original_cwd)  # Change back to the original directory
        print(f"Restored directory to: {os.getcwd()}")
