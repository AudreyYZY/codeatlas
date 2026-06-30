"""Global config for codeatlas."""

import os

# Root directory for all codeatlas data
DATA_HOME = os.path.expanduser("~/.codeatlas")


def get_project_dir(project_name: str) -> str:
    """Return the directory for a project's data."""
    return os.path.join(DATA_HOME, "projects", project_name)


def get_db_path(project_name: str) -> str:
    """Return the SQLite database path for a project."""
    os.makedirs(get_project_dir(project_name), exist_ok=True)
    return os.path.join(get_project_dir(project_name), "index.db")


def list_projects() -> list[str]:
    """List all indexed project names."""
    projects_dir = os.path.join(DATA_HOME, "projects")
    if not os.path.isdir(projects_dir):
        return []
    return sorted(
        d for d in os.listdir(projects_dir) if os.path.isdir(os.path.join(projects_dir, d))
    )


def detect_project_name(path: str) -> str:
    """Derive a project name from a directory path (last component)."""
    return os.path.basename(os.path.abspath(path))


# File extensions we support scanning
SUPPORTED_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

# Directories to exclude when scanning
EXCLUDE_DIRS = {
    "node_modules",
    ".next",
    ".git",
    "dist",
    "build",
    ".turbo",
    "coverage",
    "__pycache__",
    ".venv",
    "venv",
}
