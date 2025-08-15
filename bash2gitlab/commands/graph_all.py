from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

from bash2gitlab.bash_reader import SOURCE_COMMAND_REGEX
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

__all__ = ["generate_dependency_graph"]

Graph = dict[Path, set[Path]]


def format_dot_output(graph: Graph, root_path: Path) -> str:
    """Formats the dependency graph into the DOT language."""
    dot_lines = [
        "digraph bash2gitlab {",
        "    rankdir=LR;",
        "    node [shape=box, style=rounded];",
        "    graph [bgcolor=transparent];",
        '    edge [color="#cccccc"];',
        '    node [fontname="Inter", fontsize=10];',
        "    subgraph cluster_yaml {",
        '        label="YAML Sources";',
        '        style="rounded";',
        '        color="#0066cc";',
        '        node [style="filled,rounded", fillcolor="#e6f0fa", color="#0066cc"];',
    ]

    # Define YAML nodes first
    yaml_files = {node for node in graph if node.suffix.lower() in (".yml", ".yaml")}
    for file in sorted(yaml_files):
        relative_path = file.relative_to(root_path)
        dot_lines.append(f'        "{relative_path}" [label="{relative_path}"];')
    dot_lines.append("    }")

    dot_lines.append("    subgraph cluster_scripts {")
    dot_lines.append('        label="Scripts";')
    dot_lines.append('        style="rounded";')
    dot_lines.append('        color="#22863a";')
    dot_lines.append('        node [style="filled,rounded", fillcolor="#e9f3ea", color="#22863a"];')

    # Define Script nodes
    script_files = {node for node in graph if node not in yaml_files}
    for dep_set in graph.values():
        script_files.update(dep for dep in dep_set if dep not in yaml_files)

    for file in sorted(script_files):
        relative_path = file.relative_to(root_path)
        dot_lines.append(f'        "{relative_path}" [label="{relative_path}"];')
    dot_lines.append("    }")

    # Define edges
    for source, dependencies in sorted(graph.items()):
        source_rel = source.relative_to(root_path)
        for dep in sorted(dependencies):
            dep_rel = dep.relative_to(root_path)
            dot_lines.append(f'    "{source_rel}" -> "{dep_rel}";')

    dot_lines.append("}")
    return "\n".join(dot_lines)


def parse_shell_script_dependencies(
    script_path: Path,
    root_path: Path,
    graph: Graph,
    processed_files: set[Path],
) -> None:
    """Recursively parses a shell script to find `source` dependencies."""
    if script_path in processed_files:
        return
    processed_files.add(script_path)

    if not script_path.is_file():
        logger.warning(f"Dependency not found and will be skipped: {script_path}")
        return

    graph.setdefault(script_path, set())

    try:
        content = script_path.read_text("utf-8")
        for line in content.splitlines():
            match = SOURCE_COMMAND_REGEX.match(line)
            if match:
                sourced_script_name = match.group("path")
                # Resolve the path relative to the current script's directory
                sourced_path = (script_path.parent / sourced_script_name).resolve()

                # Security: Ensure the path is within the project root
                if not sourced_path.is_relative_to(root_path):
                    logger.error(f"Refusing to trace source '{sourced_path}': escapes allowed root '{root_path}'.")
                    continue

                graph[script_path].add(sourced_path)
                parse_shell_script_dependencies(sourced_path, root_path, graph, processed_files)
    except Exception as e:
        logger.error(f"Failed to read or parse script {script_path}: {e}")


def find_script_references_in_node(
    node: Any,
    yaml_path: Path,
    root_path: Path,
    graph: Graph,
    processed_scripts: set[Path],
) -> None:
    """Recursively traverses the YAML data structure to find script references."""
    if isinstance(node, dict):
        for key, value in node.items():
            # Check if the key indicates a script block
            if key in ("script", "before_script", "after_script"):
                find_script_references_in_node(value, yaml_path, root_path, graph, processed_scripts)
            else:
                find_script_references_in_node(value, yaml_path, root_path, graph, processed_scripts)
    elif isinstance(node, list):
        for item in node:
            find_script_references_in_node(item, yaml_path, root_path, graph, processed_scripts)
    elif isinstance(node, str):
        script_path_str = extract_script_path(node)
        if script_path_str:
            # Resolve the path relative to the YAML file's directory
            script_path = (yaml_path.parent / script_path_str).resolve()

            # Security: Ensure the path is within the project root
            if not script_path.is_relative_to(root_path):
                logger.error(f"Refusing to trace script '{script_path}': escapes allowed root '{root_path}'.")
                return

            graph.setdefault(yaml_path, set()).add(script_path)
            parse_shell_script_dependencies(script_path, root_path, graph, processed_scripts)


def generate_dependency_graph(uncompiled_path: Path) -> str:
    """
    Analyzes the source YAML and script files to build a dependency graph.

    Args:
        uncompiled_path: The root directory of the uncompiled source files.

    Returns:
        A string containing the dependency graph in DOT format.
    """
    graph: Graph = {}
    processed_scripts: set[Path] = set()
    yaml_parser = get_yaml()
    root_path = uncompiled_path.resolve()

    logger.info(f"Starting dependency graph generation in: {root_path}")

    # Discover all YAML files
    template_files = list(root_path.rglob("*.yml")) + list(root_path.rglob("*.yaml"))

    if not template_files:
        logger.warning(f"No YAML files found in {root_path}")
        return ""

    # Phase 1: Parse YAML files to find top-level script dependencies
    for yaml_path in template_files:
        logger.debug(f"Parsing YAML file: {yaml_path}")
        graph.setdefault(yaml_path, set())
        try:
            content = yaml_path.read_text("utf-8")
            yaml_data = yaml_parser.load(content)
            if yaml_data:
                find_script_references_in_node(yaml_data, yaml_path, root_path, graph, processed_scripts)
        except YAMLError as e:
            logger.error(f"Failed to parse YAML file {yaml_path}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred with {yaml_path}: {e}")

    logger.info(f"Found {len(graph)} source files and traced {len(processed_scripts)} script dependencies.")

    # Phase 2: Format the collected graph data into DOT format
    dot_output = format_dot_output(graph, root_path)
    logger.info("Successfully generated DOT graph output.")

    return dot_output
