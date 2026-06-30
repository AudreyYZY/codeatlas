"""Dependency graph: build file-level dependency structures."""

import sqlite3
from collections import defaultdict, deque

from codeatlas.storage import queries


def build_dependency_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """
    Build a file-level dependency graph (adjacency list).
    Returns {source_rel_path: [target_rel_path, ...]} for resolved edges only.
    """
    edges = queries.get_all_dependencies(conn)
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = edge["source_rel"]
        target = edge["target_rel"]
        if source and target:
            graph[source].append(target)
    return dict(graph)


def build_reverse_dependency_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Build reverse dep graph: {file: [files that depend on it]}."""
    edges = queries.get_all_dependencies(conn)
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = edge["source_rel"]
        target = edge["target_rel"]
        if source and target:
            graph[target].append(source)
    return dict(graph)


def upstream_dependencies(
    conn: sqlite3.Connection, rel_path: str, max_depth: int = 3
) -> list[tuple[int, str, list[str]]]:
    """
    Breadth-first search of upstream dependencies.
    Returns [(depth, file_path, [direct_dependents]), ...]
    """
    g = build_reverse_dependency_graph(conn)
    visited = set()
    result: list[tuple[int, str, list[str]]] = []
    queue = deque([(rel_path, 0)])
    visited.add(rel_path)

    while queue and (queue[0][1] < max_depth):
        current, depth = queue.popleft()
        deps = g.get(current, [])
        result.append((depth, current, deps))
        for dep in deps:
            if dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))

    return result


def downstream_dependencies(
    conn: sqlite3.Connection, rel_path: str, max_depth: int = 3
) -> list[tuple[int, str, list[str]]]:
    """
    Breadth-first search of downstream dependencies.
    Returns [(depth, file_path, [direct_dependencies]), ...]
    """
    g = build_dependency_graph(conn)
    visited = set()
    result: list[tuple[int, str, list[str]]] = []
    queue = deque([(rel_path, 0)])
    visited.add(rel_path)

    while queue and (queue[0][1] < max_depth):
        current, depth = queue.popleft()
        deps = g.get(current, [])
        result.append((depth, current, deps))
        for dep in deps:
            if dep not in visited:
                visited.add(dep)
                queue.append((dep, depth + 1))

    return result
