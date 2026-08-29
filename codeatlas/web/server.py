"""
FastAPI backend for the CodeAtlas web UI.

Runs entirely on localhost against the same SQLite indexes the CLI writes, so
the web UI is a view over your existing knowledge base — not a second store.

Security note: this server can index and read any directory the user running it
can read, which is the point of a local dev tool. It binds to 127.0.0.1 by
default; do not expose it on a public interface.
"""

import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
import zipfile

from codeatlas.analysis.report import build_report, report_to_markdown
from codeatlas.config import get_data_home, get_project_dir, list_projects, sanitize_project_name
from codeatlas.graph.callgraph import find_call_chain
from codeatlas.graph.cycles import find_cycles, shortest_cycle_path
from codeatlas.graph.dependency import build_dependency_graph
from codeatlas.graph.mermaid import calls_to_mermaid, deps_to_mermaid
from codeatlas.indexer.indexer import index_project
from codeatlas.storage import queries

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Uploaded archives are extracted here so they survive the request and can be
# re-indexed later.
UPLOAD_ROOT = os.path.join(get_data_home(), "uploads")

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class JobStore:
    """In-memory registry of running index jobs (one process, one user)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, project: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "project": project,
                "state": "queued",
                "done": 0,
                "total": 0,
                "message": "Queued",
                "started_at": time.time(),
                "stats": None,
                "error": None,
            }
        return job_id

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


def _db_path(project: str) -> str:
    return os.path.join(get_project_dir(project), "index.db")


def _open(project: str) -> sqlite3.Connection:
    from fastapi import HTTPException

    path = _db_path(project)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"No index for project '{project}'")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _safe_extract(zip_path: str, dest: str) -> None:
    """Extract a zip, refusing entries that escape the destination (zip-slip)."""
    with zipfile.ZipFile(zip_path) as zf:
        total = sum(info.file_size for info in zf.infolist())
        if total > MAX_UPLOAD_BYTES * 5:
            raise ValueError("Archive expands to more than the allowed size")
        dest_abs = os.path.abspath(dest)
        for info in zf.infolist():
            target = os.path.abspath(os.path.join(dest_abs, info.filename))
            if not target.startswith(dest_abs + os.sep) and target != dest_abs:
                raise ValueError(f"Unsafe path in archive: {info.filename}")
        zf.extractall(dest_abs)


def _strip_single_root(path: str) -> str:
    """GitHub zips wrap everything in one folder; index that folder instead."""
    entries = [e for e in os.listdir(path) if not e.startswith("__MACOSX")]
    if len(entries) == 1 and os.path.isdir(os.path.join(path, entries[0])):
        return os.path.join(path, entries[0])
    return path


def create_app():  # noqa: C901 — route registration is naturally long
    from fastapi import FastAPI, File, HTTPException, Query, UploadFile
    from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    app = FastAPI(title="CodeAtlas", version="0.3.0", docs_url="/api/docs")
    jobs = JobStore()

    class IndexRequest(BaseModel):
        path: str
        name: str | None = None
        incremental: bool = True

    # ── Projects ──

    @app.get("/api/projects")
    def api_projects():
        out = []
        for name in list_projects():
            path = _db_path(name)
            if not os.path.exists(path):
                continue
            try:
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                stats = queries.get_stats(conn)
                root = conn.execute("SELECT value FROM meta WHERE key='project_root'").fetchone()
                indexed_at = conn.execute(
                    "SELECT value FROM meta WHERE key='indexed_at'"
                ).fetchone()
                conn.close()
            except sqlite3.Error:
                continue
            out.append(
                {
                    "name": name,
                    "root": root[0] if root else "",
                    "indexed_at": indexed_at[0] if indexed_at else "",
                    **stats,
                }
            )
        return {"projects": sorted(out, key=lambda p: p["name"])}

    @app.delete("/api/projects/{project}")
    def api_delete_project(project: str):
        project = sanitize_project_name(project)
        directory = get_project_dir(project)
        if not os.path.isdir(directory):
            raise HTTPException(status_code=404, detail="No such project")
        shutil.rmtree(directory)
        return {"deleted": project}

    # ── Indexing ──

    def _run_index(job_id: str, path: str, name: str, incremental: bool) -> None:
        def progress(event: str, payload: dict) -> None:
            if event == "scanned":
                jobs.update(
                    job_id,
                    state="running",
                    total=payload.get("count", 0),
                    message=f"Found {payload.get('count', 0)} files",
                )
            elif event == "progress":
                jobs.update(
                    job_id,
                    state="running",
                    done=payload.get("done", 0),
                    total=payload.get("total", 0),
                    message=f"Parsing {payload.get('file', '')}",
                )

        try:
            stats = index_project(
                path, name, incremental=incremental, progress=progress, quiet=True
            )
            jobs.update(job_id, state="done", stats=stats, message="Index complete")
        except Exception as e:  # noqa: BLE001 — surface any failure to the UI
            jobs.update(job_id, state="error", error=f"{type(e).__name__}: {e}")

    def _start_index(path: str, name: str, incremental: bool) -> dict:
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail=f"Not a directory: {path}")
        name = sanitize_project_name(name or os.path.basename(os.path.abspath(path)))
        job_id = jobs.create(name)
        thread = threading.Thread(
            target=_run_index, args=(job_id, path, name, incremental), daemon=True
        )
        thread.start()
        return {"job": job_id, "project": name}

    @app.post("/api/index")
    def api_index(req: IndexRequest):
        path = os.path.abspath(os.path.expanduser(req.path.strip()))
        return _start_index(path, req.name or "", req.incremental)

    @app.post("/api/upload")
    async def api_upload(file: UploadFile = File(...), name: str | None = None):
        if not file.filename or not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Please upload a .zip archive")

        project = sanitize_project_name(
            name or os.path.splitext(os.path.basename(file.filename))[0]
        )
        os.makedirs(UPLOAD_ROOT, exist_ok=True)
        dest = os.path.join(UPLOAD_ROOT, project)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)

        size = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    tmp.close()
                    os.unlink(tmp.name)
                    raise HTTPException(status_code=413, detail="Archive too large (200 MB cap)")
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            _safe_extract(tmp_path, dest)
        except (zipfile.BadZipFile, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        finally:
            os.unlink(tmp_path)

        root = _strip_single_root(dest)
        return _start_index(root, project, incremental=False)

    @app.get("/api/jobs/{job_id}")
    def api_job(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown job")
        return job

    # ── Reading an index ──

    @app.get("/api/projects/{project}/report")
    def api_report(project: str):
        conn = _open(sanitize_project_name(project))
        try:
            return build_report(conn, project)
        finally:
            conn.close()

    @app.get("/api/projects/{project}/report.md", response_class=PlainTextResponse)
    def api_report_md(project: str):
        conn = _open(sanitize_project_name(project))
        try:
            return report_to_markdown(build_report(conn, project))
        finally:
            conn.close()

    @app.get("/api/projects/{project}/files")
    def api_files(project: str):
        conn = _open(sanitize_project_name(project))
        try:
            return {"files": _rows(queries.get_files(conn))}
        finally:
            conn.close()

    @app.get("/api/projects/{project}/file")
    def api_file(project: str, path: str = Query(...)):
        conn = _open(sanitize_project_name(project))
        try:
            row = queries.get_file_by_path(conn, path)
            if row is None:
                raise HTTPException(status_code=404, detail=f"No indexed file '{path}'")
            file_id = row["id"]
            source = None
            try:
                if os.path.isfile(row["path"]) and os.path.getsize(row["path"]) < 400_000:
                    with open(row["path"], encoding="utf-8", errors="replace") as f:
                        source = f.read()
            except OSError:
                source = None
            return {
                "file": dict(row),
                "symbols": _rows(
                    conn.execute(
                        "SELECT * FROM symbols WHERE file_id = ? ORDER BY line_start",
                        (file_id,),
                    ).fetchall()
                ),
                "imports": _rows(queries.get_file_imports(conn, file_id)),
                "dependencies": _rows(queries.get_dependencies(conn, file_id)),
                "dependents": _rows(queries.get_dependents(conn, file_id)),
                "source": source,
            }
        finally:
            conn.close()

    @app.get("/api/projects/{project}/graph")
    def api_graph(
        project: str,
        focus: str | None = None,
        depth: int = 2,
        direction: str = "both",
        limit: int = 400,
    ):
        """Nodes and edges for the dependency map, ready for force layout."""
        conn = _open(sanitize_project_name(project))
        try:
            forward = build_dependency_graph(conn)
            file_rows = {r["rel_path"]: dict(r) for r in queries.get_files(conn)}

            if focus:
                reverse: dict[str, list[str]] = {}
                for src, targets in forward.items():
                    for tgt in targets:
                        reverse.setdefault(tgt, []).append(src)

                keep = {focus}
                frontier = {focus}
                for _ in range(max(1, depth)):
                    nxt: set[str] = set()
                    for node in frontier:
                        if direction in ("both", "downstream"):
                            nxt.update(forward.get(node, []))
                        if direction in ("both", "upstream"):
                            nxt.update(reverse.get(node, []))
                    nxt -= keep
                    keep |= nxt
                    frontier = nxt
                    if not frontier:
                        break
            else:
                keep = set(file_rows)

            # Cap the node count so the browser stays responsive; keep the
            # best-connected files.
            if len(keep) > limit:
                degree = {
                    node: len(forward.get(node, []))
                    + sum(1 for targets in forward.values() if node in targets)
                    for node in keep
                }
                keep = set(sorted(keep, key=lambda n: -degree.get(n, 0))[:limit])

            cycle_files: set[str] = set()
            for component in find_cycles(conn):
                cycle_files.update(component)

            nodes = []
            for path in sorted(keep):
                info = file_rows.get(path, {})
                nodes.append(
                    {
                        "id": path,
                        "label": path.rsplit("/", 1)[-1],
                        "module": path.split("/")[0] if "/" in path else "(root)",
                        "language": info.get("language", ""),
                        "lines": info.get("lines", 0),
                        "symbols": info.get("symbol_count", 0),
                        "in_degree": info.get("in_degree", 0),
                        "out_degree": info.get("out_degree", 0),
                        "in_cycle": path in cycle_files,
                        "is_focus": path == focus,
                    }
                )

            edges = [
                {"source": src, "target": tgt}
                for src, targets in forward.items()
                if src in keep
                for tgt in targets
                if tgt in keep
            ]
            return {"nodes": nodes, "edges": edges, "truncated": len(keep) >= limit}
        finally:
            conn.close()

    @app.get("/api/projects/{project}/search")
    def api_search(project: str, q: str = Query(..., min_length=1), limit: int = 40):
        conn = _open(sanitize_project_name(project))
        try:
            symbols = _rows(queries.search_symbols(conn, q, limit))
            files = _rows(
                conn.execute(
                    "SELECT id, rel_path, language, lines FROM files "
                    "WHERE rel_path LIKE ? ORDER BY LENGTH(rel_path) LIMIT ?",
                    (f"%{q}%", limit),
                ).fetchall()
            )
            return {"symbols": symbols, "files": files}
        finally:
            conn.close()

    @app.get("/api/projects/{project}/symbol")
    def api_symbol(project: str, name: str = Query(...), depth: int = 3):
        conn = _open(sanitize_project_name(project))
        try:
            matches = _rows(queries.get_symbol_by_name(conn, name))
            if not matches:
                raise HTTPException(status_code=404, detail=f"No symbol '{name}'")
            primary = matches[0]
            chain = [
                {"depth": d, "symbol": sym, "callees": callees}
                for d, sym, callees in find_call_chain(conn, name, depth)
            ]
            return {
                "matches": matches,
                "primary": primary,
                "callers": _rows(queries.find_callers(conn, name)),
                "callees": _rows(queries.find_callees(conn, primary["id"])),
                "chain": chain,
                "mermaid": calls_to_mermaid(conn, name, depth, fenced=False),
            }
        finally:
            conn.close()

    @app.get("/api/projects/{project}/cycles")
    def api_cycles(project: str):
        conn = _open(sanitize_project_name(project))
        try:
            graph = build_dependency_graph(conn)
            components = find_cycles(conn)
            return {
                "cycles": [{"files": c, "path": shortest_cycle_path(graph, c)} for c in components]
            }
        finally:
            conn.close()

    @app.get("/api/projects/{project}/mermaid", response_class=PlainTextResponse)
    def api_mermaid(
        project: str, path: str = Query(...), direction: str = "downstream", depth: int = 3
    ):
        conn = _open(sanitize_project_name(project))
        try:
            return deps_to_mermaid(conn, path, direction, depth, fenced=True)
        finally:
            conn.close()

    # ── Static frontend ──

    @app.get("/")
    def root():
        index_html = os.path.join(STATIC_DIR, "index.html")
        if not os.path.exists(index_html):
            return JSONResponse(
                {"error": "UI assets missing", "hint": "Reinstall codeatlas"}, status_code=500
            )
        return FileResponse(index_html)

    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
