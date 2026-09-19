# Architecture / implementation reader — 2026-09-19

- **127 pytest tests passed** on local Python 3.11, including 16 new architecture/implementation cases. These check parameter/return directions, producer-to-consumer provenance, aliases/nested calls, independent branch scopes, overwrites, shadowed imports, TS namespace/async/scope facts, missing-analysis backfill, deletion cleanup, focus limits, API validation and stale-source detection.
- Ruff lint/format and mypy passed. Node syntax checks passed for `app.js`, `reader.js` and `snapshot.js`.
- Package rebuilt and installed locally as **0.5.0** without a dependency download. The console entry point and packaged reader assets were verified from outside the checkout.
- Initial editable installation exposed an environment issue: its `.pth` finder was not loaded at interpreter startup, so the console command could not import CodeAtlas. A regular package installation fixed the issue; the setup launcher now uses that mode. Running from the project directory alone would have hidden this failure.
- Self-index: **47 source files, 782 declarations, 3,118 recorded call sites, 74 resolved import edges**, zero file parse failures. These are index counts, not counts of fully resolved runtime calls.
- Browser checks verified seven directory modules with 20 import relationships; module → file-guide navigation; parameters/returns/control steps; real source handoff evidence and line-numbered source excerpts.
- A verified source handoff: `build_dependency_graph()` → `graph` → argument 1 of `shortest_cycle_path()` in `build_report()` (`analysis/report.py:84`) and `api_cycles()` (`web/server.py:568`). The focused handoff view displays four relevant files rather than all 34 production source files.
- The standalone snapshot loaded from a plain static HTML server with **no CodeAtlas backend**. Architecture, handoff filters, callsite evidence and file implementation guides worked; source bodies remained excluded and no browser console errors were recorded in that snapshot session. Direct `file://` loading retains the prior browser-policy testing limitation below.

The analysis is AST-based and offline. Documentation is quoted from source comments/docstrings, not generated business semantics. Module roles are directory-name hints. Provenance covers a straight-line scope (including independent block bodies), direct call results, simple aliases and nested call expressions; it never crosses branch/loop joins. Dynamic dispatch, mutations, closures, HTTP/messages and actual runtime values are outside this release's guarantees. No LLM explanation service or runtime tracer is claimed.

Snapshots now include source-derived documentation and implementation expressions in addition to declarations/dependencies. They exclude complete source bodies and indexed absolute file paths, not all potentially private project metadata.

---

# Local validation — 2026-09-18

Tested in a fresh Python 3.11 environment on Apple Silicon macOS, with the current web/dev dependencies installed independently from the original checkout.

- 111 pytest tests passed, including import alias identity, same-name methods, unresolved member calls, package-submodule imports, file-graph limits, HTML snapshot escaping and preservation of the old index when every parser fails.
- Ruff lint and format checks passed; mypy passed. Two warnings come from upstream TestClient/AnyIO deprecations; they do not indicate test failures.
- Node syntax checks passed for `app.js` and `snapshot.js`.
- CodeAtlas indexed its own 43 source files, 606 declarations and 2,356 recorded call sites with zero parse failures.
- Browser smoke checks verified boot/project selection, directory search, declaration outlines, focused call graphs, and display of shown/total limits. Browser snapshots use the same frontend and an in-memory transport.
- The standalone snapshot loaded and displayed structure/call graphs when served as static HTML without a CodeAtlas backend. Direct `file://` navigation was blocked by the browser automation URL policy, so double-click loading was not automatically verified.
- `codeatlas app --no-open` successfully bound an available loopback port and served the explorer.

This release replaces the old generic language-pack dependency with installed TSX/Python grammars. Installing the old broad dependency in the fresh environment reproduced runtime grammar download failures and zero-file indexes; the new offline grammars fixed those failures. No remote grammar download is needed for analysis.

The new browser call graph uses declaration identity and conservative direct-name/import matching. Member calls, external functions and ambiguous targets cannot all be resolved statically. The source tree covers the supported source files in the index, not repository assets. Legacy CLI name-based chain queries are documented as name-based.

Snapshots exclude source bodies and absolute local paths, not project metadata. File names, declaration signatures and dependency relationships still require review before sharing private codebase snapshots.
