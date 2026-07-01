# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**codeatlas** is a CLI tool that indexes TypeScript/TSX/JavaScript/JSX projects into a local SQLite knowledge base, enabling symbol search, call graph traversal, dependency analysis, and Mermaid diagram generation. Think of it as a personal Sourcegraph Lite — index once, query forever, no cloud needed.

## Quick Commands

```bash
# Install in editable mode
pip install -e .

# Run all tests
pytest -v

# Run a single test file
pytest tests/test_parser.py -v

# Run a single test
pytest tests/test_parser.py::test_parse_functions -v

# Lint
ruff check codeatlas/ tests/

# Format
ruff format codeatlas/ tests/

# Type check
mypy codeatlas/

# Build wheel
pip install build && python -m build
```

## Architecture

### Data Flow: Scan → Parse → Resolve → Store

```
index_project()                        # indexer/indexer.py — orchestrator
 ├── scan_files()                     # scanner/scanner.py — walk directory tree
 ├── parse_file()                     # indexer/parser.py — tree-sitter AST extraction
 │   ├── symbols (functions, classes, interfaces, types, enums, variables)
 │   ├── imports (named, default, namespace, side-effect, type imports)
 │   └── call_edges (call expressions within callable bodies)
 ├── resolve_import_path()            # indexer/resolver.py — tsconfig aliases + extension resolution
 └── _insert_*()                      # indexer/indexer.py — two-pass SQLite insertion
      ├── Pass 1: files → symbols → call_edges
      └── Pass 2: imports → dependency_edges (needs file_id map from pass 1)
```

### Module Structure

```
codeatlas/
├── cli.py                    # Click CLI — all commands (index, stats, symbols, callers, graph, etc.)
├── config.py                 # DATA_HOME (~/.codeatlas), supported extensions, excluded dirs
├── scanner/
│   └── scanner.py            # os.walk file finder, skips node_modules/dist/.git etc.
├── indexer/
│   ├── indexer.py            # Orchestrator: scan → parse → resolve → insert (two-pass)
│   ├── parser.py             # tree-sitter TSX AST walker: symbols, imports, call expressions
│   └── resolver.py           # tsconfig.json path alias parser + import path resolution
├── storage/
│   ├── schema.py             # SQLite DDL: files, symbols, imports, call_edges, dependency_edges + indexes
│   ├── models.py             # Dataclass definitions for each entity
│   └── queries.py            # SQL query functions (find_symbols, find_callers, get_dependencies, etc.)
└── graph/
    ├── callgraph.py          # Symbol-level call graph BFS (build_call_graph, find_call_chain)
    ├── dependency.py         # File-level dependency graph BFS (downstream/upstream_dependencies)
    └── mermaid.py            # Mermaid TD diagram generators for deps and calls
```

### Database Schema (5 tables, 13 indexes)

| Table | Purpose |
|-------|---------|
| `files` | Source files with path, language, line/byte counts |
| `symbols` | Declarations (functions, classes, interfaces, types, enums, variables) with parent_symbol/enclosing_type for nesting |
| `imports` | Import statements with resolved_file_id linking to target files |
| `call_edges` | Function call sites (caller_symbol_id → callee_name, best-effort resolution) |
| `dependency_edges` | File-level edges (source → target, resolved boolean) |

Key relationships: `symbols.file_id → files.id`, `imports.resolved_file_id → files.id`, `call_edges.caller_symbol_id → symbols.id`.

### CLI Design

All commands use a shared `_connect(project_name)` helper that loads the SQLite DB for a project. The `--project` flag overrides the default (current directory name). Commands fall into four categories:

1. **Indexing**: `index` — scan, parse, store
2. **Querying**: `stats`, `symbols`, `file`, `imports`, `used-by`, `list` — symbol/import/file searches
3. **Call analysis**: `callers`, `callees`, `chain` — symbol-level BFS on call graph
4. **Dependency analysis**: `graph`, `deps` — file-level BFS + Mermaid output

### Parser Details (parser.py)

- Uses `tree-sitter-languages` TSX parser (works for TS/JS/JSX too)
- Tracks enclosing scope via a stack for `parent_symbol`/`enclosing_type` (methods belong to classes, nested funcs belong to outer funcs)
- Extracts function signatures from AST (params + return type)
- Collects call expressions recursively within callable bodies (handles both named functions and arrow functions)
- Classifies import types: `named`, `default`, `namespace`, `side_effect`
- Detects `import type`, `export`, `default export`, `async` modifiers

### Graph Algorithms

Both `callgraph.py` and `dependency.py` use BFS with configurable depth (default 3). `callgraph.py` builds an adjacency list from `call_edges` grouped by `caller_name`. `dependency.py` builds from `dependency_edges` grouped by `source_file_id`. Both cap expansion at 10 callees per node to prevent blowup.

## Testing Patterns

- All tests use temporary directories/files for filesystem isolation
- `test_queries.py` uses in-memory SQLite with pre-inserted sample data
- Parser tests define inline TypeScript source strings and assert on extracted symbols/imports/calls
- Scanner tests verify exclusion logic (node_modules, hidden dirs, build dirs)

## Key Implementation Notes

- **Two-pass indexing**: First pass inserts files+symbols+calls to get file IDs. Second pass resolves imports against the file ID map. This is necessary because import resolution depends on knowing all file IDs upfront.
- **Best-effort call resolution**: `call_edges` store `callee_name` as a string, not a resolved symbol ID. Resolution happens at query time via `find_callees`/`find_callers`.
- **tsconfig alias support**: `resolver.py` parses `compilerOptions.paths` from `tsconfig.json` and maps alias prefixes (e.g., `@/`) to directory targets during import resolution.
- **WAL mode**: Database uses `PRAGMA journal_mode = WAL` for concurrent read safety.
- **Project isolation**: Each indexed project gets its own `~/.codeatlas/projects/<name>/index.db`.
