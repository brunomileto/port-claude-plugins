"""Plugin discovery — BFS search bounded by depth.

Finds directories matching a plugin name that contain at least one
recognised marker (skills/, commands/, agents/, .mcp.json by default).
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Iterable


def _is_probable_plugin_dir(path: Path, *, markers: Iterable[str]) -> bool:
    """Return ``True`` if *path* contains at least one known marker child."""
    return path.is_dir() and any((path / m).exists() for m in markers)


def find_plugin(
    plugin_name: str,
    root: Path,
    *,
    max_depth: int = 6,
    markers: Iterable[str] = frozenset({"skills", "commands", "agents", ".mcp.json"}),
) -> list[Path]:
    """BFS for directories named *plugin_name* under *root*, bounded by *max_depth*.

    Parameters
    ----------
    plugin_name:
        Exact directory name to look for.
    root:
        Tree root to start searching from (``~`` is expanded).
    max_depth:
        Maximum folder depth below *root* to recurse.
    markers:
        Child names that identify a directory as a probable plugin.

    Returns
    -------
    list[Path]
        Resolved absolute paths to every matching plugin directory.
    """
    root = root.expanduser().resolve()
    if not root.exists():
        return []

    frozen_markers = frozenset(markers)
    matches: list[Path] = []
    queue: deque[tuple[Path, int]] = deque([(root, 0)])

    while queue:
        current, depth = queue.popleft()
        if depth > max_depth:
            continue
        try:
            for child in current.iterdir():
                if not child.is_dir():
                    continue
                if child.name == plugin_name and _is_probable_plugin_dir(
                    child, markers=frozen_markers
                ):
                    matches.append(child.resolve())
                queue.append((child, depth + 1))
        except PermissionError:
            continue

    return matches
