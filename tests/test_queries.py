"""Tests for storage queries using in-memory SQLite."""

import sqlite3

import pytest

from codeatlas.storage import queries, schema


@pytest.fixture
def db():
    """Create an in-memory database with the codeatlas schema and sample data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    for stmt in schema.SQL_STATEMENTS:
        conn.execute(stmt)

    # Insert sample files
    conn.execute(
        """INSERT INTO files (id, path, rel_path, language)
           VALUES (1, '/proj/src/a.ts', 'src/a.ts', 'typescript')"""
    )
    conn.execute(
        """INSERT INTO files (id, path, rel_path, language)
           VALUES (2, '/proj/src/b.ts', 'src/b.ts', 'typescript')"""
    )

    # Insert sample symbols
    conn.execute(
        """INSERT INTO symbols (id, file_id, name, kind, line_start, is_export, parent_symbol)
           VALUES (1, 1, 'foo', 'function', 10, 1, NULL)"""
    )
    conn.execute(
        """INSERT INTO symbols (id, file_id, name, kind, line_start, is_export, parent_symbol)
           VALUES (2, 1, 'bar', 'function', 25, 0, 'foo')"""
    )
    conn.execute(
        """INSERT INTO symbols (id, file_id, name, kind, line_start, is_export, parent_symbol)
           VALUES (3, 2, 'baz', 'class', 5, 1, NULL)"""
    )

    # Insert import
    conn.execute(
        """INSERT INTO imports (file_id, symbol_name, source_path, import_type)
           VALUES (1, 'baz', 'src/b', 'default')"""
    )

    # Insert call edge
    conn.execute(
        """INSERT INTO call_edges (caller_file_id, caller_symbol_id, callee_name)
           VALUES (1, 1, 'bar')"""
    )

    # Insert dependency edge
    conn.execute(
        """INSERT INTO dependency_edges (source_file_id, target_file_id, resolved)
           VALUES (1, 2, 1)"""
    )

    conn.commit()
    return conn


def test_get_stats(db):
    s = queries.get_stats(db)
    assert s["files"] == 2
    assert s["symbols"] == 3
    assert s["imports"] == 1
    assert s["calls"] == 1
    assert s["deps"] == 1


def test_find_symbols(db):
    rows = queries.find_symbols(db, "foo")
    assert len(rows) == 1
    assert rows[0]["name"] == "foo"
    assert rows[0]["kind"] == "function"


def test_find_symbols_fuzzy(db):
    rows = queries.find_symbols(db, "%ba%")
    assert len(rows) == 2  # bar and baz


def test_list_symbols_in_file(db):
    rows = queries.list_symbols_in_file(db, "a.ts")
    assert len(rows) == 2


def test_list_symbols_filtered(db):
    rows = queries.list_symbols(db, kind="class")
    assert len(rows) == 1
    assert rows[0]["name"] == "baz"


def test_list_symbols_exported(db):
    rows = queries.list_symbols(db, exported_only=True)
    assert len(rows) == 2  # foo and baz are exported


def test_get_children_of(db):
    rows = queries.get_children_of(db, "foo")
    assert len(rows) == 1
    assert rows[0]["name"] == "bar"


def test_find_imports_of_symbol(db):
    rows = queries.find_imports_of_symbol(db, "baz")
    assert len(rows) == 1
    assert rows[0]["source_path"] == "src/b"


def test_find_imports_from_module(db):
    rows = queries.find_imports_from_module(db, "src/b")
    assert len(rows) == 1


def test_find_callers(db):
    rows = queries.find_callers(db, "bar")
    assert len(rows) == 1
    assert rows[0]["caller_name"] == "foo"


def test_find_callees(db):
    rows = queries.find_callees(db, 1)  # symbol id 1 = foo
    assert len(rows) == 1
    assert rows[0]["callee_name"] == "bar"


def test_get_dependencies(db):
    rows = queries.get_dependencies(db, 1)
    assert len(rows) == 1
    assert rows[0]["target_rel_path"] == "src/b.ts"


def test_get_dependents(db):
    rows = queries.get_dependents(db, 2)
    assert len(rows) == 1
    assert rows[0]["source_rel_path"] == "src/a.ts"


def test_get_all_dependencies(db):
    rows = queries.get_all_dependencies(db)
    assert len(rows) == 1
