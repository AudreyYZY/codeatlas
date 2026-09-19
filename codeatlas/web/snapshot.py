"""Portable read-only explorer exports. No source bodies or absolute paths."""

import json
import sqlite3
from pathlib import Path

from codeatlas.analysis.architecture import explain_file, relationship_graph
from codeatlas.analysis.report import build_report
from codeatlas.analysis.structure import call_graph, project_structure
from codeatlas.graph.dependency import build_dependency_graph
from codeatlas.storage import queries


def snapshot_html(conn: sqlite3.Connection, name: str) -> str:
    report = build_report(conn, name)
    report["root"] = "Offline snapshot · source bodies excluded"
    files = [dict(r) for r in queries.get_files(conn)]
    structure = project_structure(conn)
    forward = build_dependency_graph(conn)
    cycles = {p for c in report["cycles"] for p in c["files"]}
    graph = {
        "nodes": [
            {
                **f,
                "id": f["rel_path"],
                "label": f["rel_path"].rsplit("/", 1)[-1],
                "module": f["rel_path"].split("/")[0],
                "symbols": f["symbol_count"],
                "in_cycle": f["rel_path"] in cycles,
            }
            for f in files
        ],
        "edges": [
            {"source": src, "target": tgt} for src, targets in forward.items() for tgt in targets
        ],
    }
    details = {}
    for f in files:
        imports = [dict(row) for row in queries.get_file_imports(conn, f["id"])]
        for imp in imports:
            imp.pop("resolved_path", None)
        details[f["rel_path"]] = {
            "file": f,
            "source": None,
            "source_status": "snapshot",
            "explanation": explain_file(conn, f["rel_path"]),
            "symbols": [s for s in structure["symbols"] if s["file_id"] == f["id"]],
            "imports": imports,
            "dependencies": [dict(row) for row in queries.get_dependencies(conn, f["id"])],
            "dependents": [dict(row) for row in queries.get_dependents(conn, f["id"])],
        }
    stats = report["stats"]
    payload = {
        "name": name,
        "report": report,
        "files": files,
        "structure": structure,
        "graph": graph,
        "calls": call_graph(conn, limit=stats["symbols"] + stats["calls"] + 1),
        "details": details,
        "relationships": relationship_graph(conn, limit=len(files) + 1, include_tests=True),
    }
    # Escape script delimiters even when a symbol/import contains HTML.
    encoded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
    transport = Path(__file__).with_name("static").joinpath("snapshot.js").read_text()
    template = Path(__file__).with_name("static").joinpath("index.html").read_text()
    css = Path(__file__).with_name("static").joinpath("app.css").read_text()
    app = Path(__file__).with_name("static").joinpath("app.js").read_text()
    reader = Path(__file__).with_name("static").joinpath("reader.js").read_text()
    template = template.replace(
        '<link rel="stylesheet" href="/static/app.css">', "<style>" + css + "</style>"
    )
    template = template.replace('<script src="/static/reader.js"></script>', "")
    return template.replace(
        '<script src="/static/app.js"></script>',
        "<script>window.CODEATLAS_SNAPSHOT="
        + encoded
        + ";\n"
        + transport
        + "\n"
        + app
        + "\n"
        + reader
        + "</script>",
    )
