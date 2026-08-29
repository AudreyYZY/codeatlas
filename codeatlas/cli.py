"""Unified CLI for codeatlas."""

import json
import os
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager

import click

from codeatlas.config import detect_project_name, get_project_dir, list_projects
from codeatlas.graph.mermaid import calls_to_mermaid, cycles_to_mermaid, deps_to_mermaid
from codeatlas.indexer.indexer import index_project
from codeatlas.storage import queries

__version__ = "0.3.0"


def _get_project_name(project_arg: str | None = None) -> str:
    """Determine project name: explicit arg → current dir name."""
    if project_arg:
        return project_arg
    return detect_project_name(".")


def _connect(project_name: str) -> sqlite3.Connection:
    # Deliberately does NOT use get_db_path(), which creates the directory —
    # a typo'd project name should not leave an empty folder behind.
    db_path = os.path.join(get_project_dir(project_name), "index.db")
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


@contextmanager
def _project_conn(project_arg: str | None) -> Iterator[tuple[str, sqlite3.Connection]]:
    """Yield (project_name, connection), always closing the connection."""
    pname = _get_project_name(project_arg)
    conn = _connect(pname)
    try:
        yield pname, conn
    finally:
        conn.close()


# ── CLI Entry Point ──


@click.group()
@click.version_option(version=__version__, prog_name="codeatlas")
def cli():
    """codeatlas — a local-first, language-aware code knowledge base.

    Index, query, and visualize TypeScript, JavaScript and Python projects.
    """


# ── Index ──


@cli.command()
@click.argument("path", default=".")
@click.option("--name", default=None, help="Project name (default: directory name)")
@click.option("--verbose", "-v", is_flag=True, help="Print per-file progress")
@click.option(
    "--incremental/--full",
    default=False,
    help="Reuse rows for files whose content is unchanged (default: full re-index)",
)
def index(path: str, name: str | None, verbose: bool, incremental: bool):
    """Index a TypeScript / JavaScript / Python project."""
    try:
        index_project(path, name, verbose, incremental=incremental)
    except NotADirectoryError as e:
        click.echo(str(e), err=True)
        sys.exit(1)


# ── Projects ──


@cli.command(name="projects")
def projects_cmd():
    """List every indexed project."""
    names = list_projects()
    if not names:
        click.echo("No projects indexed yet. Run: codeatlas index <path>")
        return
    click.echo(f"\n📚 {len(names)} indexed project(s):\n")
    for name in names:
        try:
            conn = sqlite3.connect(os.path.join(get_project_dir(name), "index.db"))
            conn.row_factory = sqlite3.Row
            stats = queries.get_stats(conn)
            click.echo(f"  {name:<28} {stats['files']:>5} files  {stats['symbols']:>6} symbols")
            conn.close()
        except sqlite3.Error:
            click.echo(f"  {name:<28} (unreadable)")


# ── Stats ──


@cli.command()
@click.option("--project", default=None, help="Project name")
def stats(project: str | None):
    """Show index statistics."""
    with _project_conn(project) as (pname, conn):
        s = queries.get_stats(conn)
        kinds = queries.get_kind_counts(conn)
        langs = queries.get_language_counts(conn)
        top = queries.get_top_imports(conn)

        click.echo(f"\n📊 {pname}")
        click.echo(f"   Files:   {s['files']}")
        click.echo(f"   Lines:   {s['lines']:,}")
        click.echo(f"   Symbols: {s['symbols']}")
        click.echo(f"   Imports: {s['imports']}")
        click.echo(f"   Calls:   {s['calls']}")
        click.echo(f"   Deps:    {s['deps']} resolved, {s['unresolved_deps']} unresolved")

        click.echo("\n   Languages:")
        for r in langs:
            click.echo(f"     {r['language']:<18} {r['cnt']:>5} files  {r['lines']:>8,} lines")

        click.echo("\n   Symbol kinds:")
        for r in kinds:
            click.echo(f"     {r['kind']:<18} {r['cnt']:>5}")

        click.echo("\n   Top imports:")
        for r in top:
            click.echo(f"     {r['source_path']:<45} {r['cnt']:>3}")


# ── Explain ──


@cli.command()
@click.option("--project", default=None, help="Project name")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw report as JSON")
def explain(project: str | None, as_json: bool):
    """Print a structured architecture report for the project."""
    from codeatlas.analysis.report import build_report, report_to_markdown

    with _project_conn(project) as (pname, conn):
        report = build_report(conn, pname)
        if as_json:
            click.echo(json.dumps(report, indent=2, default=str))
        else:
            click.echo(report_to_markdown(report))


# ── Cycles ──


@cli.command()
@click.option("--project", default=None, help="Project name")
@click.option("--mermaid", is_flag=True, help="Emit a Mermaid diagram instead of a list")
def cycles(project: str | None, mermaid: bool):
    """Detect circular imports between files."""
    from codeatlas.graph.cycles import find_cycles, shortest_cycle_path
    from codeatlas.graph.dependency import build_dependency_graph

    with _project_conn(project) as (_pname, conn):
        graph = build_dependency_graph(conn)
        components = find_cycles(conn)

        if not components:
            click.echo("✅ No import cycles found.")
            return

        paths = [shortest_cycle_path(graph, component) for component in components]
        if mermaid:
            click.echo(cycles_to_mermaid(paths))
            return

        click.echo(f"\n🔁 {len(components)} import cycle(s):\n")
        for i, path in enumerate(paths, 1):
            click.echo(f"  {i}. " + " → ".join(path))


# ── Symbols ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def symbols(name: str, project: str | None):
    """Find symbols by name (use * as a wildcard)."""
    with _project_conn(project) as (_pname, conn):
        rows = queries.find_symbols(conn, name)
        if not rows:
            rows = queries.search_symbols(conn, name)

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
    with _project_conn(project) as (_pname, conn):
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
    with _project_conn(project) as (_pname, conn):
        rows = queries.find_imports_of_symbol(conn, name)

        if not rows:
            click.echo(f"No files import '{name}'")
            return

        click.echo(f"\n📥 {len(rows)} file(s) import '{name}':\n")
        for r in rows:
            alias = f" as {r['alias_name']}" if r["alias_name"] else ""
            resolved = f" → {r['resolved_path']}" if r["resolved_path"] else ""
            line = f"  {r['importer']}:{r['line']}  ← {r['source_path']}"
            line += f" ({r['import_type']}{alias}){resolved}"
            click.echo(line)


# ── Used-by ──


@cli.command(name="used-by")
@click.argument("module")
@click.option("--project", default=None, help="Project name")
def used_by(module: str, project: str | None):
    """Show which files import from a module."""
    with _project_conn(project) as (_pname, conn):
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


@cli.command(name="list")
@click.option("--kind", default=None, help="Filter by kind (function, class, interface, ...)")
@click.option("--exported", is_flag=True, help="Only exported symbols")
@click.option("--limit", default=0, help="Cap the number of rows (0 = no cap)")
@click.option("--project", default=None, help="Project name")
def list_cmd(kind: str | None, exported: bool, limit: int, project: str | None):
    """List symbols, optionally filtered."""
    with _project_conn(project) as (_pname, conn):
        rows = queries.list_symbols(conn, kind, exported, limit)

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
    with _project_conn(project) as (_pname, conn):
        rows = queries.find_callers(conn, name)

        if not rows:
            click.echo(f"No callers found for '{name}'")
            return

        click.echo(f"\n📞 {len(rows)} call site(s) → '{name}':\n")
        for r in rows:
            caller = f"{r['caller_name']}()" if r["caller_name"] else "(top-level)"
            loc = f":{r['line']}" if r["line"] else ""
            click.echo(f"  {r['rel_path']}{loc}  [{caller}]")


# ── Callees ──


@cli.command()
@click.argument("name")
@click.option("--project", default=None, help="Project name")
def callees(name: str, project: str | None):
    """Show what a symbol calls."""
    with _project_conn(project) as (_pname, conn):
        found = queries.get_symbol_by_name(conn, name)

        if not found:
            click.echo(f"No symbol '{name}'")
            return

        sym = found[0]
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

    with _project_conn(project) as (_pname, conn):
        steps = find_call_chain(conn, name, depth)

        if not steps:
            click.echo(f"No call chain found for '{name}'")
            return

        click.echo(f"\n🔗 Call chain: {name}()\n")
        for d, sym, callee_names in steps:
            indent = "  " * (d + 1)
            click.echo(f"{indent}{sym}()")
            for callee in callee_names[:5]:
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
    with _project_conn(project) as (_pname, conn):
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

    with _project_conn(project) as (_pname, conn):
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
        for d, file_path, dep_list in steps:
            indent = "  " * d
            click.echo(f"{indent}{file_path}")
            for dep in dep_list:
                click.echo(f"{indent}  {arrow} {dep}")


# ── Export ──


@cli.command(name="export")
@click.option("--project", default=None, help="Project name")
@click.option(
    "--out", "-o", default="codeatlas.json", help="Output file (use - for stdout)", type=str
)
def export_cmd(project: str | None, out: str):
    """Export the whole index as JSON (for external tools or an LLM prompt)."""
    from codeatlas.analysis.report import build_report

    with _project_conn(project) as (pname, conn):
        payload = {
            "report": build_report(conn, pname),
            "files": [dict(r) for r in queries.get_files(conn)],
            "symbols": [dict(r) for r in queries.list_symbols(conn)],
        }
        text = json.dumps(payload, indent=2, default=str)
        if out == "-":
            click.echo(text)
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(text)
            click.echo(f"Wrote {out} ({len(text):,} bytes)")


# ── Serve ──


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8000, help="Bind port")
@click.option("--open/--no-open", "open_browser", default=True, help="Open a browser window")
def serve(host: str, port: int, open_browser: bool):
    """Start the web UI: import a project, index it, explore it visually."""
    try:
        import uvicorn
    except ImportError:
        click.echo(
            'The web UI needs extra packages. Install them with:\n  pip install "codeatlas[web]"',
            err=True,
        )
        sys.exit(1)

    from codeatlas.web.server import create_app

    url = f"http://{host}:{port}"
    click.echo(f"🌐 CodeAtlas UI → {url}")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


def main():
    cli()


if __name__ == "__main__":
    main()
