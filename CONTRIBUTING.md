# Contributing to CodeAtlas

Thanks for taking a look. CodeAtlas is small on purpose — a local index, a CLI,
and a web UI over the same SQLite database.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[web,dev]"
```

## The loop

```bash
pytest                      # all tests
pytest tests/test_indexer.py -v
ruff check codeatlas/ tests/
ruff format codeatlas/ tests/
mypy codeatlas/
```

CI runs exactly these four commands. If they pass locally, they pass there.

Tests write to a temporary `CODEATLAS_HOME` (see `tests/conftest.py`), so
running the suite never touches your real `~/.codeatlas`.

## Where things live

| Area | Path | Notes |
|---|---|---|
| CLI | `codeatlas/cli.py` | One Click command per verb |
| Scanning | `codeatlas/scanner/` | Which files get looked at |
| Parsing | `codeatlas/indexer/parser.py` | Dispatches by extension to `ts_parser` / `py_parser` |
| Resolution | `codeatlas/indexer/resolver.py` | Import specifier → file on disk |
| Storage | `codeatlas/storage/` | DDL, models, every SQL query |
| Graphs | `codeatlas/graph/` | Call graph, dependency graph, cycles, Mermaid |
| Report | `codeatlas/analysis/report.py` | The structured walkthrough |
| Web | `codeatlas/web/` | FastAPI app + one static HTML file |

## Adding a language

1. Write `codeatlas/indexer/<lang>_parser.py` exposing
   `parse_<lang>_file(path, aliases) -> dict` in the shape documented at the
   top of `parser.py`.
2. Register its extensions in `config.LANGUAGE_BY_EXTENSION` and add an
   `<LANG>_EXTENSIONS` tuple.
3. Dispatch to it in `parser.parse_file`.
4. Teach `resolver.py` how that language resolves imports, and branch on the
   language in `indexer._resolve_one_import`.
5. Add a parser test file and an end-to-end case in `tests/test_indexer.py`.

No change to the schema, the queries, the graphs or the UI should be needed —
that's the point of the shared result shape.

## Schema changes

Bump `SCHEMA_VERSION` in `codeatlas/storage/schema.py`. Existing databases with
an older version are dropped and rebuilt on the next index run, which is
deliberate: a half-migrated index is worse than a rebuilt one.

## Style

Ruff enforces the formatting (100 columns, double quotes). Comments should say
*why*, not restate the code. Keep the web UI dependency-free — it ships as one
HTML file with no CDN, because the project promises to work offline.
