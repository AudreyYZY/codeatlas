## 0.5.0 — 2026-09-19

- Added evidence-backed directory architecture and separate import/call/argument/return/handoff file views.
- Added index-time AST implementation facts: parameters, documentation, returns, control structures and bounded local provenance.
- Linked guides to resolved internal declarations, callsite evidence and indexed/current-source status; added Markdown, SVG and Mermaid exports.
- Added standalone snapshot support for the new reader without backend/CDN dependencies.
- Fixed missing TypeScript namespace imports, self-parented top-level declarations, arrow async flags and local scope/export attribution.
- Added an additive `file_analyses` table; incremental runs backfill missing facts.

# Changelog

## 0.4.0

- `codeatlas app [PATH]`: free loopback port, readiness-based browser opening and first-launch example.
- Mac double-click launcher plus first-time setup script.
- Searchable directory/declaration outlines and layered function call graphs with SVG export.
- Preserve callable identity across files and same-name methods within a file; keep ambiguous/member calls unresolved.
- Declaration-specific symbol details and disambiguation by file/line.
- Portable self-contained read-only HTML snapshots; source bodies and local absolute paths excluded.
- Ship individual TSX/Python grammars with installation; remove runtime grammar downloads.
- Resolve Python package-submodule imports to their real source files.
- Show graph limits precisely, validate traversal parameters and retain focused nodes when capped.
- Report partial parsing failures, fail all-parser-failure runs and preserve the previous usable index in that case.
- Keep parser instances per indexing thread; split frontend JS/CSS into maintainable assets.
- Schema version 4 rebuilds old indexes to correct caller attribution; re-index after upgrading.

- Reject overlapping re-index jobs and stage uploads separately from existing sources.
