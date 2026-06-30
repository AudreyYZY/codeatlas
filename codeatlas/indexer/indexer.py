"""Indexer orchestrator: scan → parse → resolve → insert."""

import os
import sqlite3
import time

from codeatlas.config import detect_project_name
from codeatlas.indexer.parser import parse_file
from codeatlas.indexer.resolver import parse_tsconfig_aliases, resolve_import_path
from codeatlas.scanner.scanner import scan_files
from codeatlas.storage.schema import init_db


def _clear_project_data(conn: sqlite3.Connection):
    """Remove all data from a previous index run."""
    conn.execute("DELETE FROM dependency_edges")
    conn.execute("DELETE FROM call_edges")
    conn.execute("DELETE FROM imports")
    conn.execute("DELETE FROM symbols")
    conn.execute("DELETE FROM files")


def _insert_file(conn: sqlite3.Connection, result: dict) -> int:
    cur = conn.execute(
        "INSERT INTO files (path, rel_path, language, lines, bytes) VALUES (?, ?, ?, ?, ?)",
        (result["path"], result["rel_path"], result["language"], result["lines"], result["bytes"]),
    )
    return cur.lastrowid


def _insert_symbols(
    conn: sqlite3.Connection, file_id: int, symbols: list[dict]
) -> dict[tuple, int]:
    """Insert symbols and return a map of (name, file_id) → symbol_id."""
    sym_id_map: dict[tuple, int] = {}
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
        sym_id_map[(sym["name"], file_id)] = cur.lastrowid
    return sym_id_map


def _insert_imports(
    conn: sqlite3.Connection,
    file_id: int,
    imports: list[dict],
    project_root: str,
    aliases: dict[str, str],
    rel_to_file_id: dict[str, int],
) -> int:
    """Insert imports and dependency edges. Returns count of resolved deps."""
    resolved_count = 0
    for imp in imports:
        source = imp["source_path"]
        resolved_rel, resolved_abs = resolve_import_path(source, project_root, aliases)
        resolved_file_id = None
        if resolved_abs and resolved_abs in rel_to_file_id:
            resolved_file_id = rel_to_file_id[resolved_abs]

        conn.execute(
            """INSERT INTO imports
               (file_id, symbol_name, alias_name, source_path, import_type,
                line, resolved_path, resolved_file_id, is_type_import)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_id,
                imp["symbol_name"],
                imp["alias_name"],
                source,
                imp["import_type"],
                imp["line"],
                resolved_rel,
                resolved_file_id,
                imp.get("is_type_import", False),
            ),
        )

        # Also insert a dependency edge (file-level)
        if resolved_file_id:
            conn.execute(
                """INSERT INTO dependency_edges
                   (source_file_id, target_file_id, resolved) VALUES (?, ?, 1)""",
                (file_id, resolved_file_id),
            )
            resolved_count += 1
        elif source.startswith((".", "@", "/")):
            # Internal import but unresolved
            conn.execute(
                """INSERT INTO dependency_edges
                   (source_file_id, target_file_id, resolved) VALUES (?, NULL, 0)""",
                (file_id,),
            )
        # External packages (react, cesium...) don't get dep_edges

    return resolved_count


def _insert_call_edges(
    conn: sqlite3.Connection,
    file_id: int,
    call_edges: list[dict],
    sym_id_map: dict[tuple, int],
):
    """Insert call edges with caller_symbol_id resolved."""
    for call in call_edges:
        caller_name = call.get("caller_symbol_name")
        caller_sym_id = None
        if caller_name:
            caller_sym_id = sym_id_map.get((caller_name, file_id))
        conn.execute(
            """INSERT INTO call_edges
               (caller_file_id, caller_symbol_id, callee_name)
               VALUES (?, ?, ?)""",
            (file_id, caller_sym_id, call["name"]),
        )


def index_project(project_path: str, project_name: str = None, verbose: bool = False) -> dict:
    """
    Index a TypeScript project.

    Args:
        project_path: Path to the project root.
        project_name: Override project name (default: derived from dir name).
        verbose: Print per-file progress.

    Returns:
        Stats dict with file_count, symbol_count, import_count, etc.
    """
    project_root = os.path.abspath(project_path)
    if project_name is None:
        project_name = detect_project_name(project_path)

    # Parse tsconfig aliases
    aliases = parse_tsconfig_aliases(project_root)
    if verbose and aliases:
        print(f"   Path aliases: {aliases}")

    print(f"🔍 Indexing: {project_name}")
    print(f"   Path: {project_root}")

    conn = init_db(project_name)
    _clear_project_data(conn)

    # Phase 1: Scan
    files = list(scan_files(project_root))
    print(f"   Found {len(files)} source files")

    n_symbols = 0
    n_imports = 0
    n_calls = 0
    n_deps = 0
    n_errors = 0
    start = time.time()

    # Phase 2: Parse — first pass to insert all files (so we have file_id → rel_path mapping)
    all_results: list[dict] = []
    for i, file_path in enumerate(files):
        rel_path = os.path.relpath(file_path, project_root)
        if verbose:
            print(f"   [{i + 1}/{len(files)}] {rel_path}")

        try:
            result = parse_file(file_path, aliases)
            result["rel_path"] = rel_path
            all_results.append(result)
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Error parsing {rel_path}: {e}")
            n_errors += 1

    # Phase 3: Build rel_path → file_id map (after inserting all files)
    # We do a two-pass approach: first insert all files to get IDs,
    # then insert imports/deps with resolved targets.

    with conn:
        # First pass: insert files and symbols
        for result in all_results:
            file_id = _insert_file(conn, result)
            sym_id_map = _insert_symbols(conn, file_id, result["symbols"])
            n_symbols += len(result["symbols"])
            _insert_call_edges(conn, file_id, result["call_edges"], sym_id_map)
            n_calls += len(result["call_edges"])
            result["_file_id"] = file_id
            result["_sym_id_map"] = sym_id_map

    # Build file path → file_id map for import resolution
    rel_to_file_id: dict[str, int] = {}
    for result in all_results:
        rel_to_file_id[result["path"]] = result["_file_id"]
        # Also map by rel_path (for resolution relative to project root)
        rel_to_file_id[result["rel_path"]] = result["_file_id"]

    # Second pass: insert imports and dependency edges
    with conn:
        for result in all_results:
            n_deps += _insert_imports(
                conn,
                result["_file_id"],
                result["imports"],
                project_root,
                aliases,
                rel_to_file_id,
            )
            n_imports += len(result["imports"])

    conn.commit()
    elapsed = time.time() - start

    stats = {
        "files": len(files) - n_errors,
        "errors": n_errors,
        "symbols": n_symbols,
        "imports": n_imports,
        "calls": n_calls,
        "deps": n_deps,
        "elapsed": elapsed,
    }

    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Files:   {stats['files']} parsed ({n_errors} errors)")
    print(f"   Symbols: {n_symbols}")
    print(f"   Imports: {n_imports}")
    print(f"   Calls:   {n_calls}")
    print(f"   Deps:    {n_deps}")

    conn.close()
    return stats
