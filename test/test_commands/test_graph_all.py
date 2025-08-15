from __future__ import annotations

from pathlib import Path

import pytest

from bash2gitlab.commands import graph_all as graph_mod

# ---------- small helpers -----------------------------------------------------


def _w(p: Path, content: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _norm_rel(root: Path, p: Path) -> str:
    """Forward-slash relative path for robust assertions on any OS."""
    return str(p.resolve().relative_to(root.resolve())).replace("\\", "/")


# ---------- parse_shell_script_dependencies -----------------------------------


def test_parse_script_dependencies_recurses_and_skips_outside_root(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = tmp_path
    a = _w(
        root / "a.sh",
        """
#!/usr/bin/env bash
. ./b.sh
# an attempt to escape root:
source ../outside.sh
""".strip(),
    )
    _b = _w(
        root / "b.sh",
        """
#!/usr/bin/env bash
source ./lib/c.sh
""".strip(),
    )
    _c = _w(root / "lib" / "c.sh", "#!/usr/bin/env bash\necho c\n")

    graph: dict[Path, set[Path]] = {}
    processed: set[Path] = set()

    graph_mod.parse_shell_script_dependencies(a, root, graph, processed)

    # a depends on b, not on outside.sh
    assert a in graph
    assert (root / "b.sh").resolve() in graph[a]
    assert all("outside.sh" not in str(p) for p in graph[a])

    # b depends on c via recursion
    assert (root / "b.sh").resolve() in graph
    assert (root / "lib" / "c.sh").resolve() in graph[(root / "b.sh").resolve()]

    # we logged an error for the outside reference
    assert any("Refusing to trace source" in r.message for r in caplog.records)


def test_parse_script_dependencies_warns_on_missing_file(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    root = tmp_path
    a = _w(root / "a.sh", "source ./missing.sh\n")
    graph: dict[Path, set[Path]] = {}
    processed: set[Path] = set()

    graph_mod.parse_shell_script_dependencies(a, root, graph, processed)

    # Dependency edge exists, but the missing file isn't parsed further
    missing = (a.parent / "missing.sh").resolve()
    assert missing in graph[a]
    assert any("Dependency not found and will be skipped" in r.message for r in caplog.records)


# ---------- find_script_references_in_node ------------------------------------


def test_find_script_references_traces_yaml_to_script_then_sources(tmp_path: Path):
    root = tmp_path
    yaml_path = _w(root / "ci" / "pipeline.yml", "placeholder\n")
    run = _w(root / "ci" / "scripts" / "run.sh", "#!/usr/bin/env bash\n. ../lib/helper.sh\n")
    helper = _w(root / "ci" / "lib" / "helper.sh", "#!/usr/bin/env bash\necho ok\n")

    node = {
        "stages": ["build"],
        "job": {
            "script": [
                "bash scripts/run.sh",  # should be detected
                "echo not-a-script-line",  # ignored by extract_script_path
            ]
        },
    }

    graph: dict[Path, set[Path]] = {}
    processed: set[Path] = set()

    graph_mod.find_script_references_in_node(node, yaml_path, root, graph, processed)

    assert yaml_path in graph
    assert run.resolve() in graph[yaml_path]
    # transitive source discovered
    assert run.resolve() in graph
    assert helper.resolve() in graph[run.resolve()]


def test_generate_dependency_graph_no_yaml_returns_empty(tmp_path: Path):
    root = tmp_path / "empty"
    root.mkdir(parents=True, exist_ok=True)
    assert graph_mod.generate_dependency_graph(root) == ""


def test_generate_dependency_graph_handles_yaml_error(tmp_path: Path):
    root = tmp_path / "bad"
    root.mkdir(parents=True, exist_ok=True)
    bad_yaml = _w(root / "oops.yml", "stages: [build  # missing closing bracket causes YAML error\n")

    dot = graph_mod.generate_dependency_graph(root)

    # Graph still produced with YAML node but no edges
    bad_rel = _norm_rel(root, bad_yaml)
    assert f'"{bad_rel}" [label="{bad_rel}"]' in dot
    # Likely no edges, but be tolerant — just ensure DOT header/footer exist
    assert dot.startswith("digraph bash2gitlab {")
    assert dot.strip().endswith("}")


# ---------- additional edge cases ---------------------------------------------


def test_yaml_with_nested_collections_and_multiple_scripts(tmp_path: Path):
    root = tmp_path
    yaml_path = _w(root / "ci" / "deep.yml", "placeholder\n")

    # build out real scripts
    s1 = _w(root / "ci" / "scripts" / "a.sh", "#!/usr/bin/env bash\n")
    s2 = _w(root / "ci" / "scripts" / "b.sh", "#!/usr/bin/env bash\n. ./c.sh\n")
    s3 = _w(root / "ci" / "scripts" / "c.sh", "#!/usr/bin/env bash\n")

    node = {
        "before_script": ["bash scripts/a.sh"],
        "script": [["bash scripts/b.sh", "echo nope"], "echo ok"],
        "after_script": ["./scripts/a.sh"],  # acceptable direct path if extract_script_path allows it
    }

    graph: graph_mod.Graph = {}
    processed: set[Path] = set()
    graph_mod.find_script_references_in_node(node, yaml_path, root, graph, processed)

    assert s1.resolve() in graph[yaml_path]
    assert s2.resolve() in graph[yaml_path]
    # transitive edge from b.sh to c.sh
    assert s2.resolve() in graph and s3.resolve() in graph[s2.resolve()]
