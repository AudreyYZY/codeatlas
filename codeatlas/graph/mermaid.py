"""Mermaid diagram output for dependency and call graphs."""

import sqlite3
from codeatlas.graph.dependency import (
    build_dependency_graph,
    upstream_dependencies,
    downstream_dependencies,
)
from codeatlas.graph.callgraph import build_call_graph, find_call_chain


def deps_to_mermaid(conn: sqlite3.Connection, rel_path: str, direction: str = "downstream", max_depth: int = 3) -> str:
    """
    Generate a Mermaid graph TD for file dependencies.

    Args:
        conn: database connection
        rel_path: starting file (relative path)
        direction: "downstream" (what this file depends on) or "upstream" (what depends on this file)
        max_depth: BFS depth
    """
    if direction == "downstream":
        steps = downstream_dependencies(conn, rel_path, max_depth)
        arrow = " --> "
    else:
        steps = upstream_dependencies(conn, rel_path, max_depth)
        arrow = " --> "

    lines = ["```mermaid", "graph TD"]

    # Generate compact node IDs
    node_ids: dict[str, str] = {}
    for i, (depth, path, deps) in enumerate(steps):
        short = path.rsplit("/", 1)[-1].replace(".", "_").replace("-", "_")
        node_id = f"{short}_{i}"
        node_ids[path] = node_id
        label = path.rsplit("/", 1)[-1]
        lines.append(f"    {node_id}[\"{label}\"]")

    # Generate edges
    for depth, path, deps in steps:
        src_id = node_ids[path]
        for dep in deps:
            if dep not in node_ids:
                short = dep.rsplit("/", 1)[-1].replace(".", "_").replace("-", "_")
                node_ids[dep] = f"{short}_{len(node_ids)}"
                label = dep.rsplit("/", 1)[-1]
                lines.append(f"    {node_ids[dep]}[\"{label}\"]")
            if direction == "downstream":
                lines.append(f"    {src_id}{arrow}{node_ids[dep]}")
            else:
                lines.append(f"    {node_ids[dep]}{arrow}{src_id}")

    lines.append("```")
    return "\n".join(lines)


def calls_to_mermaid(conn: sqlite3.Connection, symbol_name: str, max_depth: int = 3) -> str:
    """
    Generate a Mermaid graph TD for symbol call chains.
    """
    chain = find_call_chain(conn, symbol_name, max_depth)

    lines = ["```mermaid", "graph TD"]

    node_ids: dict[str, str] = {}
    for i, (depth, sym, callees) in enumerate(chain):
        nid = sym.replace(".", "_").replace("-", "_")
        node_ids[sym] = nid
        lines.append(f"    {nid}[\"{sym}()\"]")

    for depth, sym, callees in chain:
        src_id = node_ids[sym]
        for callee in callees[:8]:
            if callee not in node_ids:
                cid = callee.replace(".", "_").replace("-", "_")
                node_ids[callee] = cid
                lines.append(f"    {cid}[\"{callee}()\"]")
            lines.append(f"    {src_id} --> {node_ids[callee]}")

    lines.append("```")
    return "\n".join(lines)
