"""Indexer orchestrator: scan → parse → resolve → insert."""

import hashlib
import os
import sqlite3
import time
from collections.abc import Callable

from codeatlas.config import detect_project_name
from codeatlas.indexer.parser import parse_file
from codeatlas.indexer.resolver import (
    parse_tsconfig_aliases,
    resolve_import_path,
    resolve_python_import,
)
from codeatlas.scanner.scanner import scan_files
from codeatlas.storage.schema import get_meta, init_db, set_meta

ProgressFn = Callable[[str, dict], None]


def _to_posix(path: str) -> str:
    return path.replace("\\", "/")


def _file_hash(path: str) -> str:
    """Content hash used to decide whether a file needs re-parsing."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _clear_project_data(conn: sqlite3.Connection) -> None:
    """Remove all data from a previous index run."""
    for table in ("dependency_edges", "call_edges", "imports", "symbols", "files"):
        conn.execute(f"DELETE FROM {table}")


def _delete_file_rows(conn: sqlite3.Connection, file_id: int) -> None:
    """Remove everything derived from one file (both directions)."""
    conn.execute("DELETE FROM dependency_edges WHERE source_file_id = ?", (file_id,))
    conn.execute("DELETE FROM dependency_edges WHERE target_file_id = ?", (file_id,))
    conn.execute("DELETE FROM call_edges WHERE caller_file_id = ?", (file_id,))
    conn.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))


def _insert_file(conn: sqlite3.Connection, result: dict) -> int:
    cur = conn.execute(
        """INSERT INTO files (path, rel_path, language, lines, bytes, mtime, content_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            result["path"],
            result["rel_path"],
            result["language"],
            result["lines"],
            result["bytes"],
            result.get("mtime", 0.0),
            result.get("content_hash"),
        ),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def _insert_symbols(conn: sqlite3.Connection, file_id: int, symbols: list[dict]) -> dict[str, int]:
    """Insert symbols and return a ``name → symbol_id`` map for this file.

    When a name is declared more than once in a file the first declaration
    wins, which matches how call-edge attribution reads.
    """
    sym_id_map: dict[str, int] = {}
    for sym in symbols:
        cur = conn.execute(
            """INSERT INTO symbols
               (file_id, name, kind, line_start, line_end, signature,
                is_export, is_default_export, is_async,
                parent_symbol, enclosing_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id,
                sym["name"],
                sym["kind"],
                sym["line_start"],
                sym["line_end"],
                sym["signature"],
                sym["is_export"],
                sym["is_default_export"],
                sym["is_async"],
                sym.get("parent_symbol"),
                sym.get("enclosing_type"),
            ),
        )
        if cur.lastrowid is not None:
            sym_id_map.setdefault(sym["name"], cur.lastrowid)
    return sym_id_map


def _insert_call_edges(
    conn: sqlite3.Connection,
    file_id: int,
    call_edges: list[dict],
    sym_id_map: dict[str, int],
) -> None:
    """Insert call edges with caller_symbol_id resolved where possible."""
    for call in call_edges:
        caller_name = call.get("caller_symbol_name")
        caller_sym_id = sym_id_map.get(caller_name) if caller_name else None
        conn.execute(
            """INSERT INTO call_edges
               (caller_file_id, caller_symbol_id, callee_name, line, is_member)
               VALUES (?, ?, ?, ?, ?)""",
            (
                file_id,
                caller_sym_id,
                call["name"],
                call.get("line"),
                bool(call.get("is_member", False)),
            ),
        )


def _resolve_one_import(
    imp: dict, language: str, from_file: str, project_root: str, aliases: dict[str, str]
) -> tuple[str | None, str | None]:
    if language == "python":
        return resolve_python_import(
            imp.get("module", imp["source_path"].lstrip(".")),
            project_root,
            from_file=from_file,
            level=imp.get("level", 0),
        )
    return resolve_import_path(imp["source_path"], project_root, aliases, from_file=from_file)


def _insert_imports(
    conn: sqlite3.Connection,
    result: dict,
    project_root: str,
    aliases: dict[str, str],
    abs_to_file_id: dict[str, int],
) -> int:
    """Insert imports and (deduplicated) dependency edges.

    Returns the number of distinct resolved dependency edges added.
    """
    file_id = result["_file_id"]
    from_file = result["path"]
    language = result["language"]

    resolved_targets: dict[int, int] = {}
    unresolved_internal = 0

    for imp in result["imports"]:
        resolved_rel, resolved_abs = _resolve_one_import(
            imp, language, from_file, project_root, aliases
        )
        resolved_file_id = abs_to_file_id.get(resolved_abs) if resolved_abs else None

        conn.execute(
            """INSERT INTO imports
               (file_id, symbol_name, alias_name, source_path, import_type,
                line, resolved_path, resolved_file_id, is_type_import)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id,
                imp["symbol_name"],
                imp["alias_name"],
                imp["source_path"],
                imp["import_type"],
                imp["line"],
                resolved_rel,
                resolved_file_id,
                imp["is_type_import"],
            ),
        )

        if resolved_file_id is not None and resolved_file_id != file_id:
            resolved_targets[resolved_file_id] = resolved_targets.get(resolved_file_id, 0) + 1
        elif resolved_file_id is None and resolved_rel is not None:
            # Looked internal (relative / alias / in-project module) but no
            # file was found — usually a genuinely broken import.
            unresolved_internal += 1

    for target_id, weight in resolved_targets.items():
        conn.execute(
            """INSERT INTO dependency_edges (source_file_id, target_file_id, weight, resolved)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(source_file_id, target_file_id)
               DO UPDATE SET weight = weight + excluded.weight""",
            (file_id, target_id, weight),
        )

    if unresolved_internal:
        # NULL targets can't use ON CONFLICT (SQLite treats NULLs as distinct
        # in a unique index), and one row per file per run is all we insert.
        conn.execute(
            """INSERT INTO dependency_edges (source_file_id, target_file_id, weight, resolved)
               VALUES (?, NULL, ?, 0)""",
            (file_id, unresolved_internal),
        )

    return len(resolved_targets)


def index_project(
    project_path: str,
    project_name: str | None = None,
    verbose: bool = False,
    incremental: bool = False,
    progress: ProgressFn | None = None,
    quiet: bool = False,
) -> dict:
    """
    Index a project into its SQLite knowledge base.

    Args:
        project_path: path to the project root.
        project_name: override the project name (default: directory name).
        verbose: print per-file progress.
        incremental: reuse rows for files whose content hash is unchanged.
            Import and dependency edges are always rebuilt, because a file that
            did not change can still gain or lose edges when its neighbours do.
        progress: optional callback ``(event, payload)`` for the web UI.
        quiet: suppress stdout (the web server sets this).

    Returns a stats dict.
    """
    project_root = os.path.abspath(project_path)
    if not os.path.isdir(project_root):
        raise NotADirectoryError(f"Not a directory: {project_root}")

    if project_name is None:
        project_name = detect_project_name(project_path)

    def emit(event: str, **payload) -> None:
        if progress:
            progress(event, payload)

    def say(msg: str) -> None:
        if not quiet:
            print(msg)

    aliases = parse_tsconfig_aliases(project_root)
    if verbose and aliases:
        say(f"   Path aliases: {aliases}")

    say(f"🔍 Indexing: {project_name}")
    say(f"   Path: {project_root}")

    conn = init_db(project_name)
    previous_root = get_meta(conn, "project_root")
    if previous_root and previous_root != project_root:
        # The name now points at a different directory — stale rows would mix
        # two projects together.
        incremental = False

    start = time.time()

    files = list(scan_files(project_root))
    say(f"   Found {len(files)} source files")
    emit("scanned", count=len(files))

    # ── Decide which files need re-parsing ──
    previous: dict[str, tuple[int, str]] = {}
    if incremental:
        for row in conn.execute("SELECT id, path, content_hash FROM files").fetchall():
            previous[row["path"]] = (row["id"], row["content_hash"])

    hashes: dict[str, str] = {}
    for path in files:
        try:
            hashes[path] = _file_hash(path)
        except OSError:
            hashes[path] = ""

    reused: set[str] = set()
    if incremental:
        for path in files:
            prior = previous.get(path)
            if prior and prior[1] and prior[1] == hashes[path]:
                reused.add(path)
        # Drop files that disappeared, and every changed file's rows.
        with conn:
            for path, (file_id, _hash) in previous.items():
                if path not in reused:
                    _delete_file_rows(conn, file_id)
    else:
        with conn:
            _clear_project_data(conn)

    to_parse = [p for p in files if p not in reused]
    emit("parsing", total=len(to_parse), reused=len(reused))

    n_errors = 0
    errors: list[dict] = []
    all_results: list[dict] = []

    for i, file_path in enumerate(to_parse):
        rel_path = _to_posix(os.path.relpath(file_path, project_root))
        if verbose:
            say(f"   [{i + 1}/{len(to_parse)}] {rel_path}")
        if progress and (i % 25 == 0 or i == len(to_parse) - 1):
            emit("progress", done=i + 1, total=len(to_parse), file=rel_path)

        try:
            result = parse_file(file_path)
            result["rel_path"] = rel_path
            result["content_hash"] = hashes.get(file_path)
            result["mtime"] = os.path.getmtime(file_path)
            all_results.append(result)
        except Exception as e:  # noqa: BLE001 — one bad file must not stop the run
            n_errors += 1
            errors.append({"file": rel_path, "error": f"{type(e).__name__}: {e}"})
            if verbose:
                say(f"   ⚠️  Error parsing {rel_path}: {e}")

    # ── Pass 1: files, symbols, call edges ──
    n_symbols = 0
    n_calls = 0
    with conn:
        for result in all_results:
            file_id = _insert_file(conn, result)
            sym_id_map = _insert_symbols(conn, file_id, result["symbols"])
            _insert_call_edges(conn, file_id, result["call_edges"], sym_id_map)
            n_symbols += len(result["symbols"])
            n_calls += len(result["call_edges"])
            result["_file_id"] = file_id

    # ── Pass 2: imports and dependency edges ──
    # Needs the full file-id map, so it cannot be folded into pass 1.
    abs_to_file_id: dict[str, int] = {
        row["path"]: row["id"] for row in conn.execute("SELECT id, path FROM files").fetchall()
    }

    if reused:
        # A reused file's edges may point at files that just changed; rebuild
        # every file's import rows against the fresh id map.
        reused_rows = conn.execute(
            "SELECT id, path, rel_path, language FROM files WHERE path IN ({})".format(
                ",".join("?" * len(reused))
            ),
            tuple(reused),
        ).fetchall()
        with conn:
            for row in reused_rows:
                conn.execute("DELETE FROM imports WHERE file_id = ?", (row["id"],))
                conn.execute("DELETE FROM dependency_edges WHERE source_file_id = ?", (row["id"],))
        for row in reused_rows:
            try:
                reparsed = parse_file(row["path"])
            except Exception:  # noqa: BLE001
                continue
            all_results.append(
                {
                    "_file_id": row["id"],
                    "path": row["path"],
                    "rel_path": row["rel_path"],
                    "language": row["language"],
                    "imports": reparsed["imports"],
                }
            )

    n_deps = 0
    n_imports = 0
    with conn:
        for result in all_results:
            n_deps += _insert_imports(conn, result, project_root, aliases, abs_to_file_id)
            n_imports += len(result["imports"])

    with conn:
        set_meta(conn, "project_root", project_root)
        set_meta(conn, "project_name", project_name)
        set_meta(conn, "indexed_at", time.strftime("%Y-%m-%dT%H:%M:%S"))

    elapsed = time.time() - start

    def count(table: str, where: str = "") -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0])

    # Report the state of the index, not just this run's inserts — otherwise
    # an incremental run reports near-zero symbols.
    stats = {
        "project": project_name,
        "root": project_root,
        "files": count("files"),
        "parsed": len(to_parse) - n_errors,
        "reused": len(reused),
        "errors": n_errors,
        "error_details": errors[:50],
        "symbols": count("symbols"),
        "imports": count("imports"),
        "calls": count("call_edges"),
        "deps": count("dependency_edges", "WHERE resolved = 1"),
        "unresolved_deps": count("dependency_edges", "WHERE resolved = 0"),
        "elapsed": elapsed,
    }
    say(f"\n✅ Done in {elapsed:.1f}s")
    say(f"   Files:   {stats['files']} indexed ({len(reused)} unchanged, {n_errors} errors)")
    say(f"   Symbols: {stats['symbols']}")
    say(f"   Imports: {stats['imports']}")
    say(f"   Calls:   {stats['calls']}")
    say(f"   Deps:    {stats['deps']}")

    conn.close()
    emit("done", stats=stats)
    return stats
