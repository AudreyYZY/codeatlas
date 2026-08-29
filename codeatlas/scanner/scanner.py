"""Scanner: walk a project directory and yield file paths."""

import os
from collections.abc import Iterator

from codeatlas.config import EXCLUDE_DIRS, MAX_FILE_BYTES, SUPPORTED_EXTENSIONS


def scan_files(project_root: str, max_bytes: int = MAX_FILE_BYTES) -> Iterator[str]:
    """
    Walk project_root and yield absolute paths for all supported source files.

    Skips excluded and hidden directories, symlinked directories (which can
    introduce cycles), minified bundles, and files larger than ``max_bytes``.
    """
    project_root = os.path.abspath(project_root)
    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune excluded / hidden / symlinked directories in-place
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDE_DIRS
            and not d.startswith(".")
            and not os.path.islink(os.path.join(dirpath, d))
        ]

        for fname in sorted(filenames):
            if not fname.endswith(SUPPORTED_EXTENSIONS):
                continue
            # Generated bundles carry no useful structure and dominate runtime.
            if fname.endswith((".min.js", ".min.ts", ".bundle.js", ".d.ts")):
                continue
            full = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(full) > max_bytes:
                    continue
            except OSError:
                continue
            yield full
