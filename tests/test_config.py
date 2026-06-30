"""Tests for config module."""

import os

from codeatlas import config


def test_detect_project_name():
    assert config.detect_project_name("/Users/me/projects/my-app") == "my-app"
    assert config.detect_project_name("./relative/path") == "path"
    assert config.detect_project_name("/foo") == "foo"


def test_data_home():
    assert config.DATA_HOME == os.path.expanduser("~/.codeatlas")


def test_get_project_dir():
    d = config.get_project_dir("test-project")
    assert d.endswith("/test-project")
    assert ".codeatlas" in d


def test_get_db_path():
    path = config.get_db_path("test-project")
    assert path.endswith("test-project/index.db")
    assert ".codeatlas" in path


def test_list_projects_empty():
    # Should not crash even if no projects indexed
    projects = config.list_projects()
    assert isinstance(projects, list)


def test_supported_extensions():
    assert ".ts" in config.SUPPORTED_EXTENSIONS
    assert ".tsx" in config.SUPPORTED_EXTENSIONS


def test_exclude_dirs():
    assert "node_modules" in config.EXCLUDE_DIRS
    assert ".git" in config.EXCLUDE_DIRS
    assert "dist" in config.EXCLUDE_DIRS
