"""Import-resolution tests — the layer that used to silently mis-resolve
every relative import against the project root instead of the importing file."""

import os

from codeatlas.indexer.resolver import (
    parse_tsconfig_aliases,
    resolve_import_path,
    resolve_python_import,
)


def test_relative_import_resolves_against_the_importing_file(ts_project):
    aliases = parse_tsconfig_aliases(ts_project)
    from_file = os.path.join(ts_project, "src", "components", "Map.ts")
    rel, abs_path = resolve_import_path("../lib/util", ts_project, aliases, from_file=from_file)
    assert rel == "src/lib/util.ts"
    assert abs_path == os.path.join(ts_project, "src", "lib", "util.ts")


def test_dot_slash_import_resolves(ts_project):
    aliases = parse_tsconfig_aliases(ts_project)
    from_file = os.path.join(ts_project, "src", "index.ts")
    rel, abs_path = resolve_import_path("./components/Map", ts_project, aliases, from_file)
    assert rel == "src/components/Map.ts"
    assert abs_path is not None


def test_tsconfig_alias_resolves(ts_project):
    aliases = parse_tsconfig_aliases(ts_project)
    assert aliases == {"@/*": "src/*"}
    rel, abs_path = resolve_import_path(
        "@/lib/util", ts_project, aliases, os.path.join(ts_project, "src", "index.ts")
    )
    assert rel == "src/lib/util.ts"


def test_exact_and_wildcard_aliases_coexist(tmp_path):
    """`"pkg": [...]` and `"pkg/*": [...]` are two rules, not one.

    Real repos (zustand, for one) declare both, and the wildcard target can
    carry an extension: `"pkg/*": ["./src/*.ts"]`.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const a = 1;")
    (tmp_path / "src" / "middleware.ts").write_text("export const b = 2;")
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":".",'
        '"paths":{"pkg":["./src/index.ts"],"pkg/*":["./src/*.ts"]}}}'
    )
    aliases = parse_tsconfig_aliases(str(tmp_path))
    assert resolve_import_path("pkg", str(tmp_path), aliases)[0] == os.path.join("src", "index.ts")
    assert resolve_import_path("pkg/middleware", str(tmp_path), aliases)[0] == os.path.join(
        "src", "middleware.ts"
    )


def test_longest_alias_prefix_wins(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "x.ts").write_text("")
    (tmp_path / "b" / "x.ts").write_text("")
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"paths":{"@/*":["./a/*"],"@/deep/*":["./b/*"]}}}'
    )
    aliases = parse_tsconfig_aliases(str(tmp_path))
    assert resolve_import_path("@/deep/x", str(tmp_path), aliases)[0] == os.path.join("b", "x.ts")


def test_jsonc_tsconfig_with_comments_and_trailing_commas(ts_project):
    # The fixture's tsconfig has both; plain json.load would raise and the
    # aliases would be silently dropped.
    assert parse_tsconfig_aliases(ts_project)


def test_scoped_npm_package_is_external(ts_project):
    aliases = parse_tsconfig_aliases(ts_project)
    assert resolve_import_path("@scope/pkg", ts_project, aliases) == (None, None)
    assert resolve_import_path("react", ts_project, aliases) == (None, None)


def test_index_file_resolution(ts_project):
    rel, abs_path = resolve_import_path(
        "./lib", ts_project, {}, os.path.join(ts_project, "src", "index.ts")
    )
    assert rel == "src/lib/index.ts"


def test_missing_file_reports_candidate_but_no_abs(ts_project):
    rel, abs_path = resolve_import_path(
        "./nope", ts_project, {}, os.path.join(ts_project, "src", "index.ts")
    )
    assert abs_path is None
    assert rel.endswith("nope")


def test_python_absolute_import(py_project):
    rel, abs_path = resolve_python_import(
        "pkg.sub.helpers", py_project, os.path.join(py_project, "pkg", "core.py")
    )
    assert rel == os.path.join("pkg", "sub", "helpers.py")
    assert abs_path is not None


def test_python_relative_import(py_project):
    rel, abs_path = resolve_python_import(
        "core", py_project, os.path.join(py_project, "pkg", "sub", "helpers.py"), level=2
    )
    assert rel == os.path.join("pkg", "core.py")


def test_python_package_import_resolves_to_init(py_project):
    rel, _ = resolve_python_import("pkg.sub", py_project)
    assert rel == os.path.join("pkg", "sub", "__init__.py")


def test_python_stdlib_is_external(py_project):
    assert resolve_python_import("os.path", py_project) == (None, None)


def test_asset_imports_are_not_broken_internal_imports(ts_project):
    # `import "./styles.css"` is a bundler feature, not a missing module.
    for spec in ("./styles.css", "../logo.png", "./data.json", "./font.woff2"):
        assert resolve_import_path(
            spec, ts_project, {}, os.path.join(ts_project, "src", "index.ts")
        ) == (None, None), spec
