"""Tests for the web API. Skipped when the optional web extras aren't installed."""

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from codeatlas.indexer.indexer import index_project  # noqa: E402
from codeatlas.web.server import _safe_extract, _strip_single_root, create_app  # noqa: E402


@pytest.fixture
def client(ts_project):
    index_project(ts_project, "webproj", quiet=True)
    return TestClient(create_app())


def test_index_page_served(client):
    assert client.get("/").status_code == 200


def test_projects_listed(client):
    names = [p["name"] for p in client.get("/api/projects").json()["projects"]]
    assert "webproj" in names


def test_report_has_narrative_and_health(client):
    report = client.get("/api/projects/webproj/report").json()
    assert report["stats"]["files"] == 4
    assert report["narrative"] and report["health"]
    assert len(report["cycles"]) == 1


def test_report_markdown(client):
    text = client.get("/api/projects/webproj/report.md").text
    assert "architecture report" in text


def test_graph_nodes_and_edges(client):
    graph = client.get("/api/projects/webproj/graph").json()
    ids = {n["id"] for n in graph["nodes"]}
    assert "src/index.ts" in ids
    assert any(e["source"] == "src/index.ts" for e in graph["edges"])
    assert any(n["in_cycle"] for n in graph["nodes"])


def test_graph_focus_narrows_the_view(client):
    graph = client.get(
        "/api/projects/webproj/graph", params={"focus": "src/lib/util.ts", "depth": 1}
    ).json()
    ids = {n["id"] for n in graph["nodes"]}
    assert "src/lib/util.ts" in ids
    assert len(ids) < 4 or "src/index.ts" in ids


def test_file_detail(client):
    data = client.get("/api/projects/webproj/file", params={"path": "src/index.ts"}).json()
    assert data["file"]["rel_path"] == "src/index.ts"
    assert any(s["name"] == "main" for s in data["symbols"])
    assert data["source"].startswith("import")


def test_search(client):
    data = client.get("/api/projects/webproj/search", params={"q": "help"}).json()
    assert any(s["name"] == "helper" for s in data["symbols"])


def test_symbol_detail(client):
    data = client.get("/api/projects/webproj/symbol", params={"name": "helper"}).json()
    assert data["primary"]["name"] == "helper"
    assert "mermaid" in data


def test_unknown_project_is_404(client):
    assert client.get("/api/projects/nope/report").status_code == 404


def test_index_rejects_a_bad_path(client):
    res = client.post("/api/index", json={"path": "/definitely/not/here"})
    assert res.status_code == 400


def test_zip_slip_is_rejected(tmp_path):
    import zipfile

    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "nope")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError):
        _safe_extract(str(archive), str(dest))


def test_single_root_is_stripped(tmp_path):
    inner = tmp_path / "repo-main"
    inner.mkdir()
    (inner / "a.ts").write_text("export const a = 1;")
    assert _strip_single_root(str(tmp_path)) == str(inner)


def test_structure_and_callgraph_endpoints(client):
    structure = client.get("/api/projects/webproj/structure").json()
    assert structure["files"] == 4
    graph = client.get("/api/projects/webproj/callgraph").json()
    assert any(e["resolution"] == "import" for e in graph["edges"])
    assert graph["shown_nodes"] == len(graph["nodes"])


def test_graph_limits_and_unknown_focus(client):
    root = "/api/projects/webproj/"
    assert client.get(root + "graph", params={"limit": 0}).status_code == 422
    assert client.get(root + "callgraph", params={"depth": 99}).status_code == 422
    assert client.get(root + "graph", params={"direction": "invalid"}).status_code == 422
    assert client.get(root + "graph", params={"focus": "missing.py"}).status_code == 404
    assert client.get(root + "callgraph", params={"focus": -1}).status_code == 404
    full = client.get(root + "graph", params={"limit": 4}).json()
    assert not full["truncated"] and full["total_nodes"] == 4
    focused = client.get(root + "graph", params={"focus": "src/index.ts", "limit": 1}).json()
    assert focused["nodes"][0]["is_focus"] and focused["truncated"]


def test_job_store_prevents_overlapping_indexing():
    from codeatlas.web.server import JobStore

    jobs = JobStore()
    first = jobs.create("same")
    with pytest.raises(ValueError, match="already indexing"):
        jobs.create("same")
    jobs.update(first, state="done")
    assert jobs.create("same") != first
    assert jobs.create("other")
