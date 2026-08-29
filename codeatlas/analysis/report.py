"""
Structured architecture report.

Everything here is derived from the index — no LLM, no network. The output is
a plain dict so the CLI can print it, the web UI can render it, and an agent
can paste it into a prompt.
"""

import sqlite3

from codeatlas.graph.cycles import find_cycles, shortest_cycle_path
from codeatlas.graph.dependency import build_dependency_graph
from codeatlas.storage import queries
from codeatlas.storage.schema import get_meta

# Directory names that carry a conventional meaning. Used to describe modules
# in plain language instead of just listing them.
ROLE_HINTS: dict[str, str] = {
    "app": "application routes / pages",
    "pages": "application routes / pages",
    "routes": "application routes",
    "components": "UI components",
    "ui": "UI components",
    "lib": "shared library code",
    "libs": "shared library code",
    "utils": "helpers and utilities",
    "helpers": "helpers and utilities",
    "hooks": "React hooks",
    "store": "state management",
    "stores": "state management",
    "api": "API layer",
    "server": "server-side code",
    "services": "service layer",
    "models": "data models",
    "schema": "data schema",
    "schemas": "data schema",
    "storage": "persistence layer",
    "db": "persistence layer",
    "test": "tests",
    "tests": "tests",
    "spec": "tests",
    "config": "configuration",
    "types": "type declarations",
    "cli": "command-line entry points",
    "scripts": "one-off scripts",
    "graph": "graph algorithms",
    "parser": "parsing layer",
    "indexer": "indexing pipeline",
    "scanner": "file discovery",
    "web": "web layer",
    "static": "static assets",
}


def _row_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


def describe_module(name: str) -> str | None:
    """Best-effort plain-language role for a top-level directory."""
    key = name.strip("/").split("/")[-1].lower()
    role = ROLE_HINTS.get(key)
    # Don't hand back "tests — tests"; the name already says it.
    return None if role and role.lower() == key else role


def build_report(conn: sqlite3.Connection, project_name: str = "") -> dict:
    """Assemble the full structured report for an indexed project."""
    stats = queries.get_stats(conn)
    languages = _row_dicts(queries.get_language_counts(conn))
    kinds = _row_dicts(queries.get_kind_counts(conn))
    modules = queries.get_module_breakdown(conn)
    hotspots = _row_dicts(queries.get_hotspots(conn, 12))
    entrypoints = _row_dicts(queries.get_entrypoints(conn, 12))
    orphans = _row_dicts(queries.get_orphans(conn, 20))
    externals = _row_dicts(queries.get_external_packages(conn, 15))

    graph = build_dependency_graph(conn)
    cycle_components = find_cycles(conn)
    cycles = [
        {"files": component, "path": shortest_cycle_path(graph, component)}
        for component in cycle_components[:20]
    ]

    for module in modules:
        module["role"] = describe_module(module["module"])

    largest = _row_dicts(
        conn.execute(
            """SELECT rel_path, language, lines,
                      (SELECT COUNT(*) FROM symbols s WHERE s.file_id = f.id) AS symbols
               FROM files f ORDER BY lines DESC LIMIT 12"""
        ).fetchall()
    )

    busiest = _row_dicts(
        conn.execute(
            """SELECT s.name, s.kind, f.rel_path, s.line_start,
                      COUNT(ce.id) AS outbound_calls
               FROM symbols s
               JOIN files f ON s.file_id = f.id
               JOIN call_edges ce ON ce.caller_symbol_id = s.id
               GROUP BY s.id ORDER BY outbound_calls DESC LIMIT 12"""
        ).fetchall()
    )

    most_called = _row_dicts(
        conn.execute(
            """SELECT callee_name AS name, COUNT(*) AS call_sites,
                      COUNT(DISTINCT caller_file_id) AS calling_files
               FROM call_edges
               GROUP BY callee_name ORDER BY call_sites DESC LIMIT 12"""
        ).fetchall()
    )

    report = {
        "project": project_name or get_meta(conn, "project_name", "") or "",
        "root": get_meta(conn, "project_root", ""),
        "indexed_at": get_meta(conn, "indexed_at", ""),
        "stats": stats,
        "languages": languages,
        "kinds": kinds,
        "modules": modules,
        "hotspots": hotspots,
        "entrypoints": entrypoints,
        "orphans": orphans,
        "externals": externals,
        "cycles": cycles,
        "largest_files": largest,
        "busiest_symbols": busiest,
        "most_called": most_called,
    }
    report["narrative"] = build_narrative(report)
    report["health"] = build_health(report)
    return report


def build_narrative(report: dict) -> list[dict]:
    """Turn the numbers into a handful of readable paragraphs.

    Deterministic templates — same index in, same words out.
    """
    stats = report["stats"]
    sections: list[dict] = []

    langs = report["languages"]
    lang_text = ", ".join(f"{lang['language']} ({lang['cnt']} files)" for lang in langs[:4])
    sections.append(
        {
            "title": "Overview",
            "body": (
                f"{report['project'] or 'This project'} indexes to {stats['files']} source "
                f"files and roughly {stats['lines']:,} lines, holding {stats['symbols']:,} "
                f"declarations. Languages present: {lang_text or 'none detected'}. "
                f"The files reference each other through {stats['deps']} resolved import "
                f"edges and {stats['calls']:,} recorded call sites."
            ),
        }
    )

    modules = report["modules"][:6]
    if modules:
        parts = []
        for module in modules:
            role = f" — {module['role']}" if module.get("role") else ""
            parts.append(
                f"**{module['module']}**: {module['files']} files, "
                f"{module['symbols']} symbols{role}"
            )
        sections.append(
            {
                "title": "How the code is organised",
                "body": ("Top-level directories, largest first:\n\n- " + "\n- ".join(parts)),
            }
        )

    if report["entrypoints"]:
        names = ", ".join(f"`{e['rel_path']}`" for e in report["entrypoints"][:5])
        sections.append(
            {
                "title": "Where to start reading",
                "body": (
                    f"No other indexed file imports {names}. Those are the project's "
                    "entry points — CLI mains, route files, or (occasionally) dead code. "
                    "Read them first: everything else hangs off them."
                ),
            }
        )

    if report["hotspots"]:
        top = report["hotspots"][0]
        names = ", ".join(f"`{h['rel_path']}` ({h['dependents']})" for h in report["hotspots"][:5])
        sections.append(
            {
                "title": "Load-bearing modules",
                "body": (
                    f"Ranked by how many files import them: {names}. "
                    f"`{top['rel_path']}` has the widest blast radius — a change there "
                    f"reaches {top['dependents']} direct dependents, so it is the file to "
                    "understand before refactoring anything."
                ),
            }
        )

    if report["cycles"]:
        example = report["cycles"][0]["path"]
        arrow = " → ".join(p.rsplit("/", 1)[-1] for p in example)
        sections.append(
            {
                "title": "Import cycles",
                "body": (
                    f"{len(report['cycles'])} cycle(s) detected. Example: {arrow}. "
                    "Cycles make modules impossible to load or test in isolation and "
                    "often signal a missing shared module that both sides should depend on."
                ),
            }
        )
    else:
        sections.append(
            {
                "title": "Import cycles",
                "body": "None. The file-level dependency graph is acyclic.",
            }
        )

    if report["externals"]:
        names = ", ".join(f"`{e['source_path']}`" for e in report["externals"][:8])
        sections.append(
            {
                "title": "External surface",
                "body": (
                    f"Most-used third-party imports: {names}. These are the libraries "
                    "whose idioms show up throughout the codebase."
                ),
            }
        )

    if report["orphans"]:
        sections.append(
            {
                "title": "Unconnected files",
                "body": (
                    f"{len(report['orphans'])} file(s) neither import nor are imported by "
                    "anything indexed. Usually configuration, generated code, or code that "
                    "is no longer reachable — worth a look."
                ),
            }
        )

    return sections


def build_health(report: dict) -> list[dict]:
    """A few blunt signals worth surfacing at a glance."""
    stats = report["stats"]
    signals: list[dict] = []

    total_deps = stats["deps"] + stats["unresolved_deps"]
    if total_deps:
        ratio = stats["unresolved_deps"] / total_deps
        signals.append(
            {
                "label": "Import resolution",
                "value": f"{100 * (1 - ratio):.0f}%",
                "status": "good" if ratio < 0.1 else ("warn" if ratio < 0.3 else "bad"),
                "detail": (
                    f"{stats['unresolved_deps']} in-project import(s) could not be matched "
                    "to a file. High numbers usually mean a missing path alias config."
                ),
            }
        )

    cycle_count = len(report["cycles"])
    signals.append(
        {
            "label": "Import cycles",
            "value": str(cycle_count),
            "status": "good" if cycle_count == 0 else ("warn" if cycle_count < 5 else "bad"),
            "detail": "Strongly connected components in the file dependency graph.",
        }
    )

    if report["largest_files"]:
        biggest = report["largest_files"][0]
        signals.append(
            {
                "label": "Largest file",
                "value": f"{biggest['lines']:,} lines",
                "status": (
                    "good"
                    if biggest["lines"] < 500
                    else ("warn" if biggest["lines"] < 1500 else "bad")
                ),
                "detail": biggest["rel_path"],
            }
        )

    orphan_count = len(report["orphans"])
    if stats["files"]:
        share = orphan_count / stats["files"]
        signals.append(
            {
                "label": "Unconnected files",
                "value": str(orphan_count),
                "status": "good" if share < 0.1 else ("warn" if share < 0.25 else "bad"),
                "detail": "Files with no in-project dependency in either direction.",
            }
        )

    return signals


def report_to_markdown(report: dict) -> str:
    """Render the report as Markdown — for `codeatlas explain` and for pasting into an LLM."""
    lines = [f"# {report['project'] or 'Project'} — architecture report", ""]
    if report.get("root"):
        lines += [f"`{report['root']}`", ""]

    for section in report["narrative"]:
        lines += [f"## {section['title']}", "", section["body"], ""]

    lines += ["## Signals", ""]
    for signal in report["health"]:
        lines.append(f"- **{signal['label']}**: {signal['value']} — {signal['detail']}")
    lines.append("")

    if report["hotspots"]:
        lines += [
            "## Most depended-upon files",
            "",
            "| File | Dependents | Lines |",
            "|---|---|---|",
        ]
        for hot in report["hotspots"]:
            lines.append(f"| `{hot['rel_path']}` | {hot['dependents']} | {hot['lines']} |")
        lines.append("")

    if report["cycles"]:
        lines += ["## Import cycles", ""]
        for cycle in report["cycles"]:
            lines.append("- " + " → ".join(cycle["path"]))
        lines.append("")

    return "\n".join(lines)
