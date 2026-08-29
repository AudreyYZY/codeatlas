"""Tests for config module."""

import os

from codeatlas import config


def test_detect_project_name():
    assert config.detect_project_name("/Users/me/projects/my-app") == "my-app"
    assert config.detect_project_name("./relative/path") == "path"
    assert config.detect_project_name("/foo") == "foo"


def test_data_home_follows_the_env_var(isolated_data_home):
    # The conftest fixture points CODEATLAS_HOME at a temp dir; get_data_home
    # must read it live rather than freezing the value at import time.
    assert config.get_data_home() == os.path.realpath(isolated_data_home) or (
        config.get_data_home() == isolated_data_home
    )


def test_data_home_default(monkeypatch):
    monkeypatch.delenv("CODEATLAS_HOME", raising=False)
    assert config.get_data_home() == os.path.abspath(os.path.expanduser("~/.codeatlas"))


def test_get_project_dir(isolated_data_home):
    d = config.get_project_dir("test-project")
    assert d.endswith(os.path.join("projects", "test-project"))
    assert d.startswith(isolated_data_home)


def test_get_db_path_creates_the_directory(isolated_data_home):
    path = config.get_db_path("test-project")
    assert path.endswith(os.path.join("test-project", "index.db"))
    assert os.path.isdir(os.path.dirname(path))


def test_project_name_cannot_escape_the_data_dir(isolated_data_home):
    d = config.get_project_dir("../../etc/passwd")
    assert os.path.dirname(d).endswith("projects")
    assert ".." not in d


def test_sanitize_project_name():
    assert config.sanitize_project_name("my app/v2") == "my-app-v2"
    assert config.sanitize_project_name("  ...  ") == "project"
    assert config.sanitize_project_name("ok-name_1.2") == "ok-name_1.2"


def test_list_projects_empty(isolated_data_home):
    assert config.list_projects() == []


def test_supported_extensions():
    for ext in (".ts", ".tsx", ".js", ".jsx", ".py"):
        assert ext in config.SUPPORTED_EXTENSIONS


def test_detect_language():
    assert config.detect_language("a/b/c.tsx") == "typescriptreact"
    assert config.detect_language("x.py") == "python"
    assert config.detect_language("x.rs") == "unknown"


def test_exclude_dirs():
    for d in ("node_modules", ".git", "dist", "__pycache__", ".venv"):
        assert d in config.EXCLUDE_DIRS
