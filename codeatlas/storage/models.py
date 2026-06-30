"""Dataclass models for codeatlas entities."""

from dataclasses import dataclass


@dataclass
class File:
    """A source file in the project."""

    id: int | None = None
    path: str = ""
    rel_path: str = ""
    language: str = "typescript"
    lines: int = 0
    bytes: int = 0
    indexed_at: str = ""


@dataclass
class Symbol:
    """A code symbol (function, class, interface, variable, etc.)."""

    id: int | None = None
    file_id: int = 0
    name: str = ""
    kind: str = ""
    line_start: int = 0
    line_end: int = 0
    signature: str | None = None
    is_export: bool = False
    is_default_export: bool = False
    is_async: bool = False
    parent_symbol: str | None = None
    enclosing_type: str | None = None  # "class" | "function" | "module"


@dataclass
class Import:
    """An import statement."""

    id: int | None = None
    file_id: int = 0
    symbol_name: str = ""
    alias_name: str | None = None
    source_path: str = ""
    import_type: str = "named"  # named | default | namespace | side_effect
    line: int = 0
    resolved_path: str | None = None
    resolved_file_id: int | None = None
    is_type_import: bool = False


@dataclass
class CallEdge:
    """A function call from one symbol to another (best-effort)."""

    id: int | None = None
    caller_file_id: int = 0
    caller_symbol_id: int | None = None
    callee_name: str = ""
    callee_symbol_id: int | None = None
    callee_file_id: int | None = None
    resolved: bool = False


@dataclass
class DepEdge:
    """A file-level dependency edge."""

    id: int | None = None
    source_file_id: int = 0
    target_file_id: int | None = None  # NULL if external
    resolved: bool = False
