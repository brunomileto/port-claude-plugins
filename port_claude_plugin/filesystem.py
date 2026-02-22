"""File-system transfer helpers — copy, symlink, and cleanup.

All public helpers return ``(success: bool, detail: str)`` to keep
side-effects and reporting cleanly separated.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from port_claude_plugin.domain import ComponentKind, ComponentPlan, TransferMode


# ──────────────────────────────────────────────────────────────────────
# Low-level helpers
# ──────────────────────────────────────────────────────────────────────


def _ensure_parent(path: Path) -> None:
    """Create all parent directories of *path* if they don't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _remove_existing(path: Path) -> None:
    """Remove *path* whether it is a file, symlink, or directory tree."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


# ──────────────────────────────────────────────────────────────────────
# Safe transfer functions
# ──────────────────────────────────────────────────────────────────────

_EXISTS_MSG = "destination exists (use --force to overwrite)"


def _safe_copy_dir(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if dst.exists() and not force:
        return False, _EXISTS_MSG
    if dst.exists():
        _remove_existing(dst)
    _ensure_parent(dst)
    shutil.copytree(src, dst)
    return True, "copied"


def _safe_copy_file(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if dst.exists() and not force:
        return False, _EXISTS_MSG
    if dst.exists():
        _remove_existing(dst)
    _ensure_parent(dst)
    shutil.copy2(src, dst)
    return True, "copied"


def _safe_link(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if (dst.exists() or dst.is_symlink()) and not force:
        return False, _EXISTS_MSG
    if dst.exists() or dst.is_symlink():
        _remove_existing(dst)
    _ensure_parent(dst)
    dst.symlink_to(src, target_is_directory=src.is_dir())
    return True, "linked"


# ──────────────────────────────────────────────────────────────────────
# Strategy dispatch
# ──────────────────────────────────────────────────────────────────────

type _TransferFn = type[object]  # callable signature shorthand for dispatch

_DISPATCH: dict[
    tuple[TransferMode, ComponentKind],
    _TransferFn,
] = {
    (TransferMode.COPY, ComponentKind.DIR): _safe_copy_dir,  # type: ignore[dict-item]
    (TransferMode.COPY, ComponentKind.FILE): _safe_copy_file,  # type: ignore[dict-item]
    (TransferMode.LINK, ComponentKind.DIR): _safe_link,  # type: ignore[dict-item]
    (TransferMode.LINK, ComponentKind.FILE): _safe_link,  # type: ignore[dict-item]
}


def transfer(plan: ComponentPlan, *, force: bool) -> tuple[bool, str]:
    """Execute the file-system operation described by *plan*.

    Returns ``(success, human_detail)`` — never raises for expected
    filesystem conditions (those are captured in the detail string).
    """
    handler = _DISPATCH[(plan.mode, plan.kind)]
    return handler(plan.src, plan.dst, force=force)  # type: ignore[operator]
