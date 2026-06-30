"""
TypeScript/TSX parser using tree-sitter.

Extracts: function, class, interface, type alias, enum, const/let/var
declarations, plus imports, call expressions, and parent_symbol relationships.
"""

import os
from tree_sitter_languages import get_parser


# Kinds of declarations we care about — maps tree-sitter node type → our kind label
DECLARATION_KINDS: dict[str, str] = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "arrow_function": "arrow_function",
    "method_definition": "method",
    "class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type_alias",
    "enum_declaration": "enum",
    "variable_declarator": "variable",
}

# Kinds where the name is stored in a `name` field child
SIMPLE_NAME_BINDINGS: set[str] = {
    "function_declaration", "generator_function_declaration",
    "class_declaration", "interface_declaration",
    "type_alias_declaration", "enum_declaration",
}

# Kinds that have a body we can scan for call expressions
CALLABLE_KINDS: set[str] = {
    "function_declaration", "generator_function_declaration",
    "arrow_function", "method_definition",
}

# Ancestor node types that indicate a symbol is exported
EXPORT_CONTEXT_KINDS: set[str] = {"export_statement", "export_clause", "export_specifier"}


def _parse():
    """Lazy-init the TSX parser (singleton-friendly)."""
    return get_parser("tsx")


def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _child_text_by_field(node, field_name: str, source_bytes: bytes) -> str | None:
    child = node.child_by_field_name(field_name)
    return _node_text(child, source_bytes) if child else None


def _has_ancestor_kind(node, kinds: set[str]) -> bool:
    current = node.parent
    while current:
        if current.type in kinds:
            return True
        current = current.parent
    return False


def _node_has_child_type(node, child_type: str) -> bool:
    """Check if any direct child has the given type."""
    for child in node.children:
        if child.type == child_type:
            return True
    return False


def _extract_signature(node, source_bytes: bytes) -> str | None:
    """Extract a human-readable function signature."""
    name = _child_text_by_field(node, "name", source_bytes) or "anonymous"
    params_node = node.child_by_field_name("parameters")
    params_text = _node_text(params_node, source_bytes) if params_node else "()"
    return_type = _child_text_by_field(node, "return_type", source_bytes)
    if return_type:
        return f"{name}{params_text}: {return_type}"
    return f"{name}{params_text}"


def _collect_call_expressions(node, source_bytes: bytes, calls_out: list[dict]):
    """Recursively walk a node subtree collecting call_expression nodes."""
    if node.type == "call_expression":
        func_node = node.child_by_field_name("function")
        if func_node:
            if func_node.type == "identifier":
                calls_out.append({
                    "name": _node_text(func_node, source_bytes),
                    "is_member": False,
                    "line": node.start_point[0] + 1,
                })
            elif func_node.type == "member_expression":
                obj = func_node.child_by_field_name("object")
                prop = func_node.child_by_field_name("property")
                if obj and prop:
                    calls_out.append({
                        "name": _node_text(prop, source_bytes),
                        "is_member": True,
                        "object": _node_text(obj, source_bytes) if obj.type == "identifier" else None,
                        "line": node.start_point[0] + 1,
                    })
    for child in node.children:
        _collect_call_expressions(child, source_bytes, calls_out)


def parse_file(file_path: str, aliases: dict[str, str] | None = None) -> dict:
    """
    Parse a single TypeScript/TSX file and return a dict with
    symbols, imports, and call edges.

    Returns:
        {
            "path": str,
            "language": "typescript" | "typescriptreact",
            "lines": int,
            "bytes": int,
            "symbols": [{name, kind, line_start, line_end, signature,
                          is_export, is_default_export, is_async,
                          parent_symbol, enclosing_type}],
            "imports": [{symbol_name, alias_name, source_path, import_type,
                         line, is_type_import}],
            "call_edges": [{callee_name, caller_symbol_name, is_member, line}],
        }
    """
    aliases = aliases or {}
    ext = os.path.splitext(file_path)[1]
    language = "typescriptreact" if ext == ".tsx" else "typescript"

    with open(file_path, "rb") as f:
        source_bytes = f.read()

    lines_count = source_bytes.count(b"\n")
    byte_count = len(source_bytes)

    parser = _parse()
    tree = parser.parse(source_bytes)
    root = tree.root_node

    symbols: list[dict] = []
    imports: list[dict] = []
    call_edges: list[dict] = []

    # Track the enclosing scope stack for parent_symbol
    # Stack of (symbol_name, enclosing_type) tuples
    scope_stack: list[tuple[str, str]] = []

    def walk(node):
        nonlocal scope_stack

        # ── ENCLOSING SCOPE TRACKING ──
        # Push scope when entering a class or named function
        pushed = False
        scope_name = None
        scope_type = None

        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                scope_name = _node_text(name_node, source_bytes)
                scope_type = "class"
        elif node.type in ("function_declaration", "method_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                scope_name = _node_text(name_node, source_bytes)
                scope_type = "function"

        if scope_name:
            scope_stack.append((scope_name, scope_type))
            pushed = True

        # ── SYMBOL EXTRACTION ──
        kind = DECLARATION_KINDS.get(node.type)
        name = None

        if kind is not None:
            if node.type in SIMPLE_NAME_BINDINGS:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node, source_bytes)
            elif node.type == "variable_declarator":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node, source_bytes)
                value_node = node.child_by_field_name("value")
                if value_node and value_node.type == "arrow_function":
                    kind = "arrow_function"
            elif node.type == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node, source_bytes)
            elif node.type == "arrow_function":
                # Handled under variable_declarator above
                for child in node.children:
                    walk(child)
                if pushed:
                    scope_stack.pop()
                return

            if name and kind:
                # Export status
                is_export = _has_ancestor_kind(node, EXPORT_CONTEXT_KINDS)
                if not is_export and node.parent:
                    is_export = _node_has_child_type(node.parent, "export")

                # Default export
                is_default = False
                parent = node.parent
                if parent:
                    for child in parent.children:
                        if child.type == "default":
                            is_default = True
                            break

                # Async
                is_async = False
                if node.type in CALLABLE_KINDS:
                    is_async = _node_has_child_type(node, "async")
                elif kind == "arrow_function" and parent:
                    is_async = _node_has_child_type(parent, "async")

                # Signature
                signature = None
                if node.type in CALLABLE_KINDS:
                    signature = _extract_signature(node, source_bytes)
                elif kind == "arrow_function":
                    actual_node = node
                    if node.type == "variable_declarator":
                        value_node = node.child_by_field_name("value")
                        if value_node and value_node.type == "arrow_function":
                            actual_node = value_node
                    params_node = actual_node.child_by_field_name("parameters")
                    params_text = _node_text(params_node, source_bytes) if params_node else "()"
                    ret = _child_text_by_field(actual_node, "return_type", source_bytes)
                    signature = f"{name}{params_text}: {ret}" if ret else f"{name}{params_text}"
                elif node.type == "class_declaration":
                    heritage = ""
                    for child in node.children:
                        if child.type in ("extends_clause", "implements_clause"):
                            heritage += " " + _node_text(child, source_bytes)
                    signature = f"class {name}{heritage}"
                elif node.type == "interface_declaration":
                    heritage = ""
                    for child in node.children:
                        if child.type == "extends_clause":
                            heritage += " " + _node_text(child, source_bytes)
                    signature = f"interface {name}{heritage}"

                # Parent symbol
                parent_symbol = scope_stack[-1][0] if scope_stack else None
                enclosing_type = scope_stack[-1][1] if scope_stack else None

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "line_start": node.start_point[0] + 1,
                    "line_end": node.end_point[0] + 1,
                    "signature": signature,
                    "is_export": is_export,
                    "is_default_export": is_default,
                    "is_async": is_async,
                    "parent_symbol": parent_symbol,
                    "enclosing_type": enclosing_type,
                })

            # ── CALL EDGE COLLECTION ──
            if node.type in CALLABLE_KINDS:
                body_node = node.child_by_field_name("body")
                if body_node:
                    body_calls: list[dict] = []
                    _collect_call_expressions(body_node, source_bytes, body_calls)
                    caller_name = _child_text_by_field(node, "name", source_bytes)
                    for call in body_calls:
                        call["caller_symbol_name"] = caller_name
                    call_edges.extend(body_calls)
            elif node.type == "arrow_function":
                body_node = node.child_by_field_name("body")
                if body_node:
                    body_calls: list[dict] = []
                    _collect_call_expressions(body_node, source_bytes, body_calls)
                    caller_name = "anonymous"
                    if node.parent and node.parent.type == "variable_declarator":
                        caller_name = _child_text_by_field(node.parent, "name", source_bytes) or "anonymous"
                    elif node.parent and node.parent.type == "assignment_expression":
                        left = node.parent.child_by_field_name("left")
                        if left:
                            caller_name = _node_text(left, source_bytes)
                    for call in body_calls:
                        call["caller_symbol_name"] = caller_name
                    call_edges.extend(body_calls)

        # ── IMPORT COLLECTION ──
        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            source_text = ""
            if source_node:
                source_text = _node_text(source_node, source_bytes).strip('"').strip("'")

            line = node.start_point[0] + 1

            # Check for `import type ...` pattern
            is_type = _node_has_child_type(node, "type")

            # Find import_clause among children (tree-sitter doesn't give it a field name)
            clause_node = None
            for child in node.children:
                if child.type == "import_clause":
                    clause_node = child
                    break

            if clause_node is None:
                # Side-effect import
                imports.append({
                    "symbol_name": "",
                    "alias_name": None,
                    "source_path": source_text,
                    "import_type": "side_effect",
                    "line": line,
                    "is_type_import": is_type,
                })
            else:
                for child in clause_node.children:
                    if child.type == "identifier":
                        imports.append({
                            "symbol_name": _node_text(child, source_bytes),
                            "alias_name": None,
                            "source_path": source_text,
                            "import_type": "default",
                            "line": line,
                            "is_type_import": is_type,
                        })
                    elif child.type == "named_imports":
                        for spec in child.children:
                            if spec.type == "import_specifier":
                                sn = spec.child_by_field_name("name")
                                sa = spec.child_by_field_name("alias")
                                if sn:
                                    imports.append({
                                        "symbol_name": _node_text(sn, source_bytes),
                                        "alias_name": _node_text(sa, source_bytes) if sa else None,
                                        "source_path": source_text,
                                        "import_type": "named",
                                        "line": line,
                                        "is_type_import": is_type,
                                    })
                    elif child.type == "namespace_import":
                        ns = child.child_by_field_name("name")
                        if ns:
                            imports.append({
                                "symbol_name": _node_text(ns, source_bytes),
                                "alias_name": None,
                                "source_path": source_text,
                                "import_type": "namespace",
                                "line": line,
                                "is_type_import": is_type,
                            })

        # Recurse
        for child in node.children:
            walk(child)

        # Pop scope after processing children
        if pushed:
            scope_stack.pop()

    walk(root)

    return {
        "path": file_path,
        "language": language,
        "lines": lines_count,
        "bytes": byte_count,
        "symbols": symbols,
        "imports": imports,
        "call_edges": call_edges,
    }
