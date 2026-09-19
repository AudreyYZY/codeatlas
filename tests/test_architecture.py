"""Architecture evidence must survive re-indexing without inventing dataflow."""

import json

import pytest
from fastapi.testclient import TestClient

from codeatlas.analysis.architecture import architecture_graph, explain_file, relationship_graph
from codeatlas.indexer.indexer import index_project
from codeatlas.storage.schema import init_db
from codeatlas.web.server import create_app
from codeatlas.web.snapshot import snapshot_html


@pytest.fixture
def pipeline(tmp_path):
    for folder in ["input", "processing", "output", "app", "tests"]:
        (tmp_path / folder).mkdir()
    (tmp_path / "input/load.py").write_text("def load(path):\n    return path\n")
    (tmp_path / "processing/clean.py").write_text("def clean(raw):\n    return raw\n")
    (tmp_path / "output/save.py").write_text("def save(result):\n    return result\n")
    (tmp_path / "app/main.py").write_text(
        '"""Load, clean and save user data."""\n'
        "from input.load import load\nfrom processing.clean import clean\n"
        "from output.save import save\n"
        'def run(path):\n    """Process one input path."""\n'
        "    raw = load(path)\n    result = clean(raw)\n    return save(result)\n"
    )
    (tmp_path / "tests/test_main.py").write_text(
        'from app.main import run\ndef test_run():\n    run("secret")\n'
    )
    index_project(str(tmp_path), "pipeline", quiet=True)
    conn = init_db("pipeline")
    yield tmp_path, conn
    conn.close()


def test_data_direction_and_provenance(pipeline):
    _, conn = pipeline
    graph = relationship_graph(conn, "data")
    edges = {(e["source"], e["target"], e["kind"]): e for e in graph["edges"]}
    handoff = edges[("input/load.py", "processing/clean.py", "handoff")]
    evidence = handoff["evidence"][0]
    assert evidence["variable"] == "raw" and evidence["via"] == "app/main.py"
    assert evidence["line"] == 8 and evidence["argument_index"] == 0
    assert ("processing/clean.py", "output/save.py", "handoff") in edges
    assert ("input/load.py", "app/main.py", "return") in edges
    assert ("app/main.py", "input/load.py", "argument") in edges
    assert not any("tests/" in n["id"] for n in graph["nodes"])
    assert graph["analysis_files"] == graph["indexed_files"] == 5


def test_module_grouping_and_limits_preserve_focus(pipeline):
    _, conn = pipeline
    graph = architecture_graph(conn, level=1)
    assert {n["id"] for n in graph["nodes"]} == {"input", "processing", "output", "app"}
    assert any(
        e["source"] == "input" and e["target"] == "processing" and e["kind"] == "handoff"
        for e in graph["edges"]
    )
    graph = relationship_graph(conn, "data", "app/main.py", depth=1, limit=1)
    assert graph["nodes"][0]["id"] == "app/main.py" and graph["truncated"]
    assert not graph["edges"]
    assert len(relationship_graph(conn, include_tests=True)["nodes"]) == 5


def test_explanation_contains_specific_implementation(pipeline):
    _, conn = pipeline
    guide = explain_file(conn, "app/main.py")
    assert "Load, clean" in guide["documentation"]
    function = guide["functions"][0]
    assert function["parameters"] == "(path)"
    assert function["documentation"] == "Process one input path."
    assert [c["ref"] for c in function["calls"]] == ["load", "clean", "save"]
    assert any(s["kind"] == "return" and "save(result)" in s["detail"] for s in function["steps"])


@pytest.mark.parametrize(
    "middle",
    [
        "raw = path",
        "if path:\n        raw = path",
        "for item in []:\n        raw = item",
        "raw += path",
    ],
)
def test_overwrite_or_control_join_does_not_invent_handoff(pipeline, middle):
    folder, conn = pipeline
    (folder / "app/main.py").write_text(
        "from input.load import load\nfrom processing.clean import clean\n"
        f"def run(path):\n    raw = load(path)\n    {middle}\n    return clean(raw)\n"
    )
    index_project(str(folder), "pipeline", quiet=True, incremental=True)
    assert not [
        e for e in relationship_graph(conn, "handoff")["edges"] if e["source"] == "input/load.py"
    ]


def test_alias_and_nested_call_handoffs(pipeline):
    folder, conn = pipeline
    (folder / "app/main.py").write_text(
        "from input.load import load as read\nfrom processing.clean import clean\n"
        "def run(path):\n    raw = read(path)\n    alias = raw\n    clean(alias)\n"
        "    return clean(read(path))\n"
    )
    index_project(str(folder), "pipeline", quiet=True, incremental=True)
    edges = relationship_graph(conn, "handoff")["edges"]
    edge = next(e for e in edges if e["source"] == "input/load.py")
    assert edge["count"] == 2
    assert {e["variable"] for e in edge["evidence"]} == {"alias", None}


def test_shadowed_import_is_unresolved(pipeline):
    folder, conn = pipeline
    (folder / "app/main.py").write_text(
        "from input.load import load\nfrom processing.clean import clean\n"
        'def run(load):\n    raw = load("hidden-token")\n    return clean(raw)\n'
    )
    index_project(str(folder), "pipeline", quiet=True, incremental=True)
    graph = relationship_graph(conn, "data")
    assert not any(e["source"] == "input/load.py" for e in graph["edges"])
    assert "hidden-token" not in json.dumps(
        explain_file(conn, "app/main.py")["functions"][0]["calls"]
    )


def test_ts_async_namespaces_and_named_aliases(tmp_path):
    (tmp_path / "load.ts").write_text("export async function load(path: string) { return path; }")
    (tmp_path / "save.ts").write_text("export function save(data: string) { return data; }")
    (tmp_path / "main.ts").write_text(
        'import * as input from "./load";\nimport {save as persist} from "./save";\n'
        "export const run = async (path: string) => {\n"
        "  const data = await input.load(path);\n  return persist(data);\n};\n"
    )
    index_project(str(tmp_path), "ts-pipeline", quiet=True)
    conn = init_db("ts-pipeline")
    try:
        graph = relationship_graph(conn, "data")
        handoff = next(e for e in graph["edges"] if e["kind"] == "handoff")
        assert handoff["source"] == "load.ts" and handoff["target"] == "save.ts"
        assert handoff["evidence"][0]["variable"] == "data"
        assert explain_file(conn, "main.ts")["functions"][0]["name"] == "run"
    finally:
        conn.close()


def test_incremental_missing_analysis_and_removed_files(pipeline):
    folder, conn = pipeline
    conn.execute("DELETE FROM file_analyses")
    conn.commit()
    stats = index_project(str(folder), "pipeline", incremental=True, quiet=True)
    assert stats["reused"] == 0
    assert conn.execute("SELECT COUNT(*) FROM file_analyses").fetchone()[0] == 5
    (folder / "tests/test_main.py").unlink()
    index_project(str(folder), "pipeline", incremental=True, quiet=True)
    assert conn.execute("SELECT COUNT(*) FROM file_analyses").fetchone()[0] == 4


def test_api_validation_and_stale_source(pipeline):
    folder, _ = pipeline
    client = TestClient(create_app())
    assert client.get("/api/projects/pipeline/architecture?level=0").status_code == 422
    assert client.get("/api/projects/pipeline/relationships?kind=bogus").status_code == 422
    assert client.get("/api/projects/pipeline/relationships?focus=no.py").status_code == 404
    data = client.get("/api/projects/pipeline/file?path=app/main.py").json()
    assert data["source_status"] == "indexed" and data["explanation"]["analysis_available"]
    (folder / "app/main.py").write_text("def different(): pass\n")
    assert (
        client.get("/api/projects/pipeline/file?path=app/main.py").json()["source_status"]
        == "changed"
    )


def test_snapshot_contains_reading_evidence(pipeline):
    _, conn = pipeline
    html = snapshot_html(conn, "pipeline")
    assert "reader.js" not in html
    assert "input/load.py" in html and "Process one input path." in html
    assert "function loadArchitecture" in html


def test_straight_line_handoff_inside_branch(pipeline):
    folder, conn = pipeline
    (folder / "app/main.py").write_text(
        "from input.load import load\nfrom processing.clean import clean\n"
        "def run(path):\n    if path:\n        raw = load(path)\n        clean(raw)\n"
        "    clean(raw)\n"
    )
    index_project(str(folder), "pipeline", incremental=True, quiet=True)
    edges = relationship_graph(conn, "handoff")["edges"]
    assert len(edges) == 1 and edges[0]["count"] == 1
    assert edges[0]["evidence"][0]["line"] == 6


def test_ts_top_level_and_local_scope(tmp_path):
    (tmp_path / "main.ts").write_text(
        "export function run() { const local = 1; return local; }\n"
        "export const asyncRun = async () => { const privateValue = 2; return privateValue; };\n"
    )
    index_project(str(tmp_path), "ts-scope", quiet=True)
    conn = init_db("ts-scope")
    try:
        symbols = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM symbols")}
        assert symbols["run"]["is_export"] and symbols["run"]["parent_symbol"] is None
        assert symbols["local"]["parent_symbol"] == "run" and not symbols["local"]["is_export"]
        assert symbols["asyncRun"]["is_async"]
        assert symbols["privateValue"]["parent_symbol"] == "asyncRun"
    finally:
        conn.close()


def test_nested_definition_shadows_import(pipeline):
    folder, conn = pipeline
    (folder / "app/main.py").write_text(
        "from input.load import load\nfrom processing.clean import clean\n"
        "def run(path):\n    def load(path): return path\n"
        "    raw = load(path)\n    return clean(raw)\n"
    )
    index_project(str(folder), "pipeline", incremental=True, quiet=True)
    assert not any(
        e["source"] == "input/load.py" for e in relationship_graph(conn, "data")["edges"]
    )
