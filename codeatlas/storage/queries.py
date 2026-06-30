"""SQL query functions for codeatlas."""

import sqlite3
from codeatlas.config import get_db_path


def _connect(project_name: str) -> sqlite3.Connection:
    db_path = get_db_path(project_name)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Stats ──

def get_stats(conn: sqlite3.Connection) -> dict:
    return {
        "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "symbols": conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
        "imports": conn.execute("SELECT COUNT(*) FROM imports").fetchone()[0],
        "calls": conn.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0],
        "deps": conn.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0],
    }


def get_kind_counts(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT kind, COUNT(*) as cnt FROM symbols GROUP BY kind ORDER BY cnt DESC"
    ).fetchall()


def get_top_imports(conn: sqlite3.Connection, limit: int = 10) -> list:
    return conn.execute(
        """SELECT source_path, COUNT(*) as cnt
           FROM imports WHERE source_path != ''
           GROUP BY source_path ORDER BY cnt DESC LIMIT ?""",
        (limit,),
    ).fetchall()


# ── Symbols ──

def find_symbols(conn: sqlite3.Connection, name: str) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path
           FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.name LIKE ?
           ORDER BY f.rel_path, s.line_start""",
        (name,),
    ).fetchall()


def list_symbols_in_file(conn: sqlite3.Connection, rel_path_pattern: str) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path
           FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE f.rel_path LIKE ?
           ORDER BY s.line_start""",
        (f"%{rel_path_pattern}%",),
    ).fetchall()


def list_symbols(conn: sqlite3.Connection, kind: str = None, exported_only: bool = False) -> list:
    where = ["1=1"]
    params = []
    if kind:
        where.append("s.kind = ?")
        params.append(kind)
    if exported_only:
        where.append("s.is_export = 1")
    return conn.execute(
        f"""SELECT s.*, f.rel_path FROM symbols s JOIN files f ON s.file_id = f.id
            WHERE {' AND '.join(where)} ORDER BY s.kind, s.name""",
        params,
    ).fetchall()


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
        (symbol_name,),
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


# ── Call edges ──

def find_callers(conn: sqlite3.Connection, symbol_name: str) -> list:
    """Who calls this symbol?"""
    return conn.execute(
        """SELECT ce.*, f.rel_path, s.name as caller_name, s.kind as caller_kind
           FROM call_edges ce
           JOIN files f ON ce.caller_file_id = f.id
           LEFT JOIN symbols s ON ce.caller_symbol_id = s.id
           WHERE ce.callee_name = ?""",
        (symbol_name,),
    ).fetchall()


def find_callees(conn: sqlite3.Connection, symbol_id: int) -> list:
    """What does this symbol call?"""
    return conn.execute(
        """SELECT DISTINCT ce.callee_name
           FROM call_edges ce
           WHERE ce.caller_symbol_id = ?
           ORDER BY ce.callee_name""",
        (symbol_id,),
    ).fetchall()


def get_symbol_by_name(conn: sqlite3.Connection, name: str) -> list:
    return conn.execute(
        """SELECT s.*, f.rel_path FROM symbols s JOIN files f ON s.file_id = f.id
           WHERE s.name LIKE ? LIMIT 20""",
        (name,),
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
           LEFT JOIN files t ON de.target_file_id = t.id
           WHERE de.resolved = 1"""
    ).fetchall()
