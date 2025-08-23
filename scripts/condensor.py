"""Condense Python code for bot consumption."""

import ast
import logging
import re
import textwrap
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def remove_main_block(source_code: str) -> str:
    """Remove the `if __name__ == "__main__":` block and everything that follows."""
    pattern = r"\nif\s+__name__\s*==\s*['\"]__main__['\"]\s*:"
    compiled_pattern = re.compile(pattern, flags=re.MULTILINE)
    match = compiled_pattern.search(source_code)

    if match:
        modified_source = source_code[:match.start()]
        LOGGER.info("Removed __name__ == '__main__' block")
        return modified_source
    return source_code


def remove_comments_from_lines(lines: list[str]) -> list[str]:
    """Remove comment-only lines from a list of strings."""
    return [line for line in lines if not line.lstrip().startswith("#")]


def extract_function_signatures(source_code: str) -> list[tuple[str, str]]:
    """Extract function signatures and docstrings from source code."""
    try:
        parsed_code = ast.parse(source_code)
    except SyntaxError:
        LOGGER.error("Error parsing source code")
        return []

    signatures = []
    for node in ast.walk(parsed_code):
        if isinstance(node, ast.FunctionDef):
            signature = ast.unparse(node.args)
            docstring = ast.get_docstring(node) or ""

            if docstring:
                indented_docstring = f'    """{docstring}"""\n'
            else:
                indented_docstring = ""

            return_annotation = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            full_signature = f"def {node.name}({signature}){return_annotation}:\n{indented_docstring}    ...\n"
            signatures.append((full_signature, docstring))

    return signatures


def extract_class_signatures(source_code: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Extract class signatures with their methods."""
    try:
        parsed_code = ast.parse(source_code)
    except SyntaxError:
        LOGGER.error("Error parsing source code")
        return []

    classes = []
    for node in ast.walk(parsed_code):
        if isinstance(node, ast.ClassDef):
            class_docstring = ast.get_docstring(node) or ""
            if class_docstring:
                indented_docstring = f'    """{class_docstring}"""'
            else:
                indented_docstring = "    pass"

            class_signature = f"class {node.name}:\n{indented_docstring}"

            methods = []
            for body_item in node.body:
                if isinstance(body_item, ast.FunctionDef):
                    method_signature = ast.unparse(body_item.args)
                    method_docstring = ast.get_docstring(body_item) or ""

                    if method_docstring:
                        indented_method_docstring = textwrap.indent(f'    """{method_docstring}"""\n', "    ")
                    else:
                        indented_method_docstring = ""

                    return_annotation = f" -> {ast.unparse(body_item.returns)}" if body_item.returns else ""
                    full_method_signature = f"    def {body_item.name}({method_signature}){return_annotation}:\n{indented_method_docstring}        ..."
                    methods.append((full_method_signature, method_docstring))

            classes.append((class_signature, methods))

    return classes


def process_python_file(
        file_path: Path,
        package_name: str = "",
        remove_main: bool = False,
        remove_comments: bool = False,
        signatures_only: bool = False
) -> str:
    """Process a single Python file and format it for bot consumption."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        LOGGER.warning(f"Could not read {file_path} with UTF-8 encoding")
        return ""
    except FileNotFoundError:
        LOGGER.error(f"File not found: {file_path}")
        return ""

    # Apply transformations
    if remove_main:
        content = remove_main_block(content)

    if remove_comments:
        lines = remove_comments_from_lines(content.split("\n"))
        content = "\n".join(lines)

    # Build output
    result = f"\nSource Path: {file_path}\n"

    if package_name:
        # Convert file path to module notation
        relative_path = file_path.relative_to(file_path.parents[len(file_path.parents) - 1])
        module_parts = list(relative_path.parts[:-1]) + [relative_path.stem]
        if package_name not in module_parts[0]:
            module_parts = [package_name] + module_parts
        module_name = ".".join(module_parts)
        result += f"Module Name: {module_name}\n"

    if signatures_only:
        # Extract only signatures
        result += "```python\n"

        functions = extract_function_signatures(content)
        classes = extract_class_signatures(content)

        for func_sig, _ in functions:
            if "self" not in func_sig:  # Standalone functions only
                result += func_sig + "\n"

        for class_sig, methods in classes:
            result += f"{class_sig}\n"
            for method_sig, _ in methods:
                result += f"{method_sig}\n"
            result += "\n"

        result += "```\n"
    else:
        # Include full source
        result += f"```python\n{content}\n```\n"

    return result


def find_python_files(src_path: Path) -> list[Path]:
    """Recursively find all Python files in the source directory."""
    if not src_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {src_path}")

    if src_path.is_file() and src_path.suffix == ".py":
        return [src_path]

    python_files = []
    for file_path in src_path.rglob("*.py"):
        if file_path.is_file():
            python_files.append(file_path)

    return sorted(python_files)


class CodeCondenser:
    """Main class for condensing Python code for bot consumption."""

    def __init__(
            self,
            src_path: Path,
            package_name: str = "",
            remove_main: bool = True,
            remove_comments: bool = False,
            signatures_only: bool = False
    ):
        self.src_path = Path(src_path)
        self.package_name = package_name
        self.remove_main = remove_main
        self.remove_comments = remove_comments
        self.signatures_only = signatures_only

        if not self.src_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {self.src_path}")

    def _process_file_wrapper(self, file_path: Path) -> str:
        """Wrapper for processing files in parallel."""
        return process_python_file(
            file_path,
            self.package_name,
            self.remove_main,
            self.remove_comments,
            self.signatures_only
        )

    def condense(self) -> str:
        """Condense all Python files in the source directory."""
        python_files = find_python_files(self.src_path)

        if not python_files:
            LOGGER.warning(f"No Python files found in {self.src_path}")
            return ""

        LOGGER.info(f"Found {len(python_files)} Python files")

        results = []

        if len(python_files) < 5:
            # Process serially for small number of files
            LOGGER.info("Processing files serially")
            for file_path in python_files:
                result = self._process_file_wrapper(file_path)
                if result:
                    results.append(result)
        else:
            # Process in parallel for larger number of files
            LOGGER.info("Processing files in parallel")
            with ProcessPoolExecutor() as executor:
                future_to_file = {
                    executor.submit(self._process_file_wrapper, file_path): file_path
                    for file_path in python_files
                }

                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        result = future.result()
                        if result:
                            results.append(result)
                    except Exception as e:
                        LOGGER.error(f"Error processing {file_path}: {e}")

        return "\n".join(results)

    def save_to_file(self, output_path: Path) -> None:
        """Condense and save to file."""
        condensed = self.condense()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(condensed)
        LOGGER.info(f"Condensed code saved to {output_path}")


def main():
    """Example usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Condense Python code for bot consumption")
    parser.add_argument("src_path", help="Source directory or file path")
    parser.add_argument("-p", "--package", default="", help="Package name for module notation")
    parser.add_argument("-o", "--output", help="Output file path")
    parser.add_argument("--keep-main", action="store_true", help="Keep __main__ blocks")
    parser.add_argument("--remove-comments", action="store_true", help="Remove comment lines")
    parser.add_argument("--signatures-only", action="store_true", help="Extract signatures only")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    condenser = CodeCondenser(
        src_path=Path(args.src_path),
        package_name=args.package,
        remove_main=not args.keep_main,
        remove_comments=args.remove_comments,
        signatures_only=args.signatures_only
    )

    if args.output:
        condenser.save_to_file(Path(args.output))
    else:
        print(condenser.condense())


if __name__ == "__main__":
    main()