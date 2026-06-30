"""Tests for the tree-sitter TypeScript/TSX parser."""

import os
import tempfile

import pytest

from codeatlas.indexer.parser import parse_file

SIMPLE_TS = b"""
import React, { useState } from 'react';
import type { GeographicFeature } from '@/features/types';

export interface CameraParams {
  target: [number, number];
}

export function computeCamera(ridge: string): CameraParams {
  const result = helper(ridge);
  return result;
}

function helper(input: string): CameraParams {
  return { target: [0, 0] };
}

export default class CameraManager {
  flyTo(params: CameraParams): void {
    this.active = params;
  }
}
"""


@pytest.fixture
def ts_file():
    """Create a temp .ts file with known content."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".ts", delete=False) as f:
        f.write(SIMPLE_TS)
        path = f.name
    yield path
    os.unlink(path)


def test_parse_functions(ts_file):
    result = parse_file(ts_file)
    func_names = {s["name"] for s in result["symbols"] if s["kind"] == "function"}
    assert "computeCamera" in func_names
    assert "helper" in func_names


def test_parse_classes(ts_file):
    result = parse_file(ts_file)
    classes = [s for s in result["symbols"] if s["kind"] == "class"]
    assert len(classes) == 1
    assert classes[0]["name"] == "CameraManager"
    assert classes[0]["is_default_export"] is True


def test_parse_interfaces(ts_file):
    result = parse_file(ts_file)
    interfaces = [s for s in result["symbols"] if s["kind"] == "interface"]
    assert len(interfaces) == 1
    assert interfaces[0]["name"] == "CameraParams"
    assert interfaces[0]["is_export"] is True


def test_parse_imports(ts_file):
    result = parse_file(ts_file)
    imports = result["imports"]
    assert len(imports) >= 3
    sources = {imp["source_path"] for imp in imports}
    assert "react" in sources
    assert "@/features/types" in sources
    # Check named import
    named = [imp for imp in imports if imp["import_type"] == "named"]
    assert any(imp["symbol_name"] == "useState" for imp in named)
    # Check default import
    default = [imp for imp in imports if imp["import_type"] == "default"]
    assert any(imp["symbol_name"] == "React" for imp in default)


def test_parse_call_edges(ts_file):
    result = parse_file(ts_file)
    calls = result["call_edges"]
    # computeCamera calls helper
    helper_calls = [c for c in calls if c["name"] == "helper"]
    assert len(helper_calls) >= 1


def test_parse_methods(ts_file):
    result = parse_file(ts_file)
    methods = [s for s in result["symbols"] if s["kind"] == "method"]
    assert len(methods) >= 1
    assert methods[0]["name"] == "flyTo"


def test_parse_parent_symbol(ts_file):
    result = parse_file(ts_file)
    # flyTo should have parent_symbol="CameraManager"
    methods = [s for s in result["symbols"] if s["kind"] == "method"]
    fly = next((m for m in methods if m["name"] == "flyTo"), None)
    assert fly is not None
    assert fly["parent_symbol"] == "CameraManager"


def test_parse_signatures(ts_file):
    result = parse_file(ts_file)
    cm = next((s for s in result["symbols"] if s["name"] == "computeCamera"), None)
    assert cm is not None
    assert cm["signature"] is not None
    assert "computeCamera" in cm["signature"]


def test_parse_language_detection():
    """Verify .tsx files get typescriptreact language."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".tsx", delete=False) as f:
        f.write(b"const x = <div />;")
        path = f.name
    try:
        result = parse_file(path)
        assert result["language"] == "typescriptreact"
    finally:
        os.unlink(path)
