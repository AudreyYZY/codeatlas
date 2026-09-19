"""File outlines and conservative, identity-preserving call graphs.

A call is linked to a declaration only when a direct local name or an explicit
resolved import identifies exactly one callable. Member calls and ambiguous
names stay visible as unresolved leaves rather than inventing relationships.
"""

import sqlite3
from collections import defaultdict, deque

CALLABLE_KINDS = {"function", "method", "arrow_function", "generator"}


def project_structure(conn: sqlite3.Connection) -> dict:
    files = [
        dict(r)
        for r in conn.execute("SELECT id, rel_path, language, lines FROM files ORDER BY rel_path")
    ]
    symbols = [
        dict(r)
        for r in conn.execute(
            "SELECT s.*, f.rel_path FROM symbols s JOIN files f ON f.id=s.file_id "
            "ORDER BY f.rel_path, s.line_start, s.id"
        )
    ]
    outlines: dict[int, list[dict]] = defaultdict(list)
    for symbol in symbols:
        outlines[symbol["file_id"]].append(symbol)
    tree: dict = {"name": "(root)", "kind": "directory", "children": {}}
    for file in files:
        cursor = tree
        parts = file["rel_path"].split("/")
        for part in parts[:-1]:
            cursor = cursor["children"].setdefault(
                part, {"name": part, "kind": "directory", "children": {}}
            )
        cursor["children"][parts[-1]] = {
            **file,
            "name": parts[-1],
            "kind": "file",
            "symbols": outlines[file["id"]],
        }

    def flatten(node: dict) -> dict:
        if node["kind"] == "directory":
            node["children"] = [
                flatten(n)
                for n in sorted(
                    node["children"].values(), key=lambda n: (n["kind"] != "directory", n["name"])
                )
            ]
        return node

    return {
        "tree": flatten(tree),
        "symbols": symbols,
        "files": len(files),
        "scope": "Indexed TypeScript, JavaScript and Python source files only.",
    }


def call_graph(
    conn: sqlite3.Connection,
    focus: int | None = None,
    depth: int = 2,
    direction: str = "both",
    limit: int = 300,
    include_unresolved: bool = True,
) -> dict:
    symbols = [
        dict(r)
        for r in conn.execute(
            "SELECT s.*, f.rel_path FROM symbols s JOIN files f ON f.id=s.file_id ORDER BY s.id"
        )
        if r["kind"] in CALLABLE_KINDS
    ]
    by_id = {s["id"]: s for s in symbols}
    if focus is not None and focus not in by_id:
        raise ValueError("Unknown callable symbol")
    names: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for symbol in symbols:
        names[(symbol["file_id"], symbol["name"])].append(symbol)
    imports: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM imports WHERE resolved_file_id IS NOT NULL"):
        imports[(row["file_id"], row["alias_name"] or row["symbol_name"])].append(dict(row))
    nodes = {
        f"s:{s['id']}": {
            "id": f"s:{s['id']}",
            "symbol_id": s["id"],
            "label": s["name"],
            "path": s["rel_path"],
            "line": s["line_start"],
            "kind": s["kind"],
            "unresolved": False,
        }
        for s in symbols
    }
    edges: dict[tuple[str, str], dict] = {}
    for call in conn.execute("SELECT * FROM call_edges ORDER BY id"):
        caller = by_id.get(call["caller_symbol_id"])
        if not caller:
            continue
        source = f"s:{caller['id']}"
        name = call["callee_name"]
        candidates = []
        resolution = "unresolved"
        if not call["is_member"]:
            # Nested names cannot be selected safely without lexical-scope data.
            candidates = [s for s in names[(caller["file_id"], name)] if not s["parent_symbol"]]
            if len(candidates) == 1:
                resolution = "local"
            elif not candidates:
                for imp in imports[(caller["file_id"], name)]:
                    candidates.extend(
                        s
                        for s in names[(imp["resolved_file_id"], imp["symbol_name"])]
                        if not s["parent_symbol"]
                    )
                if len({s["id"] for s in candidates}) == 1:
                    resolution = "import"
        if resolution != "unresolved":
            target = f"s:{candidates[0]['id']}"
        else:
            target = f"u:{caller['id']}:{int(call['is_member'])}:{name}"
            nodes.setdefault(
                target,
                {
                    "id": target,
                    "symbol_id": None,
                    "label": name,
                    "path": caller["rel_path"],
                    "line": call["line"],
                    "kind": "member / dynamic" if call["is_member"] else "external / ambiguous",
                    "unresolved": True,
                },
            )
        edge = edges.setdefault(
            (source, target),
            {"source": source, "target": target, "resolution": resolution, "sites": []},
        )
        edge["sites"].append(call["line"])
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        outgoing[source].add(target)
        incoming[target].add(source)
    root = f"s:{focus}" if focus is not None else None
    levels = {}
    if root:
        # Traverse callers and callees independently. Alternating directions
        # would drag a caller's unrelated callees into the focused view.
        levels[root] = 0
        for adjacency, sign, enabled in (
            (outgoing, 1, direction in ("both", "downstream")),
            (incoming, -1, direction in ("both", "upstream")),
        ):
            if not enabled:
                continue
            visited = {root: 0}
            queue = deque([root])
            while queue:
                node = queue.popleft()
                if visited[node] >= depth:
                    continue
                for neighbour in sorted(adjacency[node]):
                    if neighbour not in visited:
                        visited[neighbour] = visited[node] + 1
                        levels.setdefault(neighbour, sign * visited[neighbour])
                        queue.append(neighbour)
        keep = set(levels)
    else:
        keep = set(nodes)
    if not include_unresolved:
        keep = {n for n in keep if not nodes[n]["unresolved"]}
    total = len(keep)
    ordered = sorted(
        keep,
        key=lambda n: (
            n != root,
            abs(levels.get(n, 0)),
            nodes[n]["unresolved"],
            -(len(incoming[n]) + len(outgoing[n])),
            nodes[n]["path"],
            n,
        ),
    )[:limit]
    keep = set(ordered)
    return {
        "nodes": [
            {
                **nodes[n],
                "depth": abs(levels.get(n, 0)),
                "layer": levels.get(n, 0),
                "is_focus": n == root,
            }
            for n in ordered
        ],
        "edges": [e for (s, t), e in edges.items() if s in keep and t in keep],
        "total_nodes": total,
        "shown_nodes": len(keep),
        "truncated": total > len(keep),
        "note": "Direct local/import calls are linked conservatively. Unresolved member, "
        "external and ambiguous calls remain separate leaves; this is not a runtime trace.",
    }
