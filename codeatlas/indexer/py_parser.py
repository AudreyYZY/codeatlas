"""
Python parser using tree-sitter.

Extracts functions, classes, methods, module-level assignments, imports
(``import x``, ``from .x import y``) and best-effort call edges — the same
shape the TypeScript parser produces, so the indexer and every query works
across both languages unchanged.
"""

from functools import lru_cache

from tree_sitter_language_pack import get_parser

from codeatlas.config import detect_language


@lru_cache(maxsize=1)
def _parser():
    return get_parser("python")


def _text(node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _field_text(node, field: str, src: bytes) -> str | None:
    child = node.child_by_field_name(field)
    return _text(child, src) if child else None


def _is_async(node, src: bytes) -> bool:
    return any(c.type == "async" for c in node.children)


def _signature(node, src: bytes) -> str:
    name = _field_text(node, "name", src) or "anonymous"
    params = _field_text(node, "parameters", src) or "()"
    ret = _field_text(node, "return_type", src)
    prefix = "async def " if _is_async(node, src) else "def "
    return f"{prefix}{name}{params} -> {ret}" if ret else f"{prefix}{name}{params}"


def _collect_calls(node, src: bytes, out: list[dict], stop_types: set[str]) -> None:
    """Collect call expressions under ``node``, not descending into nested defs."""
    for child in node.children:
        if child.type in stop_types:
            continue
        if child.type == "call":
            func = child.child_by_field_name("function")
            if func is not None:
                if func.type == "identifier":
                    out.append(
                        {
                            "name": _text(func, src),
                            "is_member": False,
                            "line": child.start_point[0] + 1,
                        }
                    )
                elif func.type == "attribute":
                    attr = func.child_by_field_name("attribute")
                    obj = func.child_by_field_name("object")
                    if attr is not None:
                        out.append(
                            {
                                "name": _text(attr, src),
                                "is_member": True,
                                "object": _text(obj, src)
                                if obj is not None and obj.type == "identifier"
                                else None,
                                "line": child.start_point[0] + 1,
                            }
                        )
        _collect_calls(child, src, out, stop_types)


def _dotted_name(node, src: bytes) -> str:
    return _text(node, src).strip()


def parse_py_file(file_path: str, aliases: dict[str, str] | None = None) -> dict:
    """Parse one Python file. Returns the same dict shape as the TS parser."""
    with open(file_path, "rb") as f:
        source = f.read()

    tree = _parser().parse(source)
    root = tree.root_node

    symbols: list[dict] = []
    imports: list[dict] = []
    call_edges: list[dict] = []

    nested_def_types = {"function_definition", "class_definition"}

    def walk(node, scope: list[tuple[str, str]]) -> None:
        node_type = node.type

        if node_type in ("function_definition", "class_definition"):
            name = _field_text(node, "name", source)
            if name:
                is_class = node_type == "class_definition"
                parent_name = scope[-1][0] if scope else None
                parent_kind = scope[-1][1] if scope else None
                if is_class:
                    kind = "class"
                    bases = _field_text(node, "superclasses", source) or ""
                    signature = f"class {name}{bases}"
                else:
                    kind = "method" if parent_kind == "class" else "function"
                    signature = _signature(node, source)

                symbols.append(
                    {
                        "name": name,
                        "kind": kind,
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "signature": signature,
                        # Python has no `export`; a leading underscore is the
                        # convention for "private", everything else is public.
                        "is_export": not name.startswith("_"),
                        "is_default_export": False,
                        "is_async": not is_class and _is_async(node, source),
                        "parent_symbol": parent_name,
                        "enclosing_type": parent_kind,
                    }
                )

                if not is_class:
                    body = node.child_by_field_name("body")
                    if body is not None:
                        calls: list[dict] = []
                        _collect_calls(body, source, calls, nested_def_types)
                        for call in calls:
                            call["caller_symbol_name"] = name
                        call_edges.extend(calls)

                inner_scope = scope + [(name, "class" if is_class else "function")]
                for child in node.children:
                    walk(child, inner_scope)
                return

        # Module- or class-level assignments become "variable" symbols.
        if node_type == "assignment" and node.parent is not None:
            # Grammar versions differ on whether an `expression_statement`
            # wrapper exists, so accept both shapes.
            holder = node.parent
            if holder.type == "expression_statement" and holder.parent is not None:
                holder = holder.parent
            # Module-level constants and class attributes are declarations;
            # locals inside a function body are not, so a function scope
            # disqualifies the assignment.
            in_function = bool(scope) and scope[-1][1] == "function"
            at_declaration_level = holder.type in ("module", "block") and not in_function
            left = node.child_by_field_name("left")
            if at_declaration_level and left is not None and left.type == "identifier":
                name = _text(left, source)
                symbols.append(
                    {
                        "name": name,
                        "kind": "variable",
                        "line_start": node.start_point[0] + 1,
                        "line_end": node.end_point[0] + 1,
                        "signature": None,
                        "is_export": not name.startswith("_"),
                        "is_default_export": False,
                        "is_async": False,
                        "parent_symbol": scope[-1][0] if scope else None,
                        "enclosing_type": scope[-1][1] if scope else None,
                    }
                )

        # ── import x.y as z ──
        if node_type == "import_statement":
            line = node.start_point[0] + 1
            for child in node.children:
                if child.type == "dotted_name":
                    module = _dotted_name(child, source)
                    imports.append(
                        {
                            "symbol_name": module.split(".")[-1],
                            "alias_name": None,
                            "source_path": module,
                            "import_type": "module",
                            "line": line,
                            "is_type_import": False,
                            "level": 0,
                        }
                    )
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    alias_node = child.child_by_field_name("alias")
                    if name_node is not None:
                        module = _dotted_name(name_node, source)
                        imports.append(
                            {
                                "symbol_name": module.split(".")[-1],
                                "alias_name": _text(alias_node, source) if alias_node else None,
                                "source_path": module,
                                "import_type": "module",
                                "line": line,
                                "is_type_import": False,
                                "level": 0,
                            }
                        )

        # ── from .x import a as b ──
        if node_type == "import_from_statement":
            line = node.start_point[0] + 1
            module_node = node.child_by_field_name("module_name")
            module = ""
            level = 0
            if module_node is not None:
                raw = _dotted_name(module_node, source)
                level = len(raw) - len(raw.lstrip("."))
                module = raw.lstrip(".")
            else:
                # `from . import x` — dots appear as bare children
                level = sum(1 for c in node.children if c.type in (".", "import_prefix"))

            names: list[tuple[str, str | None]] = []
            wildcard = False
            # NB: tree-sitter returns fresh Node wrappers on every access, so
            # identity comparison against module_node is unreliable — compare
            # byte offsets instead.
            module_start = module_node.start_byte if module_node is not None else -1
            for child in node.children:
                if child.start_byte == module_start:
                    continue
                if child.type == "wildcard_import":
                    wildcard = True
                elif child.type == "dotted_name":
                    names.append((_dotted_name(child, source), None))
                elif child.type == "aliased_import":
                    n = child.child_by_field_name("name")
                    a = child.child_by_field_name("alias")
                    if n is not None:
                        names.append((_dotted_name(n, source), _text(a, source) if a else None))

            if wildcard or not names:
                names = [("*", None)]

            for symbol_name, alias in names:
                imports.append(
                    {
                        "symbol_name": symbol_name,
                        "alias_name": alias,
                        "source_path": ("." * level) + module,
                        "import_type": "named",
                        "line": line,
                        "is_type_import": False,
                        "level": level,
                        "module": module,
                    }
                )

        for child in node.children:
            walk(child, scope)

    walk(root, [])

    # Top-level calls (module body, outside any def) are attributed to the module.
    return {
        "path": file_path,
        "language": detect_language(file_path),
        "lines": source.count(b"\n"),
        "bytes": len(source),
        "symbols": symbols,
        "imports": imports,
        "call_edges": call_edges,
    }
