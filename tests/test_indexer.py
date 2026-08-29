"""End-to-end indexing tests: scan → parse → resolve → store."""

import os
import sqlite3

from codeatlas.config import get_project_dir
from codeatlas.graph.cycles import find_cycles
from codeatlas.indexer.indexer import index_project
from codeatlas.storage import queries


def _open(name):
    conn = sqlite3.connect(os.path.join(get_project_dir(name), "index.db"))
    conn.row_factory = sqlite3.Row
    return conn


def test_index_ts_project_resolves_dependencies(ts_project):
    stats = index_project(ts_project, "tsfix", quiet=True)
    assert stats["files"] == 4
    assert stats["errors"] == 0

    conn = _open("tsfix")
    edges = {(e["source_rel"], e["target_rel"]) for e in queries.get_all_dependencies(conn)}
    assert ("src/index.ts", "src/components/Map.ts") in edges
    assert ("src/index.ts", "src/lib/util.ts") in edges
    assert ("src/components/Map.ts", "src/lib/util.ts") in edges
    # re-export edge
    assert ("src/lib/index.ts", "src/lib/util.ts") in edges
    conn.close()


def test_external_packages_do_not_create_dependency_edges(ts_project):
    index_project(ts_project, "tsext", quiet=True)
    conn = _open("tsext")
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM dependency_edges WHERE resolved = 0"
    ).fetchone()[0]
    assert unresolved == 0, "react / @scope/pkg must not look like broken internal imports"
    conn.close()


def test_dependency_edges_are_deduplicated(ts_project):
    """Six named imports from one module must be one edge, not six."""
    with open(os.path.join(ts_project, "src", "many.ts"), "w", encoding="utf-8") as f:
        f.write('import { a, b, c, d } from "./lib/util";\nexport const x = 1;\n')
    index_project(ts_project, "tsdedup", quiet=True)
    conn = _open("tsdedup")
    row = conn.execute(
        """SELECT weight FROM dependency_edges de
           JOIN files s ON de.source_file_id = s.id
           JOIN files t ON de.target_file_id = t.id
           WHERE s.rel_path = 'src/many.ts' AND t.rel_path = 'src/lib/util.ts'"""
    ).fetchone()
    assert row is not None
    assert row["weight"] == 4
    conn.close()


def test_cycle_detection(ts_project):
    index_project(ts_project, "tscycle", quiet=True)
    conn = _open("tscycle")
    cycles = find_cycles(conn)
    assert len(cycles) == 1
    assert set(cycles[0]) == {"src/components/Map.ts", "src/lib/util.ts"}
    conn.close()


def test_python_project_indexes(py_project):
    stats = index_project(py_project, "pyproj", quiet=True)
    assert stats["errors"] == 0
    conn = _open("pyproj")
    edges = {(e["source_rel"], e["target_rel"]) for e in queries.get_all_dependencies(conn)}
    assert (os.path.join("pkg", "core.py"), os.path.join("pkg", "sub", "helpers.py")) in edges
    assert (os.path.join("pkg", "sub", "helpers.py"), os.path.join("pkg", "core.py")) in edges

    names = {r["name"] for r in queries.list_symbols(conn)}
    assert {"Engine", "run", "start", "assist", "CONST"} <= names
    conn.close()


def test_incremental_reindex_matches_full_reindex(py_project):
    full = index_project(py_project, "pyinc", quiet=True)
    incremental = index_project(py_project, "pyinc", incremental=True, quiet=True)
    assert incremental["reused"] == full["files"]
    for key in ("files", "symbols", "imports", "calls", "deps"):
        assert incremental[key] == full[key], key


def test_incremental_picks_up_a_changed_file(py_project):
    index_project(py_project, "pychange", quiet=True)
    with open(os.path.join(py_project, "pkg", "core.py"), "a", encoding="utf-8") as f:
        f.write("\ndef added_later():\n    return 1\n")
    stats = index_project(py_project, "pychange", incremental=True, quiet=True)
    assert stats["reused"] < stats["files"]
    conn = _open("pychange")
    names = {r["name"] for r in queries.list_symbols(conn)}
    assert "added_later" in names
    conn.close()


def test_reindex_removes_deleted_files(py_project):
    index_project(py_project, "pydel", quiet=True)
    os.remove(os.path.join(py_project, "pkg", "sub", "helpers.py"))
    stats = index_project(py_project, "pydel", incremental=True, quiet=True)
    conn = _open("pydel")
    paths = {r["rel_path"] for r in queries.get_files(conn)}
    assert not any(p.endswith("helpers.py") for p in paths)
    assert stats["files"] == len(paths)
    conn.close()
