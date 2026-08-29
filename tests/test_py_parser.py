"""Tests for the Python parser."""

import os
import tempfile

from codeatlas.indexer.parser import UnsupportedLanguageError, parse_file

SOURCE = """
import os
import os.path as osp
from . import sibling
from .relative import thing as aliased
from ..pkg.mod import A, B

CONST = 42
_private = 1

class Base:
    attr = 1

    def method(self, x: int) -> str:
        local = 1
        return helper(x)

    async def amethod(self):
        return await self.method(1)

async def top(a, b=2) -> None:
    def inner():
        return os.path.join("a")
    return inner()
"""


def _parse(source: str, suffix: str = ".py") -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "sample" + suffix)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        return parse_file(path)


def test_language_detection():
    assert _parse("x = 1")["language"] == "python"


def test_functions_and_classes():
    result = _parse(SOURCE)
    by_name = {s["name"]: s for s in result["symbols"]}
    assert by_name["Base"]["kind"] == "class"
    assert by_name["method"]["kind"] == "method"
    assert by_name["method"]["parent_symbol"] == "Base"
    assert by_name["top"]["kind"] == "function"
    assert by_name["top"]["is_async"] is True
    assert by_name["inner"]["parent_symbol"] == "top"


def test_module_constants_but_not_locals():
    names = {s["name"] for s in _parse(SOURCE)["symbols"] if s["kind"] == "variable"}
    assert {"CONST", "_private", "attr"} <= names
    assert "local" not in names, "function-local assignments are not declarations"


def test_underscore_names_are_not_exported():
    by_name = {s["name"]: s for s in _parse(SOURCE)["symbols"]}
    assert by_name["CONST"]["is_export"] is True
    assert by_name["_private"]["is_export"] is False


def test_signatures():
    by_name = {s["name"]: s for s in _parse(SOURCE)["symbols"]}
    assert by_name["method"]["signature"] == "def method(self, x: int) -> str"
    assert by_name["amethod"]["signature"].startswith("async def")


def test_imports():
    imports = _parse(SOURCE)["imports"]
    plain = {(i["source_path"], i["symbol_name"], i["alias_name"], i["level"]) for i in imports}
    assert ("os", "os", None, 0) in plain
    assert ("os.path", "path", "osp", 0) in plain
    assert (".", "sibling", None, 1) in plain
    assert (".relative", "thing", "aliased", 1) in plain
    assert ("..pkg.mod", "A", None, 2) in plain


def test_call_edges_attributed_to_enclosing_function():
    calls = {(c["caller_symbol_name"], c["name"]) for c in _parse(SOURCE)["call_edges"]}
    assert ("method", "helper") in calls
    assert ("inner", "join") in calls
    assert ("top", "inner") in calls


def test_unsupported_extension_raises():
    import pytest

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "notes.md")
        open(path, "w").close()
        with pytest.raises(UnsupportedLanguageError):
            parse_file(path)
