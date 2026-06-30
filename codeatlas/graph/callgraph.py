"""Call graph: build symbol-level call structures."""

import sqlite3
from collections import defaultdict, deque

from codeatlas.storage import queries


def build_call_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """
    Build a symbol-level call graph.
    Returns {caller_name: [callee_name, ...]} for resolved edges.
    """
    # Get all resolved call edges with both caller and callee info
    rows = conn.execute(
        """SELECT DISTINCT s1.name as caller, ce.callee_name as callee
           FROM call_edges ce
           JOIN symbols s1 ON ce.caller_symbol_id = s1.id
           WHERE ce.caller_symbol_id IS NOT NULL"""
    ).fetchall()

    graph: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        graph[row["caller"]].append(row["callee"])
    return dict(graph)


def find_call_chain(
    conn: sqlite3.Connection, start_symbol: str, max_depth: int = 5
) -> list[tuple[int, str, list[str]]]:
    """
    BFS from start_symbol to find its call chain.
    Returns [(depth, symbol, [direct_callees]), ...]
    """
    g = build_call_graph(conn)
    visited = set()
    result: list[tuple[int, str, list[str]]] = []
    queue = deque([(start_symbol, 0)])
    visited.add(start_symbol)

    while queue and (queue[0][1] < max_depth):
        current, depth = queue.popleft()
        callees = g.get(current, [])
        result.append((depth, current, callees))
        for callee in callees[:10]:  # limit expansion
            if callee not in visited:
                visited.add(callee)
                queue.append((callee, depth + 1))

    return result
