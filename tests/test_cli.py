"""Smoke tests for the CLI surface.

These don't re-test the engine — they check that every command wires up, prints
something sensible, and exits with the right code.
"""

import json

import pytest
from click.testing import CliRunner

from codeatlas.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def indexed(runner, ts_project):
    result = runner.invoke(cli, ["index", ts_project, "--name", "cliproj"])
    assert result.exit_code == 0, result.output
    return "cliproj"


def _run(runner, *args):
    result = runner.invoke(cli, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def test_version(runner):
    assert "0.3" in _run(runner, "--version")


def test_index_reports_counts(runner, ts_project):
    out = _run(runner, "index", ts_project, "--name", "cliproj")
    assert "Files:" in out and "Symbols:" in out


def test_index_rejects_a_missing_path(runner):
    result = runner.invoke(cli, ["index", "/definitely/not/here"])
    assert result.exit_code == 1


def test_query_without_an_index_exits_nonzero(runner):
    result = runner.invoke(cli, ["stats", "--project", "never-indexed"])
    assert result.exit_code == 1
    assert "No index found" in result.output


def test_stats(runner, indexed):
    out = _run(runner, "stats", "--project", indexed)
    assert "Languages:" in out and "typescript" in out


def test_projects(runner, indexed):
    assert indexed in _run(runner, "projects")


def test_explain_markdown_and_json(runner, indexed):
    md = _run(runner, "explain", "--project", indexed)
    assert "architecture report" in md
    payload = json.loads(_run(runner, "explain", "--project", indexed, "--json"))
    assert payload["stats"]["files"] == 4


def test_cycles(runner, indexed):
    out = _run(runner, "cycles", "--project", indexed)
    assert "import cycle" in out
    assert "graph LR" in _run(runner, "cycles", "--project", indexed, "--mermaid")


def test_symbols_and_wildcard(runner, indexed):
    assert "helper" in _run(runner, "symbols", "helper", "--project", indexed)
    assert "helper" in _run(runner, "symbols", "help*", "--project", indexed)


def test_symbols_not_found_is_still_success(runner, indexed):
    assert "No symbols" in _run(runner, "symbols", "zzzznope", "--project", indexed)


def test_file_listing(runner, indexed):
    assert "main" in _run(runner, "file", "src/index.ts", "--project", indexed)


def test_list_filters_by_kind(runner, indexed):
    assert "function" in _run(runner, "list", "--kind", "function", "--project", indexed)


def test_callers_and_callees(runner, indexed):
    assert "helper" in _run(runner, "callers", "helper", "--project", indexed)
    assert "main" in _run(runner, "callees", "main", "--project", indexed)


def test_chain(runner, indexed):
    assert "Call chain" in _run(runner, "chain", "main", "--project", indexed)


def test_deps_and_graph(runner, indexed):
    assert "util.ts" in _run(runner, "deps", "src/index.ts", "--project", indexed)
    assert "graph TD" in _run(
        runner, "graph", "src/index.ts", "--type", "deps", "--project", indexed
    )
    assert "graph TD" in _run(runner, "graph", "main", "--type", "calls", "--project", indexed)


def test_used_by(runner, indexed):
    assert "src/index.ts" in _run(runner, "used-by", "./components/Map", "--project", indexed)


def test_imports_command(runner, indexed):
    assert "src/index.ts" in _run(runner, "imports", "helper", "--project", indexed)


def test_export_to_stdout(runner, indexed):
    payload = json.loads(_run(runner, "export", "--project", indexed, "-o", "-"))
    assert {"report", "files", "symbols"} <= set(payload)
