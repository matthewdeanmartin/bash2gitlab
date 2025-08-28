from __future__ import annotations

import logging
import os
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import matplotlib.pyplot as plt  # noqa
    import networkx as nx  # noqa
    from graphviz import Source  # noqa
    from pyvis.network import Network  # noqa
except ModuleNotFoundError:
    # Optional render backends; handled at runtime in _auto_pick / render_graph
    pass  # nosec

from ruamel.yaml.error import YAMLError

from bash2gitlab.commands.compile_bash_reader import SOURCE_COMMAND_REGEX
from bash2gitlab.utils.parse_bash import extract_script_path
from bash2gitlab.utils.pathlib_polyfills import is_relative_to
from bash2gitlab.utils.temp_env import temporary_env_var
from bash2gitlab.utils.utils import short_path
from bash2gitlab.utils.yaml_factory import get_yaml

logger = logging.getLogger(__name__)

__all__ = ["generate_dependency_graph", "find_script_references_in_node"]

# =============================
# Data model
# =============================


@dataclass
class GraphModel:
    """Container for all graph artifacts.

    Attributes:
        root_path: Project root where we scan for YAML and scripts.
        graph: Mapping of source file → set of dependency Paths.
        processed_scripts: Set of scripts that were recursively traced.
        yaml_files: Set of YAML files discovered.
        dot_output: DOT language string representing the dependency graph.
        last_render_path: Path to the most recent rendered artifact (if any).
    """

    root_path: Path
    graph: dict[Path, set[Path]] = field(default_factory=dict)
    processed_scripts: set[Path] = field(default_factory=set)
    yaml_files: set[Path] = field(default_factory=set)
    dot_output: str | None = None
    last_render_path: Path | None = None


# =============================
# DOT formatting
# =============================


def format_dot_output(graph: dict[Path, set[Path]], root_path: Path) -> str:
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

    # YAML nodes
    yaml_files = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    for f in sorted(yaml_files):
        rel = f.relative_to(root_path)
        dot_lines.append(f'        "{rel}" [label="{rel}"];')
    dot_lines.append("    }")

    # Script nodes
    dot_lines.append("    subgraph cluster_scripts {")
    dot_lines.append('        label="Scripts";')
    dot_lines.append('        style="rounded";')
    dot_lines.append('        color="#22863a";')
    dot_lines.append('        node [style="filled,rounded", fillcolor="#e9f3ea", color="#22863a"];')

    script_files = {n for n in graph if n not in yaml_files}
    for deps in graph.values():
        script_files.update(d for d in deps if d not in yaml_files)

    for f in sorted(script_files):
        rel = f.relative_to(root_path)
        dot_lines.append(f'        "{rel}" [label="{rel}"];')
    dot_lines.append("    }")

    # Edges
    for src, deps in sorted(graph.items()):
        s_rel = src.relative_to(root_path)
        for dep in sorted(deps):
            d_rel = dep.relative_to(root_path)
            dot_lines.append(f'    "{s_rel}" -> "{d_rel}";')

    dot_lines.append("}")
    return "\n".join(dot_lines)


# =============================
# YAML/script parsing
# =============================


def parse_shell_script_dependencies(
    script_path: Path,
    root_path: Path,
    graph: dict[Path, set[Path]],
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
                sourced_path = (script_path.parent / sourced_script_name).resolve()

                if not is_relative_to(sourced_path, root_path):
                    logger.error(
                        f"Refusing to trace source '{short_path(sourced_path)}': escapes allowed root '{root_path}'."
                    )
                    continue

                graph[script_path].add(sourced_path)
                parse_shell_script_dependencies(sourced_path, root_path, graph, processed_files)
    except Exception as e:
        logger.error(f"Failed to read or parse script {script_path}: {e}")


def find_script_references_in_node(
    node: Any,
    yaml_path: Path,
    root_path: Path,
    graph: dict[Path, set[Path]],
    processed_scripts: set[Path],
) -> None:
    """Recursively traverses the YAML data structure to find script references."""
    if isinstance(node, dict):
        for key, value in node.items():
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
            script_path = (yaml_path.parent / script_path_str).resolve()
            if not is_relative_to(script_path, root_path):
                logger.error(f"Refusing to trace script '{script_path}': escapes allowed root '{root_path}'.")
                return
            graph.setdefault(yaml_path, set()).add(script_path)
            parse_shell_script_dependencies(script_path, root_path, graph, processed_scripts)


# =============================
# Build phase (no rendering)
# =============================


def build_graph(input_dir: Path) -> GraphModel:
    """Scan YAML + scripts and construct a :class:`GraphModel`.

    This function performs *no* rendering. Use :func:`render_graph` to export.
    """
    yaml_parser = get_yaml()
    root_path = input_dir.resolve()

    model = GraphModel(root_path=root_path)
    logger.info("Starting dependency graph generation in: %s", short_path(root_path))

    model.yaml_files = set(root_path.rglob("*.yml")) | set(root_path.rglob("*.yaml"))
    if not model.yaml_files:
        logger.warning("No YAML files found in %s", root_path)
        model.dot_output = ""
        return model

    for yaml_path in sorted(model.yaml_files):
        logger.debug("Parsing YAML file: %s", yaml_path)
        model.graph.setdefault(yaml_path, set())
        try:
            content = yaml_path.read_text("utf-8")
            yaml_data = yaml_parser.load(content)
            if yaml_data:
                find_script_references_in_node(yaml_data, yaml_path, root_path, model.graph, model.processed_scripts)
        except YAMLError as e:
            logger.error("Failed to parse YAML file %s: %s", yaml_path, e)
        except Exception as e:  # pragma: no cover (filesystem/env dependent)
            logger.error("An unexpected error occurred with %s: %s", yaml_path, e)

    logger.info(
        "Found %d source files and traced %d script dependencies.",
        len(model.graph),
        len(model.processed_scripts),
    )

    model.dot_output = format_dot_output(model.graph, model.root_path)
    logger.info("Successfully generated DOT graph output.")
    return model


# =============================
# Render phase (export artifact)
# =============================


def _render_with_graphviz(dot_output: str, filename_base: str) -> Path:
    src = Source(dot_output)
    out_file = src.render(
        filename=filename_base,
        directory=str(Path.cwd()),
        format="svg",
        cleanup=True,
    )
    return Path(out_file)


def _render_with_pyvis(graph: dict[Path, set[Path]], root_path: Path, filename_base: str) -> Path:
    # Pure-Python interactive HTML (vis.js)
    from pyvis.network import Network  # type: ignore

    html_path = Path.cwd() / f"{filename_base}.html"
    net = Network(height="750px", width="100%", directed=True, cdn_resources="in_line")

    yaml_nodes = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    script_nodes = set()
    for deps in graph.values():
        script_nodes.update(deps)
    script_nodes |= {n for n in graph if n not in yaml_nodes}

    # Add nodes with lightweight styling
    for n in sorted(yaml_nodes):
        rel = str(n.relative_to(root_path))
        net.add_node(rel, label=rel, title=rel, shape="box", color="#e6f0fa")
    for n in sorted(script_nodes):
        rel = str(n.relative_to(root_path))
        net.add_node(rel, label=rel, title=rel, shape="box", color="#e9f3ea")

    # Add edges
    for src, deps in graph.items():
        s_rel = str(src.relative_to(root_path))
        for dep in deps:
            d_rel = str(dep.relative_to(root_path))
            net.add_edge(s_rel, d_rel, arrows="to")

    # Write once; don't auto-open here (caller decides)
    net.write_html(str(html_path), open_browser=False)
    return html_path


def _render_with_networkx(graph: dict[Path, set[Path]], root_path: Path, filename_base: str) -> Path:
    import networkx as nx  # type: ignore
    from matplotlib import pyplot as plt  # type: ignore

    out_path = Path.cwd() / f"{filename_base}.svg"
    G = nx.DiGraph()

    yaml_nodes = {n for n in graph if n.suffix.lower() in (".yml", ".yaml")}
    script_nodes = set()
    for deps in graph.values():
        script_nodes.update(deps)
    script_nodes |= {n for n in graph if n not in yaml_nodes}

    def rel(p: Path) -> str:
        return str(p.relative_to(root_path))

    # Build graph
    for n in yaml_nodes | script_nodes:
        G.add_node(rel(n))
    for src, deps in graph.items():
        for dep in deps:
            G.add_edge(rel(src), rel(dep))

    # Layout & draw
    pos = nx.spring_layout(G, seed=42)
    plt.figure(figsize=(12, 6))
    nx.draw_networkx_nodes(G, pos, nodelist=[rel(n) for n in yaml_nodes])
    nx.draw_networkx_nodes(G, pos, nodelist=[rel(n) for n in script_nodes])
    nx.draw_networkx_edges(G, pos, arrows=True)
    nx.draw_networkx_labels(G, pos, font_size=8)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, format="svg")
    plt.close()
    return out_path


def _auto_pick_renderer() -> Literal["graphviz", "pyvis", "networkx", "none"]:
    try:
        import graphviz  # type: ignore  # noqa: F401

        return "graphviz"
    except Exception:
        try:
            import pyvis  # type: ignore  # noqa: F401

            return "pyvis"
        except Exception:
            try:
                import matplotlib  # type: ignore  # noqa: F401
                import networkx  # type: ignore  # noqa: F401

                return "networkx"
            except Exception:
                return "none"


def render_graph(
    model: GraphModel,
    renderer: Literal["auto", "graphviz", "pyvis", "networkx"] = "auto",
    *,
    open_in_browser: bool = True,
    filename_base: str | None = None,
) -> Path:
    """Render a :class:`GraphModel` to disk using the requested backend.

    Returns the file path of the generated artifact.
    """
    if model.dot_output is None:
        model.dot_output = format_dot_output(model.graph, model.root_path)

    base = filename_base or f"dependency-graph-{model.root_path.name}".replace(" ", "_")
    chosen: Literal["graphviz", "pyvis", "networkx", "none"]
    chosen = _auto_pick_renderer() if renderer == "auto" else renderer  # type: ignore

    try:
        # pyvis needs utf-8 but doesn't explicitly set it so it fails on Windows.
        with temporary_env_var("PYTHONUTF8", "1"):
            if chosen == "graphviz":
                out_path = _render_with_graphviz(model.dot_output, base)
            elif chosen == "pyvis":
                out_path = _render_with_pyvis(model.graph, model.root_path, base)
            elif chosen == "networkx":
                out_path = _render_with_networkx(model.graph, model.root_path, base)
            else:
                raise RuntimeError(
                    "No suitable renderer available. Install one of: graphviz, pyvis, networkx+matplotlib."
                )
        model.last_render_path = out_path
        logger.info("Wrote graph to %s", short_path(out_path))
        if open_in_browser and not os.environ.get("CI"):
            webbrowser.open(out_path.as_uri())
        return out_path
    except Exception as e:  # pragma: no cover - env dependent
        logger.error("Failed to render or open the graph: %s", e)
        raise


# =============================
# Convenience wrapper (build + render)
# =============================


def generate_dependency_graph(
    input_dir: Path,
    *,
    open_graph_in_browser: bool = True,
    renderer: Literal["auto", "graphviz", "pyvis", "networkx"] = "auto",
) -> str:
    """
    Convenience one-shot that builds the graph, renders it, and returns DOT.

    Note: This returns the DOT string (for stdout or further processing),
    *and* writes an artifact to disk via :func:`render_graph` when possible.
    To obtain the path to the artifact, use :func:`build_graph` +
    :func:`render_graph` directly, or inspect ``GraphModel.last_render_path``.
    """
    model = build_graph(input_dir)
    dot_output = model.dot_output or ""

    # Render as a side-effect, if requested
    try:
        render_graph(model, renderer=renderer, open_in_browser=open_graph_in_browser)
    except Exception:
        # Already logged; still return DOT for callers that only need text
        pass  # nosec

    return dot_output


# def generate_dependency_graph(
#     input_dir: Path,
#     *,
#     open_graph_in_browser: bool = True,
#     renderer: Literal["auto", "graphviz", "pyvis", "networkx"] = "auto",
#     attempts: int = 0,
#     renderers_attempted: set[str] | None = None,
# ) -> str:
#     """
#     Analyze YAML + scripts to build a dependency graph.
#
#     Args:
#         input_dir: Root directory of the uncompiled source files.
#         open_graph_in_browser: If True, write a graph file to CWD and open it.
#         renderer: "graphviz", "pyvis", "networkx", or "auto" (try in that order).
#         attempts: how many renderers attempted
#         renderers_attempted: which were tried
#
#     Returns:
#         DOT graph as a string (stdout responsibility is left to the caller).
#     """
#     auto_mode = renderer == "auto"
#     graph: dict[Path, set[Path]] = {}
#     processed_scripts: set[Path] = set()
#     yaml_parser = get_yaml()
#     root_path = input_dir.resolve()
#
#     logger.info(f"Starting dependency graph generation in: {short_path(root_path)}")
#
#     template_files = list(root_path.rglob("*.yml")) + list(root_path.rglob("*.yaml"))
#     if not template_files:
#         logger.warning(f"No YAML files found in {root_path}")
#         return ""
#
#     for yaml_path in template_files:
#         logger.debug(f"Parsing YAML file: {yaml_path}")
#         graph.setdefault(yaml_path, set())
#         try:
#             content = yaml_path.read_text("utf-8")
#             yaml_data = yaml_parser.load(content)
#             if yaml_data:
#                 find_script_references_in_node(yaml_data, yaml_path, root_path, graph, processed_scripts)
#         except YAMLError as e:
#             logger.error(f"Failed to parse YAML file {yaml_path}: {e}")
#         except Exception as e:
#             logger.error(f"An unexpected error occurred with {yaml_path}: {e}")
#
#     logger.info(f"Found {len(graph)} source files and traced {len(processed_scripts)} script dependencies.")
#
#     dot_output = format_dot_output(graph, root_path)
#     logger.info("Successfully generated DOT graph output.")
#
#     if open_graph_in_browser:
#         filename_base = f"dependency-graph-{root_path.name}".replace(" ", "_")
#
#         def _auto_pick() -> str:
#             try:
#                 import graphviz  # noqa: F401
#
#                 return "graphviz"
#             except Exception:
#                 try:
#                     import pyvis  # noqa: F401
#
#                     return "pyvis"
#                 except Exception:
#                     try:
#                         import matplotlib  # noqa: F401
#                         import networkx  # noqa: F401
#
#                         return "networkx"
#                     except Exception:
#                         return "none"
#
#         chosen = _auto_pick() if renderer == "auto" else renderer
#
#         try:
#             # pyvis needs utf-8 but doesn't explicitly set it so it fails on Windows.
#             with temporary_env_var("PYTHONUTF8", "1"):
#                 if chosen == "graphviz":
#                     # best, but requires additional installation
#                     out_path = _render_with_graphviz(dot_output, filename_base)
#                 elif chosen == "pyvis":
#                     # not at godo as graphviz
#                     out_path = _render_with_pyvis(graph, root_path, filename_base)
#                 elif chosen == "networkx":
#                     # can be a messy diagram
#                     out_path = _render_with_networkx(graph, root_path, filename_base)
#                 else:
#                     raise RuntimeError(
#                         "No suitable renderer available. Install one of: graphviz, pyvis, networkx+matplotlib."
#                     )
#
#             logger.info("Wrote graph to %s", short_path(out_path))
#             if not os.environ.get("CI"):
#                 webbrowser.open(out_path.as_uri())
#         except Exception as e:  # pragma: no cover - env dependent
#             logger.error("Failed to render or open the graph: %s", e)
#             if (1 < attempts < 4 and len(renderers_attempted or {}) < 3) or auto_mode:
#                 if not renderers_attempted:
#                     renderers_attempted = set()
#                 renderers_attempted.add(renderer)
#                 attempts += 1
#                 return generate_dependency_graph(
#                     input_dir,
#                     open_graph_in_browser=open_graph_in_browser,
#                     attempts=attempts,
#                     renderers_attempted=renderers_attempted,
#                 )
#
#     return dot_output
