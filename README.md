<div align="center">

# CodeAtlas

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-Local-003B57?style=for-the-badge)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br>

### Index once. Query forever. No cloud. No token cost.

<br>

*A local-first code knowledge base that turns your TypeScript project into an indexable, queryable SQLite database — so you can understand architecture, trace call chains, and generate diagrams without reading every file.*

Recommended for use with **Claude Code**, **Codex**, or any AI agent that needs structured context before prompting.

</div>

---

## Why CodeAtlas?

Large repositories are hard to understand.

Searching for symbols is not enough.

Reading hundreds of files is slow.

LLMs repeatedly scan the same code, burning tokens on context you've already indexed.

**CodeAtlas solves this by indexing your project once into a local SQLite database.**

After indexing, you can:

- **Find any symbol** — functions, classes, interfaces, types, enums, variables
- **Trace call chains** — who calls this? what does this call? how deep?
- **Map dependencies** — file-level downstream and upstream relationships
- **Generate Mermaid diagrams** — visual dependency graphs and call graphs
- **Produce architecture reports** — module breakdowns, symbol counts, import heatmaps

Think of it as a **personal Sourcegraph Lite** — no cloud, no API keys, no per-query cost. Just your code, indexed locally, queryable forever.

---

## Who is it for?

| User | Scenario |
|------|----------|
| **Solo Developer** | Return to an old project and understand the architecture without re-reading everything |
| **Open Source Contributor** | Learn an unfamiliar repository quickly before submitting a PR |
| **AI Engineer** | Retrieve relevant context (call graphs, dependency reports) before prompting LLMs |
| **Interview Candidate** | Prepare architecture explanations for senior engineering interviews |
| **Technical Writer** | Generate accurate module maps and symbol inventories for documentation |

---

## What can it do?

| Capability | Description |
|------------|-------------|
| **Symbol Search** | Find functions, classes, interfaces, types, enums, and variables by name across the entire project |
| **Call Graph** | Traverse who-calls-whom with configurable depth (BFS) |
| **Dependency Graph** | Map file-level downstream (imports) and upstream (imported-by) relationships |
| **Architecture Report** | Get file counts, symbol breakdowns, import heatmaps, and module summaries |
| **Module Analysis** | Inspect a module's symbols, its callers, its callees, and its dependencies |
| **Mermaid Export** | Generate TD diagrams for both dependency graphs and call chains |
| **tsconfig Alias Support** | Resolves `@/`, `~/`, and other path aliases from `tsconfig.json` |

---

## Architecture

```
Your TypeScript Project
        │
        ▼
   ┌─────────┐
   │  Scan   │  Walk the directory tree, skip node_modules / dist / .git
   └────┬────┘
        ▼
   ┌─────────┐
   │  Parse  │  tree-sitter AST → symbols, imports, call edges
   └────┬────┘
        ▼
   ┌─────────────┐
   │  Resolve    │  tsconfig aliases + extension resolution
   └─────┬───────┘
        ▼
   ┌─────────────┐
   │  SQLite DB  │  Local-first, WAL mode, project-isolated
   │  ~/.codeatlas│
   └─────┬───────┘
        │
        ▼
   ┌──────────┐    ┌──────────┐    ┌────────────┐
   │  Query   │    │  Graph   │    │  Mermaid   │
   │  Symbols │    │  BFS     │    │  Export    │
   └──────────┘    └──────────┘    └────────────┘
```

---

## Typical Workflow

Here's how a developer might use CodeAtlas when joining a new project:

```
1. Clone the project
        │
        ▼
2. Index it (one command)
   codeatlas index .
        │
        ▼
3. Explore the architecture
   codeatlas stats
   codeatlas symbols Camera
        │
        ▼
4. Trace a call chain
   codeatlas callers computeCameraFromRidge
   codeatlas chain handleSelectFeature --depth 3
        │
        ▼
5. Generate a diagram
   codeatlas graph Camera --type deps
        │
        ▼
6. Feed the output to an LLM for deeper analysis
   (or just read it — no LLM required)
```

---

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Index a project

```bash
# Index the current directory
codeatlas index .

# Or index a specific path with a custom name
codeatlas index ~/projects/my-app --name my-app
```

### 3. Query the index

```bash
# See what's in the index
codeatlas stats

# Find a symbol by name
codeatlas symbols Camera

# See who calls a function
codeatlas callers computeCameraFromRidge

# See what a function calls
codeatlas callees handleSelectFeature

# Trace a call chain
codeatlas chain handleSelectFeature --depth 3

# Generate a Mermaid dependency diagram
codeatlas graph Camera --type deps

# Show file-level dependencies
codeatlas deps lib/terrain.ts
```

That's it. Your knowledge base is ready to query anytime.

---

## Real Example: SkyTerrain

After indexing a TypeScript project, here's what you get:

### Architecture Overview

```
$ codeatlas stats

📊 SkyTerrain
   Files:   59
   Symbols: 1049
   Imports: 342
   Calls:   1598
   Deps:    287

   Symbol kinds:
     function              412
     class                  98
     interface              76
     type                   54
     enum                   23
     variable              386
```

### Dependency Graph (Mermaid)

```
$ codeatlas graph ExplorerApp --type deps

graph TD
    ExplorerApp --> CesiumMap
    ExplorerApp --> Camera
    ExplorerApp --> Terrain
    CesiumMap --> MapConfig
    CesiumMap --> TileProvider
    Camera --> Projection
    Terrain --> Heightmap
    Terrain --> Dataset
```

### Call Chain

```
$ codeatlas chain handleSelectFeature --depth 2

🔗 Call chain: handleSelectFeature()

    handleSelectFeature()
      → updateSelection()
      → renderFeature()
      → notifyListeners()
      updateSelection()
        → clearPrevious()
        → markActive()
      renderFeature()
        → drawGeometry()
        → applyStyle()
```

---

## Commands

All commands share a `--project <name>` flag to target a specific indexed project.

| Command | Description |
|---------|-------------|
| `index <path> [--name NAME] [--verbose]` | Index a TypeScript/TSX project into SQLite |
| `stats` | Show index statistics (files, symbols, imports, calls, deps) |
| `symbols <name>` | Find symbols by name across the project |
| `file <path>` | List all symbols defined in a file |
| `imports <name>` | Find which files import a given symbol |
| `used-by <module>` | Find which files import from a module |
| `list [--kind KIND] [--exported]` | List symbols, optionally filtered by kind or export status |
| `callers <name>` | Find who calls a given symbol |
| `callees <name>` | Find what a given symbol calls |
| `chain <name> [--depth N]` | Show recursive call chain from a symbol |
| `graph <target> [--type deps\|calls] [--direction downstream\|upstream] [--depth N]` | Generate a Mermaid TD diagram |
| `deps <path> [--direction downstream\|upstream] [--depth N]` | Show file-level dependency tree |

---

## Comparison

| Feature | CodeAtlas | Cursor | Sourcegraph |
|---------|-----------|--------|-------------|
| Local-first | ✅ | ❌ | ❌ |
| SQLite index | ✅ | ❌ | ❌ |
| Architecture report | ✅ | Limited | ❌ |
| Call graph traversal | ✅ | Partial | ✅ |
| Dependency graph | ✅ | ❌ | ✅ |
| Mermaid export | ✅ | ❌ | ❌ |
| LLM required | ❌ | ✅ | ❌ |
| tsconfig alias support | ✅ | ❌ | ❌ |
| Offline / no network | ✅ | ❌ | ❌ |
| Free forever | ✅ | Paid | Paid tier |

---

## FAQ

### Does it send my code to the cloud?

No. Everything is stored locally in `~/.codeatlas/projects/<name>/index.db`. No network calls.

### Does it require OpenAI or any LLM?

No. CodeAtlas works entirely offline. It's a standalone CLI tool.

### Can I use it before prompting GPT/Claude?

Yes. Many users run CodeAtlas first, then paste the output (call chains, dependency graphs, architecture reports) into their LLM session for richer context.

### Which languages does it support?

Currently: **TypeScript, TSX, JavaScript, JSX**. Python support is planned.

### Where is the data stored?

Each indexed project gets its own SQLite database at `~/.codeatlas/projects/<project-name>/index.db`. The database uses WAL mode for concurrent read safety.

### Can I index the same project twice?

Yes — running `codeatlas index` again will overwrite the previous index.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| CLI Framework | Click |
| AST Parser | tree-sitter-languages (TSX) |
| Storage | SQLite3 (WAL mode) |
| Graph Algorithms | BFS with configurable depth |
| Diagram Output | Mermaid TD syntax |

---

## Roadmap

- [ ] Python parser support
- [ ] Incremental indexing (only changed files)
- [ ] Web UI for querying the index
- [ ] Symbol rename / refactor safety checks
- [ ] Import cycle detection
- [ ] API for programmatic access (Python SDK)

---

## License

MIT
