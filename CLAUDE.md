# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**codeatlas** indexes TypeScript/TSX/JavaScript/JSX and Python projects into a local SQLite
knowledge base, enabling symbol search, call graph traversal, dependency analysis, cycle
detection, Mermaid diagram generation, and a local web UI. Index once, query forever, no
cloud needed.

## Quick Commands

```bash
# Install (web extras are needed for `codeatlas serve` and tests/test_web.py)
pip install -e ".[web,dev]"

# Run all tests
pytest

# Run a single test file / test
pytest tests/test_indexer.py -v
pytest tests/test_resolver.py::test_tsconfig_alias_resolves -v

# Lint, format, type check — CI runs exactly these
ruff check codeatlas/ tests/
ruff format --check codeatlas/ tests/
mypy codeatlas/

# Coverage
pytest --cov=codeatlas --cov-report=term-missing

# Run the web UI
codeatlas serve

# Build wheel
pip install build && python -m build
```

Tests set `CODEATLAS_HOME` to a temp dir via `tests/conftest.py`, so the suite never
touches the developer's real `~/.codeatlas`.

## Architecture

### Data Flow: Scan → Parse → Resolve → Store

```
index_project()                        # indexer/indexer.py — orchestrator
 ├── scan_files()                     # scanner/scanner.py — walk directory tree
 ├── parse_file()                     # indexer/parser.py — dispatch by extension
 │    ├── parse_ts_file()             # indexer/ts_parser.py  (tree-sitter TSX grammar)
 │    └── parse_py_file()             # indexer/py_parser.py  (tree-sitter Python grammar)
 ├── resolve_import_path()            # indexer/resolver.py — tsconfig aliases + extensions
 │   resolve_python_import()          #                     — dotted modules + relative levels
 └── _insert_*()                      # indexer/indexer.py — two-pass SQLite insertion
      ├── Pass 1: files → symbols → call_edges
      └── Pass 2: imports → dependency_edges (needs the file_id map from pass 1)
```

### Module Structure

```
codeatlas/
├── cli.py                    # Click CLI — every command
├── config.py                 # CODEATLAS_HOME, language map, excluded dirs, name sanitising
├── scanner/scanner.py        # os.walk file finder
├── indexer/
│   ├── indexer.py            # Orchestrator, incremental logic, two-pass insertion
│   ├── parser.py             # Language dispatch + result normalisation
│   ├── ts_parser.py          # TS/TSX/JS/JSX AST walker
│   ├── py_parser.py          # Python AST walker
│   └── resolver.py           # tsconfig (JSONC) aliases; TS + Python import resolution
├── storage/
│   ├── schema.py             # DDL, SCHEMA_VERSION, meta table, drop-and-rebuild migration
│   ├── models.py             # Dataclasses per entity
│   └── queries.py            # Every SQL query lives here — nothing else writes SQL
├── graph/
│   ├── callgraph.py          # Symbol-level BFS (build_call_graph, find_call_chain)
│   ├── dependency.py         # File-level BFS (downstream/upstream)
│   ├── cycles.py             # Iterative Tarjan SCC + a displayable cycle path
│   └── mermaid.py            # Mermaid generators (collision-free node ids)
├── analysis/report.py        # The structured walkthrough: narrative, health signals, markdown
└── web/
    ├── server.py             # FastAPI app factory + REST API + background index jobs
    └── static/index.html     # The entire frontend: one file, no CDN, no build step
```

### Database Schema (6 tables)

| Table | Purpose |
|-------|---------|
| `meta` | `schema_version`, `project_root`, `project_name`, `indexed_at` |
| `files` | Source files with path, language, line/byte counts, mtime, `content_hash` |
| `symbols` | Declarations with `parent_symbol`/`enclosing_type` for nesting |
| `imports` | Import statements with `resolved_file_id` linking to target files |
| `call_edges` | Call sites (`caller_symbol_id` → `callee_name`, best-effort resolution) |
| `dependency_edges` | File-level edges, deduplicated with a `weight` count, `UNIQUE(source, target)` |

`SCHEMA_VERSION` in `storage/schema.py` gates compatibility: a database written by an
older version is dropped and rebuilt on the next index run.

### CLI Design

All query commands use `_connect(project_name)`, which deliberately does *not* call
`get_db_path()` (that creates directories). `--project` overrides the default, which is
the current directory's name. Commands fall into six groups: indexing (`index`),
statistics (`stats`, `projects`), explanation (`explain`, `export`), symbol queries
(`symbols`, `file`, `imports`, `used-by`, `list`), call analysis (`callers`, `callees`,
`chain`), and dependency analysis (`graph`, `deps`, `cycles`) — plus `serve`.

### Parser Details

Both parsers return the same dict shape, documented at the top of `indexer/parser.py`.
That contract is what lets storage, graphs, report and UI stay language-agnostic.

- **ts_parser**: TSX grammar (works for TS/JS/JSX too). Tracks enclosing scope with a
  stack for `parent_symbol`/`enclosing_type`. Classifies imports as `named`, `default`,
  `namespace`, `side_effect`, `re_export` (`export … from` counts as a dependency).
- **py_parser**: functions, classes, methods, module- and class-level assignments (never
  function locals), `import x`, `from .y import z` with a `level` for relative depth.
  `is_export` follows the leading-underscore convention.

### Import Resolution — the subtle part

`resolve_import_path` takes `from_file` and resolves relative specifiers against **that
file's directory**, not the project root. Resolving `./x` against the root was a
long-standing bug that silently emptied the dependency graph for every file outside the
root. Alias prefixes are checked before the bare-specifier rule so `@/lib/x` (alias) and
`@scope/pkg` (npm package) are told apart. `tsconfig.json` is parsed as JSONC — comments
and trailing commas are normal there and `json.load` rejects them.

### Graph Algorithms

`callgraph.py` and `dependency.py` build deduplicated adjacency lists and BFS with a
configurable depth and fan-out cap. `cycles.py` runs an **iterative** Tarjan SCC, so a
deep dependency chain cannot exhaust the recursion limit.

### Web Layer

`create_app()` is a factory (imports FastAPI lazily so the CLI works without the web
extras). Index runs happen on a background thread with a polled job id. The frontend is a
single HTML file with a hand-written canvas force-directed layout — no CDN, because the
project promises to work fully offline.

## Testing Patterns

- `tests/conftest.py` provides `isolated_data_home` (autouse), `ts_project` and
  `py_project` fixtures.
- Parser tests define inline source strings and assert on extracted symbols/imports/calls.
- `test_indexer.py` asserts on real resolved edges, dedup weights, cycles and the
  incremental path (incremental output must equal full-reindex output).
- `test_web.py` uses `importorskip("fastapi")` so it is skipped when web extras are absent.

## Key Implementation Notes

- **Two-pass indexing**: pass 1 inserts files+symbols+calls to obtain file IDs; pass 2
  resolves imports against the complete ID map. Import resolution needs all IDs upfront.
- **Incremental indexing** reuses rows for files whose SHA-256 is unchanged, but always
  rebuilds *import* rows — an unchanged file's edges can still change when its neighbours do.
- **Best-effort call resolution**: `call_edges` store `callee_name` as a string; resolution
  happens at query time. Cross-file call resolution is still open (see the roadmap).
- **Project isolation**: each project gets `$CODEATLAS_HOME/projects/<name>/index.db`.
  Names are sanitised so a name can never escape that directory.
