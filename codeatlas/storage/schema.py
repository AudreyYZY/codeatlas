"""SQLite DDL for codeatlas."""

import sqlite3
from codeatlas.config import get_db_path


SQL_STATEMENTS = [
    # ── Files ──
    """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        rel_path TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'typescript',
        lines INTEGER DEFAULT 0,
        bytes INTEGER DEFAULT 0,
        indexed_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Symbols ──
    """
    CREATE TABLE IF NOT EXISTS symbols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        line_start INTEGER NOT NULL,
        line_end INTEGER,
        signature TEXT,
        is_export BOOLEAN DEFAULT 0,
        is_default_export BOOLEAN DEFAULT 0,
        is_async BOOLEAN DEFAULT 0,
        parent_symbol TEXT,
        enclosing_type TEXT
    )
    """,

    # ── Imports ──
    """
    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        symbol_name TEXT NOT NULL DEFAULT '',
        alias_name TEXT,
        source_path TEXT NOT NULL,
        import_type TEXT DEFAULT 'named',
        line INTEGER,
        resolved_path TEXT,
        resolved_file_id INTEGER REFERENCES files(id),
        is_type_import BOOLEAN DEFAULT 0
    )
    """,

    # ── Call edges (best-effort) ──
    """
    CREATE TABLE IF NOT EXISTS call_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caller_file_id INTEGER NOT NULL REFERENCES files(id),
        caller_symbol_id INTEGER REFERENCES symbols(id),
        callee_name TEXT NOT NULL,
        callee_symbol_id INTEGER REFERENCES symbols(id),
        callee_file_id INTEGER REFERENCES files(id),
        resolved BOOLEAN DEFAULT 0
    )
    """,

    # ── Dependency edges (file-level) ──
    """
    CREATE TABLE IF NOT EXISTS dependency_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file_id INTEGER NOT NULL REFERENCES files(id),
        target_file_id INTEGER REFERENCES files(id),
        resolved BOOLEAN DEFAULT 0
    )
    """,

    # ── Indexes ──
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_symbol)",
    "CREATE INDEX IF NOT EXISTS idx_imports_source ON imports(source_path)",
    "CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_imports_resolved ON imports(resolved_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_callee ON call_edges(callee_name)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_caller ON call_edges(caller_symbol_id)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_file ON call_edges(caller_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dep_edges_source ON dependency_edges(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dep_edges_target ON dependency_edges(target_file_id)",
]


def init_db(project_name: str) -> sqlite3.Connection:
    """Create the database for a project and return a connection."""
    db_path = get_db_path(project_name)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    for stmt in SQL_STATEMENTS:
        conn.execute(stmt)
    conn.commit()
    return conn
