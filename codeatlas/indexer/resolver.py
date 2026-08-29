"""Path resolver: resolve import specifiers to real files on disk."""

import json
import os

from codeatlas.config import SUPPORTED_EXTENSIONS

# Path aliases parsed from tsconfig.json (e.g. {"@/*": "./*"}).
# Can be injected at index time.
DEFAULT_ALIASES: dict[str, str] = {}

# Extension lookup order for resolving extension-less TS/JS import paths
EXTENSION_ORDER = (
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    "/index.ts",
    "/index.tsx",
    "/index.js",
    "/index.jsx",
)

# Extension order for Python module resolution
PY_EXTENSION_ORDER = (".py", ".pyi", "/__init__.py", "/__init__.pyi")


def _to_posix(path: str) -> str:
    """Normalize a relative path to forward slashes."""
    return path.replace("\\", "/")


def _strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments and trailing commas from a JSONC document.

    tsconfig.json is JSON-with-comments in practice; ``json.load`` rejects it,
    which used to silently drop every path alias in the project.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1

    cleaned = "".join(out)
    # Remove trailing commas before } or ]
    result: list[str] = []
    for idx, ch in enumerate(cleaned):
        if ch == ",":
            rest = cleaned[idx + 1 :].lstrip()
            if rest[:1] in ("}", "]"):
                continue
        result.append(ch)
    return "".join(result)


def parse_tsconfig_aliases(project_root: str) -> dict[str, str]:
    """
    Read tsconfig.json (or jsconfig.json) and extract path aliases.

    Keys are the patterns exactly as TypeScript writes them, values are the
    first target rewritten relative to the project root, with any ``*`` kept::

        {"@/*": "src/*", "zustand": "src/index.ts", "zustand/*": "src/*.ts"}

    Keeping the raw pattern matters: ``"zustand"`` and ``"zustand/*"`` are two
    different rules that commonly appear side by side, and the ``*`` can sit in
    the middle of the target (``./src/*.ts``), not only at the end.
    """
    for filename in ("tsconfig.json", "jsconfig.json"):
        config_path = os.path.join(project_root, filename)
        if not os.path.exists(config_path):
            continue
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.loads(_strip_jsonc(f.read()))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue

        options = data.get("compilerOptions") or {}
        paths = options.get("paths") or {}
        base_url = options.get("baseUrl") or "."

        aliases: dict[str, str] = {}
        for alias_pattern, targets in paths.items():
            if not targets:
                continue
            target = targets[0]
            head, star, tail = target.partition("*")
            joined = os.path.normpath(os.path.join(base_url, head))
            if star:
                # normpath eats the trailing separator that "./src/*" needs.
                if head.endswith(("/", os.sep)) and not joined.endswith(os.sep):
                    joined += "/"
                aliases[alias_pattern] = _to_posix(joined + star + tail)
            else:
                aliases[alias_pattern] = _to_posix(joined)
        if aliases:
            return aliases
    return {}


def _match_alias(import_source: str, aliases: dict[str, str]) -> tuple[str, str] | None:
    """Return ``(target_pattern, captured_suffix)`` for the best-matching alias.

    Exact patterns win over wildcards, and longer prefixes win over shorter
    ones — the same precedence TypeScript applies.
    """
    if import_source in aliases:
        return aliases[import_source], ""
    best: tuple[str, str] | None = None
    best_len = -1
    for pattern, target in aliases.items():
        if not pattern.endswith("/*"):
            continue
        prefix = pattern[:-2]
        if import_source.startswith(prefix + "/") and len(prefix) > best_len:
            best_len = len(prefix)
            best = (target, import_source[len(prefix) + 1 :])
    return best


def _is_asset(import_source: str) -> bool:
    """True for `import "./styles.css"` / `"../logo.png"` and friends.

    Bundlers let you import stylesheets, images and JSON. Those files exist but
    are not code we index, so counting them as *unresolved internal imports*
    made healthy projects look broken.
    """
    ext = os.path.splitext(import_source)[1].lower()
    return bool(ext) and ext not in SUPPORTED_EXTENSIONS


def _try_extensions(abs_base: str, order: tuple[str, ...]) -> str | None:
    """Return the first existing file for ``abs_base`` + one of ``order``."""
    if os.path.isfile(abs_base):
        return abs_base
    for ext in order:
        candidate = abs_base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_import_path(
    import_source: str,
    project_root: str,
    aliases: dict[str, str],
    from_file: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Resolve a TS/JS import specifier to a real file.

    Args:
        import_source: the specifier as written, e.g. ``"./map"`` or ``"@/lib/x"``.
        project_root: absolute project root.
        aliases: alias prefix → directory, from :func:`parse_tsconfig_aliases`.
        from_file: absolute path of the *importing* file. Relative specifiers
            resolve against this file's directory — omitting it makes every
            ``./x`` import resolve against the project root, which is wrong for
            any file that is not at the root.

    Returns:
        ``(rel_path_from_project_root, abs_path)``, or ``(None, None)`` for
        external packages, or ``(candidate_rel, None)`` when the specifier
        looks internal but no file was found.
    """
    if not import_source or _is_asset(import_source):
        return None, None

    base_dir = os.path.dirname(from_file) if from_file else project_root

    # 1. Alias patterns (checked first — "@/x" is an alias but "@scope/pkg" is
    #    an npm package).
    matched = _match_alias(import_source, aliases)

    if matched is not None:
        target, suffix = matched
        if "*" in target:
            candidate_rel = os.path.normpath(target.replace("*", suffix))
        elif suffix:
            candidate_rel = os.path.normpath(os.path.join(target, suffix))
        else:
            candidate_rel = os.path.normpath(target)
        candidate_rel = _to_posix(candidate_rel)
        abs_base = os.path.join(project_root, candidate_rel)
    elif import_source.startswith("."):
        # 2. Relative to the importing file's directory.
        abs_base = os.path.normpath(os.path.join(base_dir, import_source))
        candidate_rel = _to_posix(os.path.relpath(abs_base, project_root))
    elif import_source.startswith("/"):
        # 3. Root-absolute specifier (some bundlers) — treat as project-root relative.
        candidate_rel = _to_posix(os.path.normpath(import_source.lstrip("/")))
        abs_base = os.path.join(project_root, candidate_rel)
    else:
        # 4. Bare specifier → external package ("react", "@scope/pkg").
        return None, None

    found = _try_extensions(abs_base, EXTENSION_ORDER)
    if found:
        return _to_posix(os.path.relpath(found, project_root)), os.path.abspath(found)
    return candidate_rel, None


def resolve_python_import(
    module: str,
    project_root: str,
    from_file: str | None = None,
    level: int = 0,
) -> tuple[str | None, str | None]:
    """
    Resolve a Python import to a file inside the project.

    Args:
        module: dotted module path, e.g. ``"codeatlas.storage.queries"``. May be
            empty for ``from . import x``.
        project_root: absolute project root.
        from_file: absolute path of the importing file (needed for relative
            imports).
        level: number of leading dots (0 = absolute import).

    Returns ``(rel_path, abs_path)`` or ``(None, None)`` for stdlib/third-party.
    """
    parts = [p for p in module.split(".") if p] if module else []

    if level > 0:
        if not from_file:
            return None, None
        base = os.path.dirname(os.path.abspath(from_file))
        for _ in range(level - 1):
            base = os.path.dirname(base)
        abs_base = os.path.join(base, *parts) if parts else os.path.join(base, "__init__")
        found = _try_extensions(abs_base, PY_EXTENSION_ORDER)
        if found:
            return _to_posix(os.path.relpath(found, project_root)), os.path.abspath(found)
        return _to_posix(os.path.relpath(abs_base, project_root)), None

    if not parts:
        return None, None

    # Absolute import: try from the project root, then from common source roots.
    search_roots = [project_root]
    for extra in ("src", "lib"):
        candidate_root = os.path.join(project_root, extra)
        if os.path.isdir(candidate_root):
            search_roots.append(candidate_root)

    for root in search_roots:
        found = _try_extensions(os.path.join(root, *parts), PY_EXTENSION_ORDER)
        if found:
            return _to_posix(os.path.relpath(found, project_root)), os.path.abspath(found)

    # Not in the project — stdlib or an installed package.
    return None, None
