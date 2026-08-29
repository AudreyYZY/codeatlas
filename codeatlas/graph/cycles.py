"""Cycle detection over the file-level dependency graph.

Uses Tarjan's strongly-connected-components algorithm (iterative, so a deep
dependency chain cannot blow the Python recursion limit). Every SCC with more
than one node is an import cycle; a self-loop counts too.
"""

import sqlite3

from codeatlas.graph.dependency import build_dependency_graph


def strongly_connected_components(graph: dict[str, list[str]]) -> list[list[str]]:
    """Return the SCCs of a directed graph, largest first."""
    index_counter = 0
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    result: list[list[str]] = []

    nodes = set(graph)
    for targets in graph.values():
        nodes.update(targets)

    for root in sorted(nodes):
        if root in index:
            continue

        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_i = work[-1]

            if child_i == 0:
                index[node] = index_counter
                lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack[node] = True

            recursed = False
            children = graph.get(node, [])
            while child_i < len(children):
                child = children[child_i]
                child_i += 1
                if child not in index:
                    work[-1] = (node, child_i)
                    work.append((child, 0))
                    recursed = True
                    break
                if on_stack.get(child):
                    lowlink[node] = min(lowlink[node], index[child])
            if recursed:
                continue

            work[-1] = (node, child_i)
            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    popped = stack.pop()
                    on_stack[popped] = False
                    component.append(popped)
                    if popped == node:
                        break
                result.append(component)

            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])

    return sorted(result, key=len, reverse=True)


def find_cycles(conn: sqlite3.Connection, min_size: int = 2) -> list[list[str]]:
    """Return import cycles as lists of file paths, largest first."""
    graph = build_dependency_graph(conn)
    cycles = []
    for component in strongly_connected_components(graph):
        if len(component) >= min_size:
            cycles.append(sorted(component))
        elif len(component) == 1:
            node = component[0]
            if node in graph.get(node, []):  # self-import
                cycles.append(component)
    return cycles


def shortest_cycle_path(graph: dict[str, list[str]], component: list[str]) -> list[str]:
    """Find a concrete cycle path within an SCC, for display.

    Returns e.g. ``["a.ts", "b.ts", "c.ts", "a.ts"]``.
    """
    members = set(component)
    start = sorted(component)[0]
    # BFS back to start, staying inside the component.
    from collections import deque

    prev: dict[str, str] = {}
    queue = deque([start])
    seen = {start}
    while queue:
        node = queue.popleft()
        for nxt in graph.get(node, []):
            if nxt not in members:
                continue
            if nxt == start:
                path = [node]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                path.reverse()
                return [*path, start]
            if nxt not in seen:
                seen.add(nxt)
                prev[nxt] = node
                queue.append(nxt)
    return [*component, component[0]]
