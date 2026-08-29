"""SQL query functions for codeatlas."""

import sqlite3

from codeatlas.config import get_db_path


def _connect(project_name: str) -> sqlite3.Connection:
    db_path = get_db_path(project_name)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _like(term: str) -> str:
    """Turn a user search term into a LIKE pattern.

    A bare term matches exactly; wrapping it in ``*`` (or using SQL's own ``%``)
    makes it a substring search. Without this, ``codeatlas symbols Camera``
    silently required an exact match despite the help text saying "find".
    """
    if "%" in term or "_" in term:
        return term
    if "*" in term:
        return term.replace("*", "%")
    return term


# ── Stats ──


def get_stats(conn: sqlite3.Connection) -> dict:
    return {
        "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "symbols": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
        "imports": conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0],
        "calls": conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0],
        "deps": conn.execute("SELECT COUNT(*) FROM dependency_edges WHERE resolved = 1").fetchone()[
            0
        ],
        "unresolved_deps": conn.execute(
            "SELECT COUNT(*) FROM dependency_edges WHERE resolved = 0"
        ).fetchone()[0],
        "lines": conn.execute("SELECT COALESCE(SUM(lines), 0) FROM files").fetchone()[0],
    }


def get_kind_counts(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT kind, COUNT(*) as cnt FROM symbols GROUP BY kind ORDER BY cnt DESC"
    ).fetchall()


def get_language_counts(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """SELECT language, COUNT(*) as cnt, COALESCE(SUM(lines), 0) as lines
           FROM files GROUP BY language ORDER BY cnt DESC"""
    ).fetchall()


def get_top_imports(conn: sqlite3.Connection, limit: int = 10) -> list:
    return conn.execute(
        """SELECT source_path, COUNT(*) as cnt
           FROM imports WHERE source_path != ''
           GROUP BY source_path ORDER BY cnt DESC LIMIT ?""",
        (limit,),
    ).fetchall()


def get_external_packages(conn: sqlite3.Connection, limit: int = 20) -> list:
    """Third-party packages the project imports, by number of importing files."""
    return conn.execute(
        """SELECT source_path, COUNT(DISTINCT file_id) as cnt
           FROM imports
           WHERE resolved_file_id IS NULL
             AND source_path != ''
             AND source_path NOT LIKE '.%'
             AND source_path NOT LIKE '/%'
           GROUP BY source_path ORDER BY cnt DESC, source_path LIMIT ?""",
        (limit,),
    ).fetchall()


def get_files(conn: sqlite3.Connection, limit: int | None = None) -> list:
    """All indexed files with their symbol and dependency counts."""
    sql = """
        SELECT f.id, f.rel_path, f.language, f.lines, f.bytes,
               (SELECT COUNT(*) FROM symbols s WHERE s.file_id = f.id) AS symbol_count,
               (SELECT COUNT(*) FROM dependency_edges d
                 WHERE d.source_file_id = f.id AND d.resolved = 1) AS out_degree,
               (SELECT COUNT(*) FROM dependency_edges d
                 WHERE d.target_file_id = f.id) AS in_degree
        FROM files f ORDER BY f.rel_path
    """
    if limit:
        sql += " LIMIT ?"
        return conn.execute(sql, (limit,)).fetchall()
    return conn.execute(sql).fetchall()


def get_hotspots(conn: sqlite3.Connection, limit: int = 15) -> list:
    """Files the most other files depend on — the load-bearing modules."""
    return conn.execute(
        """SELECT f.rel_path, f.language, f.lines,
                  COUNT(d.id) as dependents
           FROM files f JOIN dependency_edges d ON d.target_file_id = f.id
           GROUP BY f.id ORDER BY dependents DESC, f.rel_path LIMIT ?""",
        (limit,),
    ).fetchall()


def get_entrypoints(conn: sqlite3.Connection, limit: int = 15) -> list:
    """Files nothing else imports — CLI entry points, pages, dead code."""
    return conn.execute(
        """SELECT f.rel_path, f.language, f.lines,
                  (SELECT COUNT(*) FROM dependency_edges d
                    WHERE d.source_file_id = f.id AND d.resolved = 1) as imports_count
           FROM files f
           WHERE NOT EXISTS (SELECT 1 FROM dependency_edges d WHERE d.target_file_id = f.id)
             AND EXISTS (SELECT 1 FROM symbols s WHERE s.file_id = f.id)
           ORDER BY imports_count DESC, f.rel_path LIMIT ?""",
        (limit,),
    ).fetchall()


def get_orphans(conn: sqlite3.Connection, limit: int = 30) -> list:
    """Files with no in-project dependencies in either direction."""
    return conn.execute(
        """SELECT f.rel_path, f.language, f.lines FROM files f
           WHERE NOT EXISTS (SELECT 1 FROM dependency_edges d WHERE d.target_file_id = f.id)
             AND NOT EXISTS (
                 SELECT 1 FROM dependency_edges d
                 WHERE d.source_file_id = f.id AND d.resolved = 1)
           ORDER BY f.lines DESC, f.rel_path LIMIT ?""",
        (limit,),
    ).fetchall()


def get_module_breakdown(conn: sqlite3.Connection, depth: int = 1) -> list:
    """Group files by their top-level directory ("module")."""
    rows = conn.execute("SELECT rel_path, lines FROM files").fetchall()
    buckets: dict[str, dict] = {}
    for row in rows:
        parts = row["rel_path"].split("/")
        name = "/".join(parts[:depth]) if len(parts) > depth else "(root)"
        bucket = buckets.setdefault(name, {"module": name, "files": 0, "lines": 0})
        bucket["files"] += 1
        bucket["lines"] += row["lines"] or 0

    symbol_rows = conn.execute(
        """SELECT f.rel_path, COUNT(s.id) as cnt
           FROM files f LEFT JOIN symbols s ON s.file_id = f.id GROUP BY f.id"""
    ).fetchall()
    for row in symbol_rows:
        parts = row["rel_path"].split("/")
        name = "/".join(parts[:depth]) if len(parts) > depth else "(root)"
        if name in buckets:
            buckets[name].setdefault("symbols", 0)
            buckets[name]["symbols"] += row["cnt"]

    result = list(buckets.values())
    for bucket in result:
        bucket.setdefault("symbols", 0)
    return sorted(result, key=lambda b: -b["files"])


# ── Symbols ──


def find_symbols(conn: sqlite3.Connection, name: str, limit: int = 200) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path, f.language
           FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.name LIKE ?
           ORDER BY s.is_export DESC, f.rel_path, s.line_start LIMIT ?""",
        (_like(name), limit),
    ).fetchall()


def search_symbols(conn: sqlite3.Connection, term: str, limit: int = 50) -> list:
    """Substring search across symbol names — what the web UI's search box uses."""
    return conn.execute(
        """SELECT s.*, f.rel_path, f.language
           FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.name LIKE ?
           ORDER BY LENGTH(s.name), s.is_export DESC, s.name LIMIT ?""",
        (f"%{term}%", limit),
    ).fetchall()


def list_symbols_in_file(conn: sqlite3.Connection, rel_path_pattern: str) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path
           FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE f.rel_path LIKE ?
           ORDER BY f.rel_path, s.line_start""",
        (f"%{rel_path_pattern}%",),
    ).fetchall()


def list_symbols(
    conn: sqlite3.Connection, kind: str | None = None, exported_only: bool = False, limit: int = 0
) -> list:
    where = ["1=1"]
    params: list = []
    if kind:
        where.append("s.kind = ?")
        params.append(kind)
    if exported_only:
        where.append("s.is_export = 1")
    sql = f"""SELECT s.*, f.rel_path FROM symbols s JOIN files f ON s.file_id = f.id
              WHERE {" AND ".join(where)} ORDER BY s.kind, s.name"""
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def get_children_of(conn: sqlite3.Connection, parent_name: str) -> list:
    """Get all symbols whose parent_symbol matches."""
    return conn.execute(
        """SELECT s.*, f.rel_path FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.parent_symbol = ? ORDER BY s.line_start""",
        (parent_name,),
    ).fetchall()


# ── Imports ──


def find_imports_of_symbol(conn: sqlite3.Connection, symbol_name: str) -> list:
    return conn.execute(
        """SELECT i.*, f.rel_path as importer
           FROM imports i JOIN files f ON i.file_id = f.id
           WHERE i.symbol_name LIKE ? ORDER BY f.rel_path""",
        (_like(symbol_name),),
    ).fetchall()


def find_imports_from_module(conn: sqlite3.Connection, module_path: str) -> list:
    """Find all files that import from a given module path."""
    rows = conn.execute(
        """SELECT i.*, f.rel_path as importer
           FROM imports i JOIN files f ON i.file_id = f.id
           WHERE i.source_path = ? OR i.source_path LIKE ?
           ORDER BY f.rel_path""",
        (module_path, f"{module_path}/%"),
    ).fetchall()
    if not rows:
        rows = conn.execute(
            """SELECT i.*, f.rel_path as importer
               FROM imports i JOIN files f ON i.file_id = f.id
               WHERE i.source_path LIKE ? ORDER BY f.rel_path""",
            (f"%{module_path}%",),
        ).fetchall()
    return rows


def get_file_imports(conn: sqlite3.Connection, file_id: int) -> list:
    return conn.execute(
        """SELECT i.*, t.rel_path as target_rel_path
           FROM imports i LEFT JOIN files t ON i.resolved_file_id = t.id
           WHERE i.file_id = ? ORDER BY i.line""",
        (file_id,),
    ).fetchall()


# ── Call edges ──


def find_callers(conn: sqlite3.Connection, symbol_name: str) -> list:
    """Who calls this symbol?"""
    return conn.execute(
        """SELECT ce.*, f.rel_path, s.name as caller_name, s.kind as caller_kind,
                  s.line_start as caller_line
           FROM call_edges ce
           JOIN files f ON ce.caller_file_id = f.id
           LEFT JOIN symbols s ON ce.caller_symbol_id = s.id
           WHERE ce.callee_name = ?
           ORDER BY f.rel_path, ce.line""",
        (symbol_name,),
    ).fetchall()


def find_callees(conn: sqlite3.Connection, symbol_id: int) -> list:
    """What does this symbol call?"""
    return conn.execute(
        """SELECT ce.callee_name, COUNT(*) as cnt, MIN(ce.line) as line
           FROM call_edges ce
           WHERE ce.caller_symbol_id = ?
           GROUP BY ce.callee_name
           ORDER BY ce.callee_name""",
        (symbol_id,),
    ).fetchall()


def get_symbol_by_name(conn: sqlite3.Connection, name: str) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.name LIKE ?
           ORDER BY s.kind IN ('function','method','arrow_function') DESC, s.is_export DESC
           LIMIT 20""",
        (_like(name),),
    ).fetchall()


# ── Dependency edges ──


def get_dependencies(conn: sqlite3.Connection, file_id: int) -> list:
    """Files that this file imports."""
    return conn.execute(
        """SELECT de.*, f.rel_path as target_rel_path
           FROM dependency_edges de
           JOIN files f ON de.target_file_id = f.id
           WHERE de.source_file_id = ?""",
        (file_id,),
    ).fetchall()


def get_dependents(conn: sqlite3.Connection, file_id: int) -> list:
    """Files that import this file."""
    return conn.execute(
        """SELECT de.*, f.rel_path as source_rel_path
           FROM dependency_edges de
           JOIN files f ON de.source_file_id = f.id
           WHERE de.target_file_id = ?""",
        (file_id,),
    ).fetchall()


def get_all_dependencies(conn: sqlite3.Connection) -> list:
    """All resolved dependency edges."""
    return conn.execute(
        """SELECT de.*,
                  s.rel_path as source_rel,
                  t.rel_path as target_rel
           FROM dependency_edges de
           JOIN files s ON de.source_file_id = s.id
           JOIN files t ON de.target_file_id = t.id
           WHERE de.resolved = 1"""
    ).fetchall()


def get_file_by_path(conn: sqlite3.Connection, rel_path: str):
    row = conn.execute("SELECT * FROM files WHERE rel_path = ?", (rel_path,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM files WHERE rel_path LIKE ? ORDER BY LENGTH(rel_path) LIMIT 1",
            (f"%{rel_path}%",),
        ).fetchone()
    return row
