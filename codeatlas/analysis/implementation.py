"""Source-grounded implementation facts and straight-line data provenance.

Runs at index time. No model, network, source-body storage or runtime claims.
"""

import re
from typing import Any

from codeatlas.indexer.py_parser import _parser as python_parser
from codeatlas.indexer.ts_parser import _parse as typescript_parser

FUNCTIONS = {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "arrow_function",
    "method_definition",
}
CALLS = {"call", "call_expression"}
CONTROL = {
    "if_statement": "branch",
    "for_statement": "loop",
    "for_in_statement": "loop",
    "while_statement": "loop",
    "try_statement": "error handling",
    "raise_statement": "raises",
    "throw_statement": "throws",
    "await": "await",
    "await_expression": "await",
    "return_statement": "return",
    "yield": "yield",
    "yield_expression": "yield",
    "with_statement": "resource scope",
    "switch_statement": "branch",
    "match_statement": "branch",
}


def _walk(node, stop_nested=False):
    yield node
    for child in node.named_children:
        if stop_nested and child.type in FUNCTIONS | {
            "class_definition",
            "class_declaration",
            "lambda",
        }:
            continue
        yield from _walk(child, stop_nested)


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace") if node else ""


def _safe_expr(node, source: bytes) -> str:
    """Show expression structure while removing literal strings/templates."""
    if node is None:
        return ""
    fragments = []
    cursor = node.start_byte
    for part in _walk(node):
        if part.type not in {"string", "string_literal", "template_string", "concatenated_string"}:
            continue
        if part.start_byte < cursor:
            continue
        fragments.append(source[cursor : part.start_byte].decode("utf-8", errors="replace"))
        fragments.append('"…"')
        cursor = part.end_byte
    fragments.append(source[cursor : node.end_byte].decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", "".join(fragments))[:180]


def _name(node, source: bytes) -> str:
    name = node.child_by_field_name("name")
    if name:
        return _text(name, source)
    if node.type == "arrow_function" and node.parent:
        return _text(node.parent.child_by_field_name("name"), source)
    return ""


def _unwrap(node):
    while (
        node is not None
        and node.type
        in {
            "await",
            "await_expression",
            "parenthesized_expression",
            "expression_statement",
        }
        and len(node.named_children) == 1
    ):
        node = node.named_children[0]
    return node


def extract_implementation(source: bytes, language: str, symbols: list[dict]) -> dict:
    parser = python_parser() if language == "python" else typescript_parser()
    root = parser.parse(source).root_node
    definitions = {
        (n.start_point[0] + 1, _name(n, source)): n for n in _walk(root) if n.type in FUNCTIONS
    }
    facts = []
    for symbol in symbols:
        node = definitions.get((symbol["line_start"], symbol["name"]))
        if node is None:
            node = next(
                (
                    n
                    for (line, name), n in definitions.items()
                    if name == symbol["name"]
                    and symbol["line_start"] <= line <= (symbol["line_end"] or symbol["line_start"])
                ),
                None,
            )
        if node is None:
            continue
        body = node.child_by_field_name("body")
        params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
        parameters = _safe_expr(params, source)
        all_nodes = list(_walk(body or node, True))
        # Imports can be shadowed anywhere in the callable. Prefer an unresolved
        # target over selecting a different function with the same spelling.
        bindings: set[str] = set()
        if params:
            bindings.update(_text(n, source) for n in _walk(params) if n.type == "identifier")
        for n in _walk(body or node):
            if n != node and n.type in FUNCTIONS | {"class_definition", "class_declaration"}:
                name = _name(n, source)
                if name:
                    bindings.add(name)
        for n in all_nodes:
            if n.type in {
                "import_statement",
                "import_from_statement",
                "global_statement",
                "nonlocal_statement",
            }:
                bindings.update(_text(p, source) for p in _walk(n) if p.type == "identifier")
            if n.type in {
                "assignment",
                "augmented_assignment",
                "variable_declarator",
                "assignment_expression",
                "for_statement",
                "for_in_statement",
            }:
                left = n.child_by_field_name("left") or n.child_by_field_name("name")
                if left:
                    bindings.update(_text(p, source) for p in _walk(left) if p.type == "identifier")
        calls: list[dict[str, Any]] = []
        by_key = {}
        for n in all_nodes:
            if n.type not in CALLS:
                continue
            fn = n.child_by_field_name("function")
            ref = _text(fn, source)
            args_node = n.child_by_field_name("arguments")
            args = list(args_node.named_children) if args_node else []
            key = f"{n.start_point[0] + 1}:{n.start_point[1]}"
            call = {
                "key": key,
                "ref": ref[:180],
                "line": n.start_point[0] + 1,
                "arguments": [_safe_expr(a, source) for a in args],
                "shadowed": ref.split(".")[0] in bindings,
                "result_used": False,
                "result_name": None,
                "handoffs": [],
            }
            parent = n.parent
            while parent and parent.type in {
                "await",
                "await_expression",
                "parenthesized_expression",
            }:
                parent = parent.parent
            call["result_used"] = bool(
                parent
                and parent.type
                in {
                    "assignment",
                    "variable_declarator",
                    "return_statement",
                    "argument_list",
                    "arguments",
                }
            )
            calls.append(call)
            by_key[key] = call

        def nested_blocks(n):
            for child in n.named_children:
                if child.type in FUNCTIONS | {"class_definition", "class_declaration"}:
                    continue
                if child.type in {"block", "statement_block"}:
                    yield child
                else:
                    yield from nested_blocks(child)

        def process_statements(statements, by_key=by_key):
            provenance: dict[str, str] = {}
            for statement in statements:
                simple = _unwrap(statement)
                if simple is None:
                    continue
                if simple.type in {"lexical_declaration", "variable_declaration"}:
                    units = simple.named_children
                elif (
                    simple.type
                    in {
                        "assignment",
                        "augmented_assignment",
                        "variable_declarator",
                        "return_statement",
                    }
                    | CALLS
                ):
                    units = [simple]
                else:
                    # Branch joins, loops, try, closures and mutation need a CFG.
                    # Do not carry straight-line provenance across them.
                    provenance.clear()
                    for nested in nested_blocks(simple):
                        process_statements(nested.named_children)
                    continue
                for unit in units:
                    for n in _walk(unit, True):
                        if n.type not in CALLS:
                            continue
                        key = f"{n.start_point[0] + 1}:{n.start_point[1]}"
                        current_call = by_key.get(key)
                        if not current_call:
                            continue
                        arguments = n.child_by_field_name("arguments")
                        for i, arg in enumerate(arguments.named_children if arguments else []):
                            value = _unwrap(arg)
                            provider = None
                            variable = None
                            if value is not None and value.type == "identifier":
                                variable = _text(value, source)
                                provider = provenance.get(variable)
                            elif value is not None and value.type in CALLS:
                                provider = f"{value.start_point[0] + 1}:{value.start_point[1]}"
                            if provider:
                                current_call["handoffs"].append(
                                    {
                                        "provider": provider,
                                        "variable": variable,
                                        "argument_index": i,
                                        "line": current_call["line"],
                                    }
                                )
                    left = unit.child_by_field_name("left") or unit.child_by_field_name("name")
                    right = _unwrap(
                        unit.child_by_field_name("right") or unit.child_by_field_name("value")
                    )
                    if left and left.type == "identifier":
                        variable = _text(left, source)
                        origin = None
                        if right is not None and right.type in CALLS:
                            origin = f"{right.start_point[0] + 1}:{right.start_point[1]}"
                            if origin in by_key:
                                by_key[origin]["result_name"] = variable
                        elif right is not None and right.type == "identifier":
                            origin = provenance.get(_text(right, source))
                        provenance.pop(variable, None)
                        if origin and unit.type != "augmented_assignment":
                            provenance[variable] = origin
                    elif left:
                        provenance.clear()

        statements = (
            body.named_children if body and body.type in {"block", "statement_block"} else []
        )
        process_statements(statements)
        docs = None
        if language == "python" and body and body.named_children:
            first = body.named_children[0]
            if (
                first.type == "expression_statement"
                and first.named_children
                and first.named_children[0].type == "string"
            ):
                docs = _text(first.named_children[0], source).strip("\"'")[:800]
        elif node.prev_named_sibling and node.prev_named_sibling.type == "comment":
            docs = _text(node.prev_named_sibling, source)[:800]
        steps = []
        for n in all_nodes:
            if n.type in CONTROL:
                steps.append(
                    {
                        "kind": CONTROL[n.type],
                        "line": n.start_point[0] + 1,
                        "detail": _safe_expr(n.child_by_field_name("condition"), source)
                        if CONTROL[n.type] == "branch"
                        else (
                            _safe_expr(n.named_children[0], source)
                            if n.type == "return_statement" and n.named_children
                            else ""
                        ),
                    }
                )
        facts.append(
            {
                "name": symbol["name"],
                "line": symbol["line_start"],
                "end_line": symbol["line_end"],
                "parent": symbol.get("parent_symbol"),
                "signature": symbol.get("signature"),
                "parameters": parameters,
                "documentation": docs,
                "steps": steps,
                "calls": calls,
            }
        )
    module_documentation = None
    if root.named_children:
        first = root.named_children[0]
        if language == "python" and first.type == "expression_statement" and first.named_children:
            if first.named_children[0].type == "string":
                module_documentation = _text(first.named_children[0], source).strip("\"'")[:1500]
        elif first.type == "comment":
            module_documentation = _text(first, source)[:1500]
    return {
        "version": 1,
        "parse_has_errors": root.has_error,
        "functions": facts,
        "documentation": module_documentation,
        "scope": "AST facts; handoffs cover straight-line assignments/direct nested calls. "
        "Branch joins, mutations, closures and runtime dispatch are not inferred.",
    }
