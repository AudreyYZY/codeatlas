"""Shared test fixtures.

Every test runs against a throwaway CODEATLAS_HOME so the suite never touches
the developer's real ``~/.codeatlas`` index.
"""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_data_home(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("CODEATLAS_HOME", tmp)
        yield tmp


@pytest.fixture
def ts_project():
    """A small TypeScript project with aliases, relative imports and a cycle."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "src", "components"))
        os.makedirs(os.path.join(tmp, "src", "lib"))

        def write(rel, text):
            path = os.path.join(tmp, rel)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

        write(
            "tsconfig.json",
            """{
              // comment, and a trailing comma below
              "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"] }, },
            }""",
        )
        write(
            "src/index.ts",
            'import { Map } from "./components/Map";\n'
            'import { helper } from "@/lib/util";\n'
            'import React from "react";\n'
            'import { Thing } from "@scope/pkg";\n'
            "export function main() { helper(); return Map(); }\n",
        )
        write(
            "src/components/Map.ts",
            'import { helper } from "../lib/util";\n'
            "export const Map = () => { helper(); return null; };\n",
        )
        write(
            "src/lib/util.ts",
            'import { Map } from "../components/Map";\nexport function helper() { return Map; }\n',
        )
        write("src/lib/index.ts", 'export { helper } from "./util";\n')
        yield tmp


@pytest.fixture
def py_project():
    """A small Python package with absolute and relative imports."""
    with tempfile.TemporaryDirectory() as tmp:
        pkg = os.path.join(tmp, "pkg")
        os.makedirs(os.path.join(pkg, "sub"))

        def write(rel, text):
            with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
                f.write(text)

        write("pkg/__init__.py", "")
        write("pkg/sub/__init__.py", "")
        write(
            "pkg/core.py",
            "import os\n"
            "from pkg.sub.helpers import assist\n"
            "CONST = 3\n"
            "class Engine:\n"
            "    def run(self):\n"
            "        return assist()\n"
            "def start():\n"
            "    return Engine().run()\n",
        )
        write(
            "pkg/sub/helpers.py",
            "from ..core import CONST\ndef assist():\n    return CONST\n",
        )
        yield tmp
