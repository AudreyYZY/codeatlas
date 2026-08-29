"""SQLite DDL for codeatlas."""

import sqlite3

from codeatlas.config import get_db_path

# Bumped whenever the DDL below changes in a way older databases cannot
# satisfy. On mismatch the index is dropped and rebuilt from scratch.
SCHEMA_VERSION = 3

SQL_STATEMENTS = [
    # ── Meta (schema version, project root, last index run) ──
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    # ── Files ──
    """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE NOT NULL,
        rel_path TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'typescript',
        lines INTEGER DEFAULT 0,
        bytes INTEGER DEFAULT 0,
        mtime REAL DEFAULT 0,
        content_hash TEXT,
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
        resolved_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
        is_type_import BOOLEAN DEFAULT 0
    )
    """,
    # ── Call edges (best-effort) ──
    """
    CREATE TABLE IF NOT EXISTS call_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caller_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        caller_symbol_id INTEGER REFERENCES symbols(id) ON DELETE CASCADE,
        callee_name TEXT NOT NULL,
        callee_symbol_id INTEGER REFERENCES symbols(id) ON DELETE SET NULL,
        callee_file_id INTEGER REFERENCES files(id) ON DELETE SET NULL,
        line INTEGER,
        is_member BOOLEAN DEFAULT 0,
        resolved BOOLEAN DEFAULT 0
    )
    """,
    # ── Dependency edges (file-level) ──
    # `weight` counts how many import statements produced the edge, so a file
    # importing six names from one module is one edge, not six.
    """
    CREATE TABLE IF NOT EXISTS dependency_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        target_file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
        weight INTEGER DEFAULT 1,
        resolved BOOLEAN DEFAULT 0
    )
    """,
    # ── Indexes ──
    "CREATE INDEX IF NOT EXISTS idx_files_rel ON files(rel_path)",
    "CREATE INDEX IF NOT EXISTS idx_files_lang ON files(language)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_symbols_parent ON symbols(parent_symbol)",
    "CREATE INDEX IF NOT EXISTS idx_imports_source ON imports(source_path)",
    "CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_imports_symbol ON imports(symbol_name)",
    "CREATE INDEX IF NOT EXISTS idx_imports_resolved ON imports(resolved_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_callee ON call_edges(callee_name)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_caller ON call_edges(caller_symbol_id)",
    "CREATE INDEX IF NOT EXISTS idx_call_edges_file ON call_edges(caller_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dep_edges_source ON dependency_edges(source_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dep_edges_target ON dependency_edges(target_file_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_dep_edges_pair "
    "ON dependency_edges(source_file_id, target_file_id)",
]

TABLES = ("dependency_edges", "call_edges", "imports", "symbols", "files", "meta")


def _apply_ddl(conn: sqlite3.Connection) -> None:
    for stmt in SQL_STATEMENTS:
        conn.execute(stmt)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _stored_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def init_db(project_name: str) -> sqlite3.Connection:
    """Open (creating if needed) a project database, migrating if stale.

    A schema-version mismatch drops every table and recreates them, which
    forces a full re-index rather than silently querying a database whose
    columns no longer match the code.
    """
    db_path = get_db_path(project_name)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    has_files = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='files'"
    ).fetchone()

    if has_files and _stored_version(conn) != SCHEMA_VERSION:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute("PRAGMA foreign_keys = ON")

    _apply_ddl(conn)
    conn.commit()
    return conn


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default
