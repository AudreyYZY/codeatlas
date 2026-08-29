"""
Language-dispatching parser front end.

``parse_file`` is the single entry point the indexer uses. It picks a
language-specific parser by file extension and normalises the result, so every
parser returns the same dict shape:

    {
        "path": str,
        "language": str,
        "lines": int,
        "bytes": int,
        "symbols":    [{name, kind, line_start, line_end, signature,
                        is_export, is_default_export, is_async,
                        parent_symbol, enclosing_type}],
        "imports":    [{symbol_name, alias_name, source_path, import_type,
                        line, is_type_import, level}],
        "call_edges": [{name, caller_symbol_name, is_member, line}],
    }
"""

import os

from codeatlas.config import PY_EXTENSIONS, TS_EXTENSIONS
from codeatlas.indexer.py_parser import parse_py_file
from codeatlas.indexer.ts_parser import parse_ts_file


class UnsupportedLanguageError(ValueError):
    """Raised when no parser is registered for a file extension."""


def parse_file(file_path: str, aliases: dict[str, str] | None = None) -> dict:
    """Parse one source file into symbols, imports and call edges."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in PY_EXTENSIONS:
        result = parse_py_file(file_path, aliases)
    elif ext in TS_EXTENSIONS:
        result = parse_ts_file(file_path, aliases)
    else:
        raise UnsupportedLanguageError(f"No parser for '{ext}' ({file_path})")

    # Normalise optional fields so downstream code never needs .get()
    for imp in result["imports"]:
        imp.setdefault("level", 0)
        imp.setdefault("is_type_import", False)
        imp.setdefault("alias_name", None)
    return result


__all__ = ["UnsupportedLanguageError", "parse_file", "parse_py_file", "parse_ts_file"]
