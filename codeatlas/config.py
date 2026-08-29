"""Global config for codeatlas."""

import os

# Root directory for all codeatlas data.
# Overridable with CODEATLAS_HOME (used by tests and by the web server).
DATA_HOME = os.path.abspath(os.path.expanduser(os.environ.get("CODEATLAS_HOME", "~/.codeatlas")))


def get_data_home() -> str:
    """Return the codeatlas data root, re-reading the env var on each call.

    Reading ``CODEATLAS_HOME`` lazily (instead of only at import time) lets
    tests and the web server point codeatlas at a temporary directory.
    """
    return os.path.abspath(os.path.expanduser(os.environ.get("CODEATLAS_HOME", "~/.codeatlas")))


def get_project_dir(project_name: str) -> str:
    """Return the directory for a project's data."""
    return os.path.join(get_data_home(), "projects", sanitize_project_name(project_name))


def get_db_path(project_name: str) -> str:
    """Return the SQLite database path for a project."""
    os.makedirs(get_project_dir(project_name), exist_ok=True)
    return os.path.join(get_project_dir(project_name), "index.db")


def list_projects() -> list[str]:
    """List all indexed project names."""
    projects_dir = os.path.join(get_data_home(), "projects")
    if not os.path.isdir(projects_dir):
        return []
    return sorted(
        d for d in os.listdir(projects_dir) if os.path.isdir(os.path.join(projects_dir, d))
    )


def detect_project_name(path: str) -> str:
    """Derive a project name from a directory path (last component)."""
    return sanitize_project_name(os.path.basename(os.path.abspath(path)))


def sanitize_project_name(name: str) -> str:
    """Make a project name safe to use as a single directory component.

    Guards against path traversal (``../../etc``) when a name arrives from the
    CLI or over HTTP.
    """
    cleaned = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name.strip())
    cleaned = cleaned.strip(".-") or "project"
    return cleaned[:100]


# ── Languages ──

# Extension → language label. Also defines what the scanner picks up.
LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascriptreact",
    ".py": "python",
    ".pyi": "python",
}

# File extensions we support scanning
SUPPORTED_EXTENSIONS = tuple(LANGUAGE_BY_EXTENSION)

# Which extensions belong to which parser family
TS_EXTENSIONS = (".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx")
PY_EXTENSIONS = (".py", ".pyi")


def detect_language(file_path: str) -> str:
    """Return the language label for a file path."""
    ext = os.path.splitext(file_path)[1].lower()
    return LANGUAGE_BY_EXTENSION.get(ext, "unknown")


# Directories to exclude when scanning
EXCLUDE_DIRS = {
    "node_modules",
    ".next",
    ".git",
    "dist",
    "build",
    "out",
    ".turbo",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".eggs",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "vendor",
    "target",
}

# Hard cap so one pathological file cannot stall an index run (2 MB).
MAX_FILE_BYTES = 2 * 1024 * 1024
