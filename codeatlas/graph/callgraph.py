"""Call graph: build symbol-level call structures."""

import sqlite3
from collections import deque


def build_call_graph(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """
    Build a symbol-level call graph.

    Returns ``{caller_name: [callee_name, ...]}``. Callee names are the raw
    identifiers at each call site (call resolution is best-effort), ordered by
    how often they are called so the busiest edges survive fan-out limits.
    """
    rows = conn.execute(
        """SELECT s1.name AS caller, ce.callee_name AS callee, COUNT(*) AS cnt
           FROM call_edges ce
           JOIN symbols s1 ON ce.caller_symbol_id = s1.id
           WHERE ce.caller_symbol_id IS NOT NULL
           GROUP BY s1.name, ce.callee_name
           ORDER BY cnt DESC, ce.callee_name"""
    ).fetchall()

    graph: dict[str, list[str]] = {}
    for row in rows:
        graph.setdefault(row["caller"], []).append(row["callee"])
    return graph


def find_call_chain(
    conn: sqlite3.Connection,
    start_symbol: str,
    max_depth: int = 5,
    max_fanout: int = 10,
) -> list[tuple[int, str, list[str]]]:
    """
    BFS from ``start_symbol`` down its call chain.

    Returns ``[(depth, symbol, [direct_callees]), ...]``. Returns an empty list
    when the symbol makes no calls at all, so callers can distinguish "unknown
    symbol" from "leaf function".
    """
    graph = build_call_graph(conn)
    if start_symbol not in graph:
        return []

    result: list[tuple[int, str, list[str]]] = []
    visited = {start_symbol}
    queue: deque[tuple[str, int]] = deque([(start_symbol, 0)])

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            result.append((depth, current, []))
            continue
        callees = graph.get(current, [])[:max_fanout]
        result.append((depth, current, callees))
        for callee in callees:
            if callee not in visited:
                visited.add(callee)
                queue.append((callee, depth + 1))

    return result


def find_call_paths(
    conn: sqlite3.Connection, start: str, target: str, max_depth: int = 6
) -> list[str] | None:
    """Shortest call path from ``start`` to ``target``, or None."""
    graph = build_call_graph(conn)
    if start not in graph:
        return None
    prev: dict[str, str] = {}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for callee in graph.get(node, []):
            if callee in seen:
                continue
            seen.add(callee)
            prev[callee] = node
            if callee == target:
                path = [target]
                while path[-1] != start:
                    path.append(prev[path[-1]])
                return list(reversed(path))
            queue.append((callee, depth + 1))
    return None
