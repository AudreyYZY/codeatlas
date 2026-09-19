"""Regression checks for declaration identity, uncertainty and portable exports."""

import json
import re

from codeatlas.analysis.structure import call_graph, project_structure
from codeatlas.indexer.indexer import index_project
from codeatlas.storage.schema import init_db
from codeatlas.web.snapshot import snapshot_html


def test_directory_tree_and_method_outline(py_project):
    index_project(py_project, "outline", quiet=True)
    conn = init_db("outline")
    try:
        data = project_structure(conn)
        assert data["tree"]["children"][0]["name"] == "pkg"
        run = next(s for s in data["symbols"] if s["name"] == "run")
        assert run["parent_symbol"] == "Engine"
    finally:
        conn.close()


def test_import_alias_resolution_does_not_merge_same_names(tmp_path):
    (tmp_path / "a.py").write_text("def work():\n    return 1\n")
    (tmp_path / "b.py").write_text("def work():\n    return 2\n")
    (tmp_path / "main.py").write_text(
        "from a import work as chosen\ndef run():\n    return chosen()\n"
    )
    index_project(str(tmp_path), "identity", quiet=True)
    conn = init_db("identity")
    try:
        graph = call_graph(conn)
        run = next(n for n in graph["nodes"] if n["label"] == "run")
        edge = next(e for e in graph["edges"] if e["source"] == run["id"])
        target = next(n for n in graph["nodes"] if n["id"] == edge["target"])
        assert target["path"] == "a.py" and edge["resolution"] == "import"
        work = [n for n in graph["nodes"] if n["label"] == "work"]
        assert len(work) == 2 and len({n["id"] for n in work}) == 2
        focused = call_graph(conn, focus=run["symbol_id"], depth=0, limit=1)
        assert focused["nodes"][0]["id"] == run["id"]
        assert not focused["edges"] and not focused["truncated"]
        limited = call_graph(conn, focus=run["symbol_id"], limit=1)
        assert limited["truncated"] and limited["nodes"][0]["is_focus"]
    finally:
        conn.close()


def test_member_calls_stay_unresolved(py_project):
    index_project(py_project, "dynamic", quiet=True)
    conn = init_db("dynamic")
    try:
        graph = call_graph(conn)
        run = next(n for n in graph["nodes"] if n["label"] == "run" and n["unresolved"])
        assert run["kind"] == "member / dynamic"
        assert any(
            e["target"] == run["id"] and e["resolution"] == "unresolved" for e in graph["edges"]
        )
    finally:
        conn.close()


def test_snapshot_excludes_source_and_absolute_paths(ts_project):
    index_project(ts_project, "portable", quiet=True)
    conn = init_db("portable")
    try:
        html = snapshot_html(conn, "portable")
        assert ts_project not in html
        assert "CODEATLAS_SNAPSHOT=" in html
        encoded = re.search(r"CODEATLAS_SNAPSHOT=(.*?);\n", html).group(1)
        payload = json.loads(encoded)
        assert all(d["source"] is None for d in payload["details"].values())
        assert payload["calls"]["nodes"]
        conn.execute("UPDATE symbols SET signature=?", ("</script><script>evil()</script>",))
        escaped = snapshot_html(conn, "portable")
        assert "</script><script>evil()" not in escaped
    finally:
        conn.close()


def test_same_name_methods_keep_their_own_calls(tmp_path):
    (tmp_path / "main.py").write_text(
        "def one(): return 1\ndef two(): return 2\n"
        "class A:\n    def run(self): return one()\n"
        "class B:\n    def run(self): return two()\n"
    )
    index_project(str(tmp_path), "methods", quiet=True)
    conn = init_db("methods")
    try:
        graph = call_graph(conn)
        runs = [n for n in graph["nodes"] if n["label"] == "run" and not n["unresolved"]]
        assert len(runs) == 2
        targets = []
        for run in runs:
            edge = next(e for e in graph["edges"] if e["source"] == run["id"])
            targets.append(next(n["label"] for n in graph["nodes"] if n["id"] == edge["target"]))
        assert set(targets) == {"one", "two"}
        clean = call_graph(conn, include_unresolved=False)
        assert all(not n["unresolved"] for n in clean["nodes"])
    finally:
        conn.close()
