from __future__ import annotations

import logging
from pathlib import Path

import pytest

# Import the unit under test
from bash2gitlab.commands.graph_all import format_dot_output, generate_dependency_graph

# ----- Helpers -----------------------------------------------------------------


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def norm(s: str) -> str:
    """Normalize path separators in strings for cross-OS assertions."""
    return s.replace("\\", "/")


# ----- Tests -------------------------------------------------------------------


def test_generate_dependency_graph_basic_edges_and_nodes(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """
    Happy-path: two YAMLs referencing scripts; scripts chain via `source` and `.`.
    We expect edges:
      a.yml        -> scripts/a.sh
      b.yaml       -> scripts/c.sh
      scripts/a.sh -> scripts/b.sh
      scripts/b.sh -> scripts/c.sh
    """
    caplog.set_level(logging.INFO)

    root = tmp_path / "proj"
    # YAML files
    write(
        root / "a.yml",
        """
stages: []
job_a:
  script:
    - "./scripts/a.sh"
""",
    )
    write(
        root / "b.yaml",
        """
stages: []
job_b:
  before_script:
    - "./scripts/c.sh"
""",
    )

    # Scripts with nested sourcing: a -> b -> c
    write(
        root / "scripts" / "a.sh",
        """#!/usr/bin/env bash
echo A
source b.sh
""",
    )
    write(
        root / "scripts" / "b.sh",
        """#!/usr/bin/env bash
echo B
. c.sh
""",
    )
    write(
        root / "scripts" / "c.sh",
        """#!/usr/bin/env bash
echo C
""",
    )

    dot = generate_dependency_graph(root, open_graph_in_browser=False)

    # Basic sanity
    assert "digraph bash2gitlab" in dot
    # Nodes appear grouped (we won't assert cluster styling beyond presence)
    assert "subgraph cluster_yaml" in dot
    assert "subgraph cluster_scripts" in dot

    d = norm(dot)
    # YAML -> script edges
    assert '"a.yml" -> "scripts/a.sh";' in d
    assert '"b.yaml" -> "scripts/c.sh";' in d
    # Script -> script edges
    assert '"scripts/a.sh" -> "scripts/b.sh";' in d
    assert '"scripts/b.sh" -> "scripts/c.sh";' in d

    # Some logging was produced
    assert any("Starting dependency graph generation" in rec.getMessage() for rec in caplog.records)


def test_no_yaml_returns_empty(tmp_path: Path) -> None:
    """
    If the root contains no *.yml/*.yaml, the function should return an empty string.
    """
    root = tmp_path / "empty"
    root.mkdir(parents=True, exist_ok=True)

    dot = generate_dependency_graph(root, open_graph_in_browser=False)
    assert dot == ""


def test_invalid_yaml_logs_and_skips_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """
    A YAML that fails to parse should be logged and skipped; other YAMLs still process.
    """
    caplog.set_level(logging.INFO)

    root = tmp_path / "proj"
    # Bad YAML
    write(root / "bad.yml", ":\n  - this is not valid yaml:\n    - {")
    # Good YAML that references a script
    write(
        root / "ok.yml",
        """
stages: []
job_ok:
  script:
    - "./scripts/run.sh"
""",
    )
    write(root / "scripts" / "run.sh", "#!/usr/bin/env bash\necho OK\n")

    dot = generate_dependency_graph(root, open_graph_in_browser=False)

    # We still got a graph for ok.yml -> scripts/run.sh
    d = norm(dot)
    assert '"ok.yml"' in d
    assert '"scripts/run.sh"' in d
    assert '"ok.yml" -> "scripts/run.sh";' in d

    # Error about bad.yml should be logged
    assert any("Failed to parse YAML file" in rec.getMessage() for rec in caplog.records)


def test_missing_dependency_warns_but_edge_exists(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """
    When a sourced script is inside root but missing on disk:
    - The edge is still recorded (current behavior),
    - A warning about missing dependency is logged during recursive parse.
    """
    caplog.set_level(logging.INFO)

    root = tmp_path / "proj"
    write(
        root / "a.yml",
        """
stages: []
job:
  script:
    - "./scripts/a.sh"
""",
    )
    write(
        root / "scripts" / "a.sh",
        """#!/usr/bin/env bash
echo A
source present.sh
source missing.sh
""",
    )
    write(root / "scripts" / "present.sh", "#!/usr/bin/env bash\necho present\n")

    dot = generate_dependency_graph(root, open_graph_in_browser=False)
    d = norm(dot)

    # Edges to present and missing are included in the DOT
    assert '"scripts/a.sh" -> "scripts/present.sh";' in d
    assert '"scripts/a.sh" -> "scripts/missing.sh";' in d

    # And a warning about the missing file should be in logs
    # (the message originates when parse recurses into the missing path)
    missing_msg = f"Dependency not found and will be skipped: {root / 'scripts' / 'missing.sh'}"
    assert any(missing_msg in rec.getMessage() for rec in caplog.records)


def test_format_dot_output_clusters_and_labels(tmp_path: Path) -> None:
    """
    Directly exercise format_dot_output to ensure cluster sections and labels
    render relative paths.
    """
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    yml = root / "pipeline.yml"
    s1 = root / "scripts" / "one.sh"
    s2 = root / "scripts" / "two.sh"

    graph = {
        yml: {s1, s2},
        s1: set(),
        s2: set(),
    }

    dot = format_dot_output(graph, root.resolve())
    d = norm(dot)

    # Clusters present
    assert "subgraph cluster_yaml" in d
    assert "subgraph cluster_scripts" in d

    # Relative node labels present
    assert '"pipeline.yml" [label="pipeline.yml"];' in d
    assert '"scripts/one.sh" [label="scripts/one.sh"];' in d
    assert '"scripts/two.sh" [label="scripts/two.sh"];' in d

    # Edges present
    assert '"pipeline.yml" -> "scripts/one.sh";' in d
    assert '"pipeline.yml" -> "scripts/two.sh";' in d


def test_extract_script_path_rules_skip_unsafe_commands(tmp_path: Path) -> None:
    """
    Ensure commands with extra args are ignored (depends on extract_script_path behavior).
    We'll place both a safe and unsafe entry in a single YAML.
    """
    root = tmp_path / "proj"
    write(
        root / "pipeline.yml",
        """
stages: []
job:
  script:
    - "./scripts/safe.sh"
    - "./scripts/unsafe.sh --flag"
""",
    )
    write(root / "scripts" / "safe.sh", "#!/usr/bin/env bash\necho OK\n")
    write(root / "scripts" / "unsafe.sh", "#!/usr/bin/env bash\necho UNSAFE\n")

    dot = generate_dependency_graph(root, open_graph_in_browser=False)
    d = norm(dot)

    # Only safe is included as an edge from YAML
    assert '"pipeline.yml" -> "scripts/safe.sh";' in d
    assert '"pipeline.yml" -> "scripts/unsafe.sh";' not in d
