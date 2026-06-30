"""Path resolver: resolve import paths to real files."""

import os
from typing import Any

# Path aliases parsed from tsconfig.json (e.g. {"@/*": "./*"}).
# Can be injected at index time.
DEFAULT_ALIASES: dict[str, str] = {}

# Extension lookup order for resolving bare import paths
EXTENSION_ORDER = (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")


def parse_tsconfig_aliases(project_root: str) -> dict[str, str]:
    """
    Read tsconfig.json to extract TypeScript path aliases.
    Returns a dict mapping alias patterns to relative directory targets.
    """
    import json

    tsconfig_path = os.path.join(project_root, "tsconfig.json")
    if not os.path.exists(tsconfig_path):
        return {}

    try:
        with open(tsconfig_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    paths = data.get("compilerOptions", {}).get("paths", {})
    base_url = data.get("compilerOptions", {}).get("baseUrl", ".")

    aliases = {}
    for alias_pattern, targets in paths.items():
        if targets and len(targets) > 0:
            target = targets[0]
            if alias_pattern.endswith("/*"):
                # "@/components/*" → "components/*"
                prefix = alias_pattern[:-2]
                target_prefix = target[:-2] if target.endswith("/*") else target
                aliases[prefix] = os.path.normpath(os.path.join(base_url, target_prefix))
            else:
                # direct alias
                aliases[alias_pattern] = os.path.normpath(os.path.join(base_url, target))
    return aliases


def resolve_import_path(
    import_source: str,
    project_root: str,
    aliases: dict[str, str]
) -> tuple[str | None, str | None]:
    """
    Resolve an import source to a real file path relative to project_root.

    Returns (resolved_rel_path, resolved_abs_path) or (None, None) if unresolvable.

    Handles:
      - "@/lib/terrain" → "lib/terrain.ts"
      - "react" → None (external package)
      - "./foo" → "path/to/foo.ts"
      - "../bar" → "path/bar.tsx"
    """
    # 1. External packages — no resolution needed
    if not import_source.startswith((".", "@", "/")):
        return None, None

    resolved_rel = import_source

    # 2. Resolve path aliases
    for alias_prefix, target_dir in aliases.items():
        if import_source.startswith(alias_prefix):
            suffix = import_source[len(alias_prefix):]
            # Strip leading "/" before joining
            suffix = suffix.lstrip("/")
            resolved_rel = os.path.normpath(os.path.join(target_dir, suffix))
            break

    # 3. If the resolved path doesn't start with a known base, it's still relative
    # 4. Try extensions in order
    abs_path = os.path.join(project_root, resolved_rel)

    # Already a file with extension?
    if os.path.isfile(abs_path):
        return resolved_rel, abs_path

    # Try appending extensions
    for ext in EXTENSION_ORDER:
        candidate = abs_path + ext
        if os.path.isfile(candidate):
            return resolved_rel + ext, candidate

    # 5. Unresolved — return the last tried relative path but no abs path
    return resolved_rel, None
