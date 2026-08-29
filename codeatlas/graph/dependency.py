"""Dependency graph: build file-level dependency structures."""

import sqlite3
from collections import deque

from codeatlas.storage import queries


def _adjacency(conn: sqlite3.Connection, reverse: bool) -> dict[str, list[str]]:
    edges = queries.get_all_dependencies(conn)
    graph: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        source = edge["source_rel"]
        target = edge["target_rel"]
        if not source or not target:
            continue
        a, b = (target, source) if reverse else (source, target)
        if (a, b) in seen:
            continue
        seen.add((a, b))
        graph.setdefault(a, []).append(b)
    for targets in graph.values():
        targets.sort()
    return graph


def build_dependency_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """{source_rel_path: [target_rel_path, ...]} for resolved edges, deduplicated."""
    return _adjacency(conn, reverse=False)


def build_reverse_dependency_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """{file: [files that depend on it]}."""
    return _adjacency(conn, reverse=True)


def _bfs(
    graph: dict[str, list[str]], start: str, max_depth: int, max_fanout: int
) -> list[tuple[int, str, list[str]]]:
    """Level-order walk from ``start``, recording each node's direct edges."""
    result: list[tuple[int, str, list[str]]] = []
    visited = {start}
    queue: deque[tuple[str, int]] = deque([(start, 0)])

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            # Still report the node so the caller sees the frontier, but do
            # not expand past the requested depth.
            result.append((depth, current, []))
            continue
        neighbours = graph.get(current, [])[:max_fanout]
        result.append((depth, current, neighbours))
        for neighbour in neighbours:
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append((neighbour, depth + 1))
    return result


def upstream_dependencies(
    conn: sqlite3.Connection, rel_path: str, max_depth: int = 3, max_fanout: int = 25
) -> list[tuple[int, str, list[str]]]:
    """BFS over files that depend on ``rel_path``."""
    return _bfs(build_reverse_dependency_graph(conn), rel_path, max_depth, max_fanout)


def downstream_dependencies(
    conn: sqlite3.Connection, rel_path: str, max_depth: int = 3, max_fanout: int = 25
) -> list[tuple[int, str, list[str]]]:
    """BFS over files that ``rel_path`` depends on."""
    return _bfs(build_dependency_graph(conn), rel_path, max_depth, max_fanout)
