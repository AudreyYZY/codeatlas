"""Evidence-backed architecture, file relationships and implementation reading."""

import json
import sqlite3
from collections import defaultdict, deque

from codeatlas.analysis.report import describe_module
from codeatlas.analysis.structure import CALLABLE_KINDS, call_graph


def _load_facts(conn: sqlite3.Connection, file_id: int | None = None) -> dict[int, dict]:
    try:
        rows = conn.execute(
            "SELECT * FROM file_analyses" + (" WHERE file_id=?" if file_id is not None else ""),
            (file_id,) if file_id is not None else (),
        )
        return {r["file_id"]: json.loads(r["payload"]) for r in rows}
    except sqlite3.OperationalError:
        return {}


def _resolve_calls(conn: sqlite3.Connection, facts: dict[int, dict]) -> dict:
    declarations: dict[tuple[int, str], list[dict]] = defaultdict(list)
    bindings: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM symbols"):
        declarations[(r["file_id"], r["name"])].append(dict(r))
    for r in conn.execute(
        "SELECT * FROM imports WHERE resolved_file_id IS NOT NULL AND NOT is_type_import"
    ):
        bindings[(r["file_id"], r["alias_name"] or r["symbol_name"])].append(dict(r))
    targets = {}
    for file_id, payload in facts.items():
        if payload["parse_has_errors"]:
            continue
        for function in payload["functions"]:
            for call in function["calls"]:
                if call["shadowed"]:
                    continue
                ref = call["ref"]
                candidates = []
                if "." not in ref:
                    local = declarations[(file_id, ref)]
                    if local:
                        candidates = [
                            s
                            for s in local
                            if s["kind"] in CALLABLE_KINDS and not s["parent_symbol"]
                        ]
                    else:
                        for imp in bindings[(file_id, ref)]:
                            # A default import must match the default export, not
                            # the receiving file's local alias spelling.
                            if imp["import_type"] == "default":
                                candidates.extend(
                                    s
                                    for (fid, _), group in declarations.items()
                                    if fid == imp["resolved_file_id"]
                                    for s in group
                                    if s["is_default_export"] and s["kind"] in CALLABLE_KINDS
                                )
                            else:
                                candidates.extend(
                                    s
                                    for s in declarations[
                                        (imp["resolved_file_id"], imp["symbol_name"])
                                    ]
                                    if s["kind"] in CALLABLE_KINDS and not s["parent_symbol"]
                                )
                elif len(ref.split(".")) == 2:
                    namespace, name = ref.split(".")
                    if declarations[(file_id, namespace)]:
                        continue
                    for imp in bindings[(file_id, namespace)]:
                        if imp["import_type"] in {"namespace", "module"}:
                            candidates.extend(
                                s
                                for s in declarations[(imp["resolved_file_id"], name)]
                                if s["kind"] in CALLABLE_KINDS and not s["parent_symbol"]
                            )
                unique = {s["id"]: s for s in candidates}
                if len(unique) == 1:
                    targets[(file_id, function["line"], call["key"])] = next(iter(unique.values()))
    return targets


def relationship_graph(
    conn: sqlite3.Connection,
    kind: str = "all",
    focus: str | None = None,
    depth: int = 1,
    limit: int = 150,
    include_tests: bool = False,
) -> dict:
    files = [
        dict(r)
        for r in conn.execute("SELECT id, rel_path, language, lines FROM files ORDER BY rel_path")
    ]
    paths = {f["id"]: f["rel_path"] for f in files}
    facts = _load_facts(conn)
    targets = _resolve_calls(conn, facts)
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    def add(src, dst, edge_kind, evidence):
        if src in paths and dst in paths and src != dst:
            grouped[(paths[src], paths[dst], edge_kind)].append(evidence)

    for imp in conn.execute("SELECT * FROM imports WHERE resolved_file_id IS NOT NULL"):
        add(
            imp["file_id"],
            imp["resolved_file_id"],
            "import",
            {
                "line": imp["line"],
                "symbol": imp["symbol_name"],
                "via": paths[imp["file_id"]],
                "type_only": bool(imp["is_type_import"]),
            },
        )
    # The graph is uncapped at construction so relationship counts are not based
    # on a display slice. Unresolved call names never become file edges.
    graph = call_graph(conn, limit=1_000_000, include_unresolved=False)
    nodes = {n["id"]: n for n in graph["nodes"]}
    for edge in graph["edges"]:
        source, target = nodes[edge["source"]], nodes[edge["target"]]
        source_file = next((fid for fid, path in paths.items() if path == source["path"]), None)
        if source_file in facts:
            # Rich AST resolution includes shadow checks; legacy name matching
            # is only a fallback for older indexes without implementation facts.
            continue
        if source["path"] != target["path"]:
            grouped[(source["path"], target["path"], "call")].append(
                {
                    "via": source["path"],
                    "line": edge["sites"][0],
                    "lines": edge["sites"],
                    "caller": source["label"],
                    "callee": target["label"],
                    "resolution": edge["resolution"],
                }
            )
    for file_id, payload in facts.items():
        for function in payload["functions"]:
            for call in function["calls"]:
                target = targets.get((file_id, function["line"], call["key"]))
                if target is None:
                    continue
                detail = {
                    "via": paths[file_id],
                    "line": call["line"],
                    "caller": function["name"],
                    "callee": target["name"],
                    "callee_line": target["line_start"],
                    "arguments": call["arguments"],
                    "result": call["result_name"],
                }
                add(
                    file_id,
                    target["file_id"],
                    "call",
                    {**detail, "resolution": "AST direct/import"},
                )
                if call["arguments"]:
                    add(file_id, target["file_id"], "argument", detail)
                if call["result_used"]:
                    add(target["file_id"], file_id, "return", detail)
                for handoff in call["handoffs"]:
                    provider = targets.get((file_id, function["line"], handoff["provider"]))
                    if provider:
                        add(
                            provider["file_id"],
                            target["file_id"],
                            "handoff",
                            {
                                **detail,
                                "producer": provider["name"],
                                "producer_line": provider["line_start"],
                                "variable": handoff["variable"],
                                "argument_index": handoff["argument_index"],
                            },
                        )
    visible_files = [f for f in files if include_tests or not is_test(f["rel_path"])]
    allowed = {f["rel_path"] for f in visible_files}
    if focus is not None and focus not in allowed:
        raise ValueError("Unknown or excluded file")
    edges: list[dict] = []
    for (source, target, edge_kind), evidence in sorted(grouped.items()):
        if source not in allowed or target not in allowed:
            continue
        if kind == "data" and edge_kind not in {"argument", "return", "handoff"}:
            continue
        if kind not in {"all", "data"} and edge_kind != kind:
            continue
        # Deduplicate recorded versus richer AST call evidence by callsite pair.
        unique = {
            (
                e.get("line"),
                e.get("caller"),
                e.get("callee"),
                e.get("symbol"),
                e.get("variable"),
                e.get("argument_index"),
            ): e
            for e in evidence
        }
        evidence = list(unique.values())
        edges.append(
            {
                "source": source,
                "target": target,
                "kind": edge_kind,
                "count": len(evidence),
                "evidence": evidence[:100],
                "evidence_truncated": len(evidence) > 100,
            }
        )
    layers = {}
    if focus:
        adjacency: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            adjacency[edge["source"]].add(edge["target"])
            adjacency[edge["target"]].add(edge["source"])
        layers[focus] = 0
        queue = deque([focus])
        while queue:
            src = queue.popleft()
            if layers[src] >= depth:
                continue
            for dst in sorted(adjacency[src]):
                if dst not in layers:
                    layers[dst] = layers[src] + 1
                    queue.append(dst)
        allowed &= set(layers)
    degree: dict[str, int] = defaultdict(int)
    for edge in edges:
        degree[edge["source"]] += edge["count"]
        degree[edge["target"]] += edge["count"]
    ordered = sorted(allowed, key=lambda p: (p != focus, layers.get(p, 0), -degree[p], p))
    keep = set(ordered[:limit])
    return {
        "nodes": [
            {
                "id": f["rel_path"],
                "label": f["rel_path"].rsplit("/", 1)[-1],
                "path": f["rel_path"],
                "language": f["language"],
                "lines": f["lines"],
                "layer": layers.get(f["rel_path"], 0),
                "is_focus": f["rel_path"] == focus,
                "is_test": is_test(f["rel_path"]),
            }
            for f in visible_files
            if f["rel_path"] in keep
        ],
        "edges": [e for e in edges if e["source"] in keep and e["target"] in keep],
        "total_nodes": len(allowed),
        "shown_nodes": len(keep),
        "truncated": len(allowed) > len(keep),
        "analysis_files": len(facts),
        "indexed_files": len(files),
        "note": "Imports/calls describe code structure. Argument and return arrows describe static "
        "data direction; handoffs link a direct result to a later argument in the same "
        "straight-line scope. No runtime, mutation or branch-join inference.",
    }


def is_test(path: str) -> bool:
    parts = path.lower().split("/")
    return any(p in {"tests", "test", "__tests__", "fixtures"} for p in parts[:-1]) or bool(
        parts[-1].startswith("test_") or ".test." in parts[-1] or ".spec." in parts[-1]
    )


def architecture_graph(
    conn: sqlite3.Connection, level: int = 2, include_tests: bool = False, limit: int = 80
) -> dict:
    graph = relationship_graph(conn, limit=1_000_000, include_tests=include_tests)
    modules: dict[str, dict] = {}
    membership = {}
    for file in graph["nodes"]:
        parent = file["path"].split("/")[:-1]
        module = "/".join(parent[:level]) or "(root)"
        membership[file["id"]] = module
        info = modules.setdefault(
            module,
            {
                "id": module,
                "label": module,
                "files": [],
                "lines": 0,
                "role": describe_module(module.split("/")[-1]),
            },
        )
        info["files"].append(file["path"])
        info["lines"] += file["lines"]
    links: dict[tuple[str, str, str], dict] = {}
    for edge in graph["edges"]:
        src, dst = membership[edge["source"]], membership[edge["target"]]
        if src == dst:
            continue
        link = links.setdefault(
            (src, dst, edge["kind"]),
            {"source": src, "target": dst, "kind": edge["kind"], "count": 0, "evidence": []},
        )
        link["count"] += edge["count"]
        link["evidence"].extend(
            {**e, "source_file": edge["source"], "target_file": edge["target"]}
            for e in edge["evidence"][:10]
        )
    degree: dict[str, int] = defaultdict(int)
    for edge in links.values():
        degree[edge["source"]] += edge["count"]
        degree[edge["target"]] += edge["count"]
    keep = set(sorted(modules, key=lambda p: (-degree[p], p))[:limit])
    return {
        "nodes": [modules[p] for p in sorted(keep)],
        "edges": [
            {**e, "evidence": e["evidence"][:100]}
            for e in links.values()
            if e["source"] in keep and e["target"] in keep
        ],
        "total_nodes": len(modules),
        "shown_nodes": len(keep),
        "truncated": len(modules) > len(keep),
        "analysis_files": graph["analysis_files"],
        "indexed_files": graph["indexed_files"],
        "note": "Modules are grouped by source directory, not inferred deployment services. "
        "Role labels are path hints; each arrow has source evidence. " + graph["note"],
    }


def explain_file(conn: sqlite3.Connection, path: str) -> dict:
    file = conn.execute("SELECT * FROM files WHERE rel_path=?", (path,)).fetchone()
    if file is None:
        raise ValueError("No indexed file")
    facts = _load_facts(conn, file["id"]).get(file["id"])
    imports = [
        dict(r)
        for r in conn.execute(
            "SELECT symbol_name, source_path, line, resolved_file_id FROM imports WHERE file_id=?",
            (file["id"],),
        )
    ]
    symbols = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM symbols WHERE file_id=? ORDER BY line_start", (file["id"],)
        )
    ]
    role = describe_module(path.split("/")[-2] if "/" in path else "(root)")
    functions = facts["functions"] if facts else []
    targets = _resolve_calls(conn, {file["id"]: facts}) if facts else {}
    paths = {r["id"]: r["rel_path"] for r in conn.execute("SELECT id, rel_path FROM files")}
    enriched = []
    collaborators = set()
    for function in functions:
        calls = []
        for call in function["calls"]:
            target = targets.get((file["id"], function["line"], call["key"]))
            declaration = None
            if target:
                declaration = {
                    "path": paths[target["file_id"]],
                    "line": target["line_start"],
                    "name": target["name"],
                    "signature": target["signature"],
                }
                if declaration["path"] != path:
                    collaborators.add((declaration["path"], target["name"], target["line_start"]))
            calls.append({**call, "target": declaration})
        enriched.append({**function, "calls": calls})
    internal_imports = sum(1 for i in imports if i["resolved_file_id"] is not None)
    return {
        "path": path,
        "role_hint": role,
        "role_basis": "Directory-name heuristic, not a semantic guarantee.",
        "summary": f"{file['language']} source with {len(symbols)} declarations and "
        f"{len(functions)} callable implementation outlines. "
        f"{internal_imports} imports resolve inside this project.",
        "functions": enriched,
        "collaborators": [
            {"path": p, "name": name, "line": line} for p, name, line in sorted(collaborators)
        ],
        "documentation": facts.get("documentation") if facts else None,
        "declarations": symbols,
        "imports": [{k: v for k, v in i.items() if k != "resolved_file_id"} for i in imports],
        "analysis_available": facts is not None,
        "parse_has_errors": facts["parse_has_errors"] if facts else None,
        "note": facts["scope"]
        if facts
        else "Re-index this project to generate implementation facts.",
    }
