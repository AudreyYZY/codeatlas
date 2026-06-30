"""Tests for the file scanner."""

import os
import tempfile

from codeatlas.scanner.scanner import scan_files


def test_scan_finds_ts_files():
    """Scan should find .ts and .tsx files."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create some source files
        os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "node_modules"), exist_ok=True)

        (os.path.join(tmp, "src", "index.ts"),)
        open(os.path.join(tmp, "src", "index.ts"), "w").close()
        open(os.path.join(tmp, "src", "App.tsx"), "w").close()
        open(os.path.join(tmp, "src", "utils.ts"), "w").close()
        # Should be excluded
        open(os.path.join(tmp, "node_modules", "lib.ts"), "w").close()
        open(os.path.join(tmp, "README.md"), "w").close()

        files = list(scan_files(tmp))
        assert len(files) == 3
        names = [os.path.basename(f) for f in files]
        assert "index.ts" in names
        assert "App.tsx" in names
        assert "utils.ts" in names


def test_scan_excludes_hidden_dirs():
    """Scan should skip directories starting with dot."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".hidden"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "src"), exist_ok=True)

        open(os.path.join(tmp, ".hidden", "secret.ts"), "w").close()
        open(os.path.join(tmp, "src", "visible.ts"), "w").close()

        files = list(scan_files(tmp))
        assert len(files) == 1
        assert os.path.basename(files[0]) == "visible.ts"


def test_scan_excludes_build_dirs():
    """Scan should skip dist, build, .next, .turbo etc."""
    with tempfile.TemporaryDirectory() as tmp:
        for d in ["dist", "build", ".next"]:
            os.makedirs(os.path.join(tmp, d), exist_ok=True)
            open(os.path.join(tmp, d, "output.ts"), "w").close()

        files = list(scan_files(tmp))
        assert len(files) == 0


def test_scan_empty_dir():
    """Scan on empty dir returns nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        files = list(scan_files(tmp))
        assert len(files) == 0


def test_scan_handles_js_files():
    """Scan also picks up .js and .jsx."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "legacy.js"), "w").close()
        open(os.path.join(tmp, "component.jsx"), "w").close()
        files = list(scan_files(tmp))
        assert len(files) == 2
