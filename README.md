# codeatlas

A local-first, language-aware code knowledge base for TypeScript/TSX projects.

Think: a personal Sourcegraph Lite — index once, query forever, no cloud needed.

## Quick Start

```bash
# Install
cd codeatlas
pip install -e .

# Index a project
codeatlas index ~/path/to/typescript-project --verbose

# Explore
codeatlas stats
codeatlas symbols ExplorerApp
codeatlas callers computeCameraFromRidge
codeatlas callees handleSelectFeature
codeatlas chain handleSelectFeature --depth 3
codeatlas graph Camera --type deps
codeatlas deps lib/terrain.ts
```

## Commands

| Command | Description |
|---------|-------------|
| `index <path>` | Index a TypeScript/TSX project |
| `stats` | Show index statistics |
| `symbols <name>` | Find symbols by name |
| `file <path>` | List symbols in a file |
| `imports <name>` | Find who imports a symbol |
| `used-by <module>` | Find who imports from a module |
| `list --kind <kind>` | Filter symbols by kind |
| `callers <name>` | Find callers of a function |
| `callees <name>` | Find what a function calls |
| `chain <name>` | Recursive call chain |
| `graph <name>` | Generate Mermaid dependency/call graph |
| `deps <path>` | Show file dependencies |

## Requirements

- Python 3.11+
- tree-sitter + tree-sitter-languages (auto-installed via pip)
- SQLite3 (included in Python stdlib)

## License

MIT
