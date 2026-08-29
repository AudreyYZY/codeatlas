"""Mermaid diagram output for dependency and call graphs."""

import re
import sqlite3

from codeatlas.graph.callgraph import find_call_chain
from codeatlas.graph.dependency import (
    downstream_dependencies,
    upstream_dependencies,
)

_UNSAFE = re.compile(r"[^0-9A-Za-z_]")


class _NodeIds:
    """Stable, collision-free Mermaid node ids."""

    def __init__(self) -> None:
        self._by_key: dict[str, str] = {}
        self._used: set[str] = set()

    def get(self, key: str) -> str:
        if key in self._by_key:
            return self._by_key[key]
        base = _UNSAFE.sub("_", key.rsplit("/", 1)[-1]) or "n"
        if base[0].isdigit():
            base = f"n{base}"
        node_id = base
        suffix = 1
        while node_id in self._used:
            node_id = f"{base}_{suffix}"
            suffix += 1
        self._used.add(node_id)
        self._by_key[key] = node_id
        return node_id

    def __contains__(self, key: str) -> bool:
        return key in self._by_key


def _label(text: str) -> str:
    """Quote a label so Mermaid cannot mis-parse it."""
    return text.replace('"', "&quot;").replace("[", "(").replace("]", ")")


def _wrap(lines: list[str], fenced: bool) -> str:
    if fenced:
        return "\n".join(["```mermaid", *lines, "```"])
    return "\n".join(lines)


def deps_to_mermaid(
    conn: sqlite3.Connection,
    rel_path: str,
    direction: str = "downstream",
    max_depth: int = 3,
    fenced: bool = True,
) -> str:
    """
    Generate a Mermaid ``graph TD`` for file dependencies.

    Args:
        conn: database connection.
        rel_path: starting file (relative path).
        direction: ``"downstream"`` (what it imports) or ``"upstream"``.
        max_depth: BFS depth.
        fenced: wrap in a ```mermaid code fence (CLI) or return raw (web UI).
    """
    if direction == "downstream":
        steps = downstream_dependencies(conn, rel_path, max_depth)
    else:
        steps = upstream_dependencies(conn, rel_path, max_depth)

    lines = ["graph TD"]
    ids = _NodeIds()

    def declare(path: str) -> str:
        new = path not in ids
        node_id = ids.get(path)
        if new:
            lines.append(f'    {node_id}["{_label(path.rsplit("/", 1)[-1])}"]')
        return node_id

    for _depth, path, _deps in steps:
        declare(path)

    for _depth, path, deps in steps:
        src_id = ids.get(path)
        for dep in deps:
            dep_id = declare(dep)
            if direction == "downstream":
                lines.append(f"    {src_id} --> {dep_id}")
            else:
                lines.append(f"    {dep_id} --> {src_id}")

    if len(lines) == 1:
        lines.append(f'    empty["No dependencies found for {_label(rel_path)}"]')

    return _wrap(lines, fenced)


def calls_to_mermaid(
    conn: sqlite3.Connection, symbol_name: str, max_depth: int = 3, fenced: bool = True
) -> str:
    """Generate a Mermaid ``graph TD`` for a symbol's call chain."""
    chain = find_call_chain(conn, symbol_name, max_depth)

    lines = ["graph TD"]
    ids = _NodeIds()

    def declare(name: str) -> str:
        new = name not in ids
        node_id = ids.get(name)
        if new:
            lines.append(f'    {node_id}["{_label(name)}()"]')
        return node_id

    for _depth, sym, _callees in chain:
        declare(sym)

    for _depth, sym, callees in chain:
        src_id = ids.get(sym)
        for callee in callees[:8]:
            lines.append(f"    {src_id} --> {declare(callee)}")

    if len(lines) == 1:
        lines.append(f'    empty["No calls recorded for {_label(symbol_name)}()"]')

    return _wrap(lines, fenced)


def cycles_to_mermaid(cycle_paths: list[list[str]], fenced: bool = True) -> str:
    """Render detected import cycles as a Mermaid diagram."""
    lines = ["graph LR"]
    ids = _NodeIds()
    if not cycle_paths:
        lines.append('    ok["No import cycles found"]')
        return _wrap(lines, fenced)

    for i, path in enumerate(cycle_paths):
        lines.append(f"    subgraph cycle{i + 1}[Cycle {i + 1}]")
        for node in path:
            if node not in ids:
                lines.append(f'    {ids.get(node)}["{_label(node.rsplit("/", 1)[-1])}"]')
        lines.append("    end")
        for a, b in zip(path, path[1:], strict=False):
            lines.append(f"    {ids.get(a)} --> {ids.get(b)}")
    return _wrap(lines, fenced)
