"""Scanner: walk a project directory and yield file paths."""

import os
from collections.abc import Iterator

from codeatlas.config import EXCLUDE_DIRS, SUPPORTED_EXTENSIONS


def scan_files(project_root: str) -> Iterator[str]:
    """
    Walk project_root and yield absolute paths for all supported source files.
    Skips excluded directories.
    """
    project_root = os.path.abspath(project_root)
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune excluded directories in-place
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for fname in filenames:
            if fname.endswith(SUPPORTED_EXTENSIONS):
                yield os.path.join(dirpath, fname)
