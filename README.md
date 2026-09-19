<div align="center">

# CodeAtlas

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![SQLite](https://img.shields.io/badge/SQLite-Local-003B57?style=for-the-badge)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br>

### Index once. Query forever. No cloud. No token cost.

<br>

*A local-first code knowledge base that turns a TypeScript, JavaScript or Python project into an indexable, queryable SQLite database — so you can understand architecture, trace call chains, spot import cycles and generate diagrams without reading every file.*

**New in 0.5:** evidence-backed directory architecture, file argument/return/handoff graphs and source-grounded implementation guides. Click through modules → files → callsite evidence; export SVG, Mermaid or Markdown. See [the implementation guide](docs/ARCHITECTURE_CN.md).

**Introduced in 0.4:** directory/declaration outlines, identity-preserving call graphs, portable HTML snapshots and a one-click local app. Offline grammars ship with the install.

**Introduced in 0.3:** a built-in web UI (`codeatlas serve`), Python support, incremental indexing and cycle detection.

Recommended for use with **Claude Code**, **Codex**, or any AI agent that needs structured context before prompting.

[中文版 README](README_CN.md)

</div>

---

## What is CodeAtlas?

CodeAtlas is a **local-first code knowledge base**.

You point it at a TypeScript/JavaScript/Python project. It indexes the code into a local SQLite database. From then on, you can query symbols, trace call chains, map dependencies, detect import cycles and generate diagrams — all offline, all free, from the CLI or from a browser.

It is not a code search tool. It is not an AI documentation generator. It is a **structured index** of your codebase, designed for depth over breadth.

---

## When should I use CodeAtlas?

- **Understanding unfamiliar repositories** — jump straight to the architecture, skip the file-by-file reading
- **Preparing technical interviews** — generate call graphs and dependency maps to explain a system
- **Writing architecture documentation** — get accurate symbol inventories and module breakdowns
- **Exploring large TypeScript projects** — find callers, callees, and dependency chains in seconds
- **Providing high-quality context for LLMs** — feed structured analysis output into Claude / GPT for richer prompts

If your task involves understanding *how code relates to other code*, CodeAtlas is built for that.

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
- **Map dependencies** — file-level downstream (imports) and upstream (imported-by) relationships
- **Detect import cycles** — strongly connected components in the file graph
- **Generate Mermaid diagrams** — visual dependency graphs and call graphs
- **Produce architecture reports** — module breakdowns, symbol counts, import heatmaps
- **Explore it in a browser** — `codeatlas serve` opens an interactive dependency map, file browser and symbol explorer

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

## What can it generate?

### Architecture Report

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

## Architecture

```
Your project (TS / JS / Python)
        │
        ▼
   ┌─────────┐
   │  Scan   │  Walk the tree; skip node_modules / dist / .venv / hidden dirs
   └────┬────┘
        ▼
   ┌─────────┐
   │  Parse  │  tree-sitter AST → symbols, imports, call edges
   └────┬────┘  (parser.py dispatches by extension: ts_parser / py_parser)
        ▼
   ┌─────────────┐
   │  Resolve    │  tsconfig aliases + extension order, or Python module paths —
   └─────┬───────┘  always relative to the *importing* file
        ▼
   ┌──────────────┐
   │  SQLite DB   │  Local-first, WAL mode, versioned schema, project-isolated
   │  ~/.codeatlas│  (content hashes enable incremental re-indexing)
   └─────┬────────┘
        │
        ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐
 │ Query  │ │ Graph  │ │ Cycles │ │ Mermaid │ │  Web UI  │
 │Symbols │ │  BFS   │ │ Tarjan │ │ Export  │ │ FastAPI  │
 └────────┘ └────────┘ └────────┘ └─────────┘ └──────────┘
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
6. Read the generated walkthrough
   codeatlas explain
   codeatlas serve          # ...or explore it all in a browser
        │
        ▼
7. Feed the output to an LLM for deeper analysis
   (or just read it — no LLM required)
```

---

## Open the browser explorer

On macOS, run `./setup.sh` once and then double-click **Open CodeAtlas.command**. The app uses an available loopback port, opens a browser when ready and includes a small checkout example for the first launch. Index your own folder or upload a source ZIP from the sidebar. Close the Terminal window or press Ctrl+C to stop the server.

From an installed package:

```sh
codeatlas app                  # browser UI on a free local port
codeatlas app /path/to/repo    # index the repo and open the UI
```

The browser offers a walkthrough, dependency map, searchable source directory tree with declaration/class outlines, function call graph, file/source inspection, symbol search and cycle review. Callers sit to the left of the selected function and callees to the right. Unresolved calls can be shown separately. Download a call graph as SVG for documentation.

File/declaration identities are preserved: same-name methods in different classes and same-name functions in different files are separate nodes. Direct local and explicit import names are linked conservatively; dynamic/member, external and ambiguous calls are visible as unresolved candidates. Static analysis cannot determine every runtime target. Top-level call sites remain in the index but are not represented as function nodes. Legacy CLI name-based `chain` queries still aggregate by name; use the browser call graph for declaration-specific exploration.

Only supported TS/JS/Python source files are indexed. The directory tree is an outline of that index, not every asset/configuration file in the repository. Graphs explicitly display shown/total counts when a view is capped; focusing on a declaration or file reduces clutter.

### Share a directly accessible snapshot

```sh
codeatlas snapshot --project my-app -o my-app.html
```

Open the result directly in a browser, email it or host it as a static file. It has no server, CDN or Python dependency. Snapshots exclude source bodies and indexed absolute local paths, but contain file names, declaration signatures, documentation, implementation expressions, imports and dependencies; review private project metadata before sharing. They are read-only: local indexing and ZIP import require the running app.

[`codeatlas-demo.html`](codeatlas-demo.html) is a generated example exploring CodeAtlas itself. See [VALIDATION.md](VALIDATION.md) for tested behavior.

## Quick Start

### 1. Install

```bash
pip install -e .            # CLI only
pip install -e ".[web]"     # CLI + web UI
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

### 4. Or explore it in a browser

```bash
codeatlas serve
```

Opens `http://127.0.0.1:8000`, where you can point at a folder (or drop a `.zip`),
watch it index, and then read the generated walkthrough, pan around an interactive
dependency map, browse files and symbols, and see any import cycles. The server binds
to localhost and reads the same SQLite indexes the CLI writes — nothing is uploaded
anywhere.

That's it. Your knowledge base is ready to query anytime.

---

## Commands

All commands share a `--project <name>` flag to target a specific indexed project.

| Command | Description |
|---------|-------------|
| `index <path> [--name NAME] [--verbose] [--incremental]` | Index a TS/JS/Python project into SQLite |
| `app [PATH] [--no-open]` | Open the browser on a free loopback port; optionally index PATH |
| `snapshot [-o FILE]` | Export a portable read-only HTML explorer |
| `serve [--host H] [--port P] [--no-open]` | Start the web UI |
| `explain [--json]` | Print a structured architecture report (modules, entry points, hotspots, cycles) |
| `stats` | Show index statistics (files, lines, symbols, imports, calls, deps) |
| `projects` | List every indexed project |
| `symbols <name>` | Find symbols by name (`*` is a wildcard) |
| `file <path>` | List all symbols defined in a file |
| `imports <name>` | Find which files import a given symbol |
| `used-by <module>` | Find which files import from a module |
| `list [--kind KIND] [--exported] [--limit N]` | List symbols, optionally filtered |
| `callers <name>` | Find who calls a given symbol |
| `callees <name>` | Find what a given symbol calls |
| `chain <name> [--depth N]` | Show recursive call chain from a symbol |
| `cycles [--mermaid]` | Detect circular imports between files |
| `graph <target> [--type deps\|calls] [--direction downstream\|upstream] [--depth N]` | Generate a Mermaid TD diagram |
| `deps <path> [--direction downstream\|upstream] [--depth N]` | Show file-level dependency tree |
| `export [-o FILE]` | Dump the whole index (report + files + symbols) as JSON |

Re-running `index` rebuilds from scratch. Add `--incremental` to reuse rows for
files whose contents are unchanged — much faster on large repos, same result.

---

## Compared to Other Tools

CodeAtlas focuses on **local-first structured indexing** of TypeScript/JS codebases. It is designed for developers who want precise, queryable code relationships without cloud dependency or LLM cost.

Other tools in this space take different approaches:

- **ZRead** generates AI-driven wiki pages from code using parallel agents. It produces human-readable documentation and supports 14+ languages, but requires an LLM provider.
- **DeepWiki** provides AI-generated repository documentation with public hosting and team collaboration features.
- **Sourcegraph** offers powerful code search across large codebases, including remote repositories.

These tools solve related but different problems. CodeAtlas trades AI-generated narrative for precise, queryable code structure — call graphs, dependency trees, symbol inventories — all running fully offline.

---

## FAQ

### Does it send my code to the cloud?

No. Everything is stored locally in `~/.codeatlas/projects/<name>/index.db`. No network calls.

### Does it require OpenAI or any LLM?

No. CodeAtlas works entirely offline. It's a standalone CLI tool.

### Can I use it before prompting GPT/Claude?

Yes. Many users run CodeAtlas first, then paste the output (call chains, dependency graphs, architecture reports) into their LLM session for richer context.

### Which languages does it support?

**TypeScript, TSX, JavaScript, JSX, and Python** (`.ts .tsx .mts .cts .js .jsx .mjs .cjs .py .pyi`).
Adding a language means writing one parser module — see [CONTRIBUTING.md](CONTRIBUTING.md).

### Where is the data stored?

Each indexed project gets its own SQLite database at `~/.codeatlas/projects/<project-name>/index.db`. The database uses WAL mode for concurrent read safety.

### Can I index the same project twice?

Yes — running `codeatlas index` again overwrites the previous index. Use
`--incremental` to only re-parse files whose contents changed.

### Does the web UI send my code anywhere?

No. `codeatlas serve` runs a local FastAPI server bound to `127.0.0.1`, reads the
same local SQLite index, and serves bundled frontend assets with no CDN
requests. It can index and read any directory you can read, which is why you should
not expose it on a public interface.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| CLI Framework | Click |
| AST Parser | tree-sitter via `tree-sitter-typescript + tree-sitter-python` (TSX + Python grammars) |
| Storage | SQLite3 (WAL mode, versioned schema) |
| Graph Algorithms | BFS with configurable depth; Tarjan's SCC for cycles |
| Diagram Output | Mermaid TD syntax |
| Web UI | FastAPI + a single dependency-free HTML file (canvas force layout) |

---

## Roadmap

- [x] Python parser support
- [x] Incremental indexing (only changed files)
- [x] Web UI for querying the index
- [x] Import cycle detection
- [x] JSON export for programmatic access
- [ ] Cross-file call resolution (today `call_edges` store callee names, resolved at query time)
- [ ] Go / Rust / Java parsers
- [ ] Symbol rename / refactor safety checks
- [ ] Watch mode (re-index on file change)

---

## License

MIT — see [LICENSE](LICENSE).

### Architecture and implementation reader (0.5)

The browser opens with a directory-grouped architecture. `Architecture` groups indexed files by directory depth and aggregates evidence-backed imports, resolved calls and data handoffs. These are source modules, not automatically inferred services or deployment topology. Role labels are directory-name hints.

`Data flow` separates argument inputs, returned results and producer-to-consumer handoffs. Handoffs track direct call results, simple aliases and direct nested call expressions in one straight-line scope. Branch/loop bodies are analyzed independently; provenance never crosses a control-flow join. Dynamic dispatch, mutations, callbacks, HTTP/messages and actual runtime values are not inferred. Static callsite evidence does not guarantee execution.

`File guide` displays module/function documentation, parameters, return expressions, control structures and linked internal callees. Source links include line-numbered excerpts; changed source is flagged against the indexed SHA-256. Export the guide as Markdown. No AI API or external service is involved, so undocumented business semantics still require source review.

Re-index old projects once to populate implementation facts. Incremental indexing reparses unchanged files if those facts are missing. The additive `file_analyses` table preserves compatible v4 indexes; it does not require an eager destructive migration. Offline snapshots include the same reader and source-derived documentation/expressions, while excluding full source bodies.
