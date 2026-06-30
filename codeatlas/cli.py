"""Unified CLI for codeatlas."""

import os
import sqlite3
import sys

import click

from codeatlas.config import detect_project_name, get_db_path, list_projects
from codeatlas.graph.mermaid import calls_to_mermaid, deps_to_mermaid
from codeatlas.indexer.indexer import index_project
from codeatlas.storage import queries


def _get_project_name(project_arg: str | None = None) -> str:
    """Determine project name: explicit arg → current dir name."""
    if project_arg:
        return project_arg
    return detect_project_name(".")


def _connect(project_name: str) -> sqlite3.Connection:
    db_path = get_db_path(project_name)
    if not os.path.exists(db_path):
        registered = list_projects()
        msg = f"No index found for '{project_name}'."
        if registered:
            msg += f"\nIndexed projects: {', '.join(registered)}"
        msg += "\nRun: codeatlas index <project-path>"
        click.echo(msg, err=True)
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── CLI Entry Point ──


@click.group()
@click.version_option(version="0.2.0", prog_name="codeatlas")
def cli():
    """codeatlas — a local-first, language-aware code knowledge base.

    Index, query, and visualize your TypeScript projects.
    """
    pass


# ── Index ──


@cli.command()
@click.argument("path", default=".")
@click.option("--name", default=None, help="Project name (default: directory name)")
@click.option("--verbose", "-v", is_flag=True, help="Print per-file progress")
def index(path: str, name: str | None, verbose: bool):
    """Index a TypeScript project."""
    index_project(path, name, verbose)


# ── Stats ──


@cli.command()
@click.option("--project", default=None, help="Project name")
def stats(project: str | None):
    """Show index statistics."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    s = queries.get_stats(conn)
    kinds = queries.get_kind_counts(conn)
    top = queries.get_top_imports(conn)

    click.echo(f"\n📊 {pname}")
    click.echo(f"   Files:   {s['files']}")
    click.echo(f"   Symbols: {s['symbols']}")
    click.echo(f"   Imports: {s['imports']}")
    click.echo(f"   Calls:   {s['calls']}")
    click.echo(f"   Deps:    {s['deps']}")
    click.echo("\n   Symbol kinds:")
    for r in kinds:
        click.echo(f"     {r['kind']:<18} {r['cnt']:>5}")
    click.echo("\n   Top imports:")
    for r in top:
        click.echo(f"     {r['source_path']:<45} {r['cnt']:>3}")


# ── Symbols ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def symbols(name: str, project: str | None):
    """Find symbols by name."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.find_symbols(conn, name)

    if not rows:
        click.echo(f"No symbols matching '{name}'")
        return

    click.echo(f"\n🔍 {len(rows)} symbol(s) matching '{name}':\n")
    for r in rows:
        exp = "📤" if r["is_export"] else "  "
        sig = f"\n     → {r['signature']}" if r["signature"] else ""
        parent = f"  [{r['parent_symbol']}]" if r["parent_symbol"] else ""
        line = f"  {exp} {r['kind']:<16} {r['name']:<28} "
        line += f"{r['rel_path']}:{r['line_start']}{parent}{sig}"
        click.echo(line)


# ── File ──


@cli.command()
@click.argument("path")
@click.option("--project", default=None, help="Project name")
def file(path: str, project: str | None):
    """List all symbols in a file."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.list_symbols_in_file(conn, path)

    if not rows:
        click.echo(f"No symbols found in '{path}'")
        return

    file_path = rows[0]["rel_path"]
    click.echo(f"\n📄 {file_path} — {len(rows)} definition(s):\n")
    for r in rows:
        exp = "[exp]" if r["is_export"] else ""
        parent = f" ← {r['parent_symbol']}" if r["parent_symbol"] else ""
        click.echo(f"  L{r['line_start']:>4}  {r['kind']:<16} {r['name']:<30} {exp}{parent}")
        if r["signature"]:
            click.echo(f"         → {r['signature']}")


# ── Imports ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def imports(name: str, project: str | None):
    """Show which files import a symbol."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.find_imports_of_symbol(conn, name)

    if not rows:
        click.echo(f"No files import '{name}'")
        return

    click.echo(f"\n📥 {len(rows)} file(s) import '{name}':\n")
    for r in rows:
        alias = f" as {r['alias_name']}" if r["alias_name"] else ""
        resolved = f" → {r['resolved_path']}" if r.get("resolved_path") else ""
        line = f"  {r['importer']}:{r['line']}  ← {r['source_path']}"
        line += f" ({r['import_type']}{alias}){resolved}"
        click.echo(line)


# ── Used-by ──


@cli.command(name="used-by")
@click.argument("module")
@click.option("--project", default=None, help="Project name")
def used_by(module: str, project: str | None):
    """Show which files import from a module."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.find_imports_from_module(conn, module)

    if not rows:
        click.echo(f"No files import from '{module}'")
        return

    importers: dict[str, list[str]] = {}
    for r in rows:
        importers.setdefault(r["importer"], []).append(r["symbol_name"])

    click.echo(f"\n📥 {len(importers)} file(s) import from '{module}':\n")
    for importer, syms in sorted(importers.items()):
        sym_list = ", ".join(s for s in syms if s)
        click.echo(f"  {importer}")
        if sym_list:
            click.echo(f"    imports: {sym_list}")


# ── List ──


@cli.command()
@click.option("--kind", default=None, help="Filter by kind (function, class, interface, ...)")
@click.option("--exported", is_flag=True, help="Only exported symbols")
@click.option("--project", default=None, help="Project name")
def list(kind: str | None, exported: bool, project: str | None):
    """List symbols, optionally filtered."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.list_symbols(conn, kind, exported)

    desc = f"kind={kind}" if kind else "all kinds"
    desc += ", exported" if exported else ""
    click.echo(f"\n📋 {len(rows)} symbols ({desc}):\n")
    for r in rows:
        exp = "📤" if r["is_export"] else "  "
        click.echo(f"  {exp} {r['kind']:<16} {r['name']:<30} {r['rel_path']}:{r['line_start']}")


# ── Callers ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def callers(name: str, project: str | None):
    """Show who calls a symbol."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    rows = queries.find_callers(conn, name)

    if not rows:
        click.echo(f"No callers found for '{name}'")
        return

    click.echo(f"\n📞 {len(rows)} call site(s) → '{name}':\n")
    for r in rows:
        caller = f"{r['caller_name']}()" if r["caller_name"] else "(top-level)"
        click.echo(f"  {r['rel_path']}  [{caller}]")


# ── Callees ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def callees(name: str, project: str | None):
    """Show what a symbol calls."""
    pname = _get_project_name(project)
    conn = _connect(pname)
    symbols = queries.get_symbol_by_name(conn, name)

    if not symbols:
        click.echo(f"No symbol '{name}'")
        return

    sym = symbols[0]
    # Only meaningful for callable symbols
    if sym["kind"] not in ("function", "method", "arrow_function"):
        click.echo(f"'{name}' ({sym['kind']}) is not callable — no callee list available")
        return

    rows = queries.find_callees(conn, sym["id"])

    if not rows:
        click.echo(f"No outbound calls for '{name}'")
        return

    click.echo(f"\n📤 '{name}' calls {len(rows)} unique function(s):\n")
    for i, r in enumerate(rows):
        click.echo(f"  {r['callee_name']:<30}", nl=(i + 1) % 4 != 0)
    if len(rows) % 4 != 0:
        click.echo()


# ── Chain ──


@cli.command()
@click.argument("name")
@click.option("--depth", default=3, help="Max depth")
@click.option("--project", default=None, help="Project name")
def chain(name: str, depth: int, project: str | None):
    """Show a call chain from a symbol."""
    from codeatlas.graph.callgraph import find_call_chain

    pname = _get_project_name(project)
    conn = _connect(pname)
    steps = find_call_chain(conn, name, depth)

    if not steps:
        click.echo(f"No call chain found for '{name}'")
        return

    click.echo(f"\n🔗 Call chain: {name}()\n")
    for d, sym, callees in steps:
        indent = "  " * (d + 1)
        click.echo(f"{indent}{sym}()")
        for callee in callees[:5]:
            click.echo(f"{indent}  → {callee}()")


# ── Graph ──


@cli.command()
@click.argument("target")
@click.option(
    "--type",
    "graph_type",
    type=click.Choice(["deps", "calls"]),
    default="deps",
    help="Graph type: file deps or symbol calls",
)
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream"]),
    default="downstream",
    help="For deps: downstream=what target imports, upstream=what imports target",
)
@click.option("--depth", default=3, help="Max BFS depth")
@click.option("--project", default=None, help="Project name")
def graph(target: str, graph_type: str, direction: str, depth: int, project: str | None):
    """Generate a Mermaid dependency/call graph."""
    pname = _get_project_name(project)
    conn = _connect(pname)

    if graph_type == "deps":
        output = deps_to_mermaid(conn, target, direction, depth)
    else:
        output = calls_to_mermaid(conn, target, depth)

    click.echo(output)


# ── Deps ──


@cli.command()
@click.argument("path")
@click.option(
    "--direction",
    type=click.Choice(["downstream", "upstream"]),
    default="downstream",
    help="downstream=what this file imports, upstream=what imports this file",
)
@click.option("--depth", default=3, help="Max BFS depth")
@click.option("--project", default=None, help="Project name")
def deps(path: str, direction: str, depth: int, project: str | None):
    """Show file dependencies."""
    from codeatlas.graph.dependency import downstream_dependencies, upstream_dependencies

    pname = _get_project_name(project)
    conn = _connect(pname)

    if direction == "downstream":
        steps = downstream_dependencies(conn, path, depth)
        arrow = "→"
    else:
        steps = upstream_dependencies(conn, path, depth)
        arrow = "←"

    if not steps:
        click.echo(f"No dependencies found for '{path}'")
        return

    click.echo(f"\n📦 Dependencies ({direction}) for '{path}':\n")
    for d, file_path, deps in steps:
        indent = "  " * d
        click.echo(f"{indent}{file_path}")
        for dep in deps:
            click.echo(f"{indent}  {arrow} {dep}")


def main():
    cli()


if __name__ == "__main__":
    main()
