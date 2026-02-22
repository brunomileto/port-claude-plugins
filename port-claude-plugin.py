#!/usr/bin/env python3
"""Port Claude-style knowledge-work plugin content into an OpenCode project.

Scans a search root for a named plugin directory, then copies or symlinks
its skills, commands, agents, and MCP configuration into the current
project's `.opencode/` tree.
"""

from __future__ import annotations

import argparse
import shutil
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence

# ──────────────────────────────────────────────────────────────────────
# Domain enums — eliminate stringly-typed fields
# ──────────────────────────────────────────────────────────────────────


class ComponentKind(StrEnum):
    """Whether the component is a directory tree or a single file."""

    DIR = "dir"
    FILE = "file"


class TransferMode(StrEnum):
    """How a component is installed into the project."""

    COPY = "copy"
    LINK = "link"


class PlanStatus(StrEnum):
    """Lifecycle status of a single component plan entry."""

    PENDING = "pending"
    SKIP = "skip"
    DONE = "done"
    ERROR = "error"


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ComponentPlan:
    """One unit of work: copy/link a single component from plugin → project."""

    name: str
    src: Path
    dst: Path
    kind: ComponentKind
    mode: TransferMode
    status: PlanStatus = PlanStatus.PENDING
    detail: str = ""


# ──────────────────────────────────────────────────────────────────────
# Logger Protocol + implementations  (SRP · OCP · DIP)
# ──────────────────────────────────────────────────────────────────────


class Logger(Protocol):
    """Abstraction over presentation output."""

    def info(self, msg: str) -> None: ...
    def ok(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def err(self, msg: str) -> None: ...
    def header(self, title: str, subtitle: str | None = None) -> None: ...
    def render_plan(self, plans: Sequence[ComponentPlan]) -> None: ...
    def render_summary(self, done: int, skipped: int, failed: int) -> None: ...


class PlainLogger:
    """Fallback logger — pure ``print()``."""

    def info(self, msg: str) -> None:
        print(f"[INFO] {msg}")

    def ok(self, msg: str) -> None:
        print(f"[OK] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[WARN] {msg}")

    def err(self, msg: str) -> None:
        print(f"[ERROR] {msg}")

    def header(self, title: str, subtitle: str | None = None) -> None:
        print("=" * 60)
        print(title)
        if subtitle:
            print(subtitle)
        print("=" * 60)

    def render_plan(self, plans: Sequence[ComponentPlan]) -> None:
        print("Plan:")
        for p in plans:
            print(f" - {p.name}: {p.src} -> {p.dst} ({p.mode}) [{p.status}] {p.detail}")

    def render_summary(self, done: int, skipped: int, failed: int) -> None:
        print(f"Summary: done={done}, skipped={skipped}, failed={failed}")


class RichLogger:
    """Pretty output via Rich."""

    def __init__(self) -> None:
        from rich.console import Console  # noqa: PLC0415

        self._console = Console()

    def info(self, msg: str) -> None:
        self._console.print(f"[bold cyan]ℹ[/] {msg}")

    def ok(self, msg: str) -> None:
        self._console.print(f"[bold green]✔[/] {msg}")

    def warn(self, msg: str) -> None:
        self._console.print(f"[bold yellow]▲[/] {msg}")

    def err(self, msg: str) -> None:
        self._console.print(f"[bold red]✖[/] {msg}")

    def header(self, title: str, subtitle: str | None = None) -> None:
        from rich import box  # noqa: PLC0415
        from rich.panel import Panel  # noqa: PLC0415
        from rich.text import Text  # noqa: PLC0415

        title_text = Text(title, style="bold white")
        body = (
            Text.assemble(title_text, "\n", Text(subtitle, style="dim"))
            if subtitle
            else title_text
        )
        self._console.print(Panel.fit(body, box=box.DOUBLE))

    def render_plan(self, plans: Sequence[ComponentPlan]) -> None:
        from rich import box  # noqa: PLC0415
        from rich.table import Table  # noqa: PLC0415

        _STATUS_STYLE: dict[PlanStatus, str] = {
            PlanStatus.PENDING: "[cyan]PENDING[/]",
            PlanStatus.SKIP: "[yellow]SKIP[/]",
            PlanStatus.DONE: "[green]DONE[/]",
            PlanStatus.ERROR: "[red]ERROR[/]",
        }

        table = Table(title="Plan", box=box.ROUNDED, show_lines=False)
        table.add_column("Component", style="bold")
        table.add_column("Source", overflow="fold")
        table.add_column("Destination", overflow="fold")
        table.add_column("Mode", justify="center")
        table.add_column("Status", justify="center")

        for p in plans:
            table.add_row(
                p.name,
                str(p.src),
                str(p.dst),
                p.mode.value.upper(),
                _STATUS_STYLE.get(p.status, "[red]ERROR[/]"),
            )
        self._console.print(table)

    def render_summary(self, done: int, skipped: int, failed: int) -> None:
        from rich import box  # noqa: PLC0415
        from rich.table import Table  # noqa: PLC0415

        summary = Table(title="Summary", box=box.SIMPLE_HEAVY)
        summary.add_column("Done", justify="right", style="green")
        summary.add_column("Skipped", justify="right", style="yellow")
        summary.add_column("Failed", justify="right", style="red")
        summary.add_row(str(done), str(skipped), str(failed))
        self._console.print(summary)


def create_logger() -> Logger:
    """Factory: return RichLogger if Rich is available, else PlainLogger."""
    try:
        return RichLogger()
    except ImportError:
        return PlainLogger()


# ──────────────────────────────────────────────────────────────────────
# Plugin discovery  (iterative BFS — no mutable closure)
# ──────────────────────────────────────────────────────────────────────

_PLUGIN_MARKERS = frozenset({"skills", "commands", "agents", ".mcp.json"})


def _is_probable_plugin_dir(path: Path) -> bool:
    """A probable plugin has at least one known marker child."""
    return path.is_dir() and any((path / m).exists() for m in _PLUGIN_MARKERS)


def find_plugin(plugin_name: str, root: Path, *, max_depth: int = 6) -> list[Path]:
    """BFS for directories named *plugin_name* under *root*, bounded by depth."""
    root = root.expanduser().resolve()
    if not root.exists():
        return []

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
                if child.name == plugin_name and _is_probable_plugin_dir(child):
                    matches.append(child.resolve())
                queue.append((child, depth + 1))
        except PermissionError:
            continue

    return matches


# ──────────────────────────────────────────────────────────────────────
# File-system helpers
# ──────────────────────────────────────────────────────────────────────


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _remove_existing(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _safe_copy_dir(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if dst.exists() and not force:
        return False, "destination exists (use --force to overwrite)"
    if dst.exists():
        _remove_existing(dst)
    _ensure_parent(dst)
    shutil.copytree(src, dst)
    return True, "copied"


def _safe_copy_file(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if dst.exists() and not force:
        return False, "destination exists (use --force to overwrite)"
    if dst.exists():
        _remove_existing(dst)
    _ensure_parent(dst)
    shutil.copy2(src, dst)
    return True, "copied"


def _safe_link(src: Path, dst: Path, *, force: bool) -> tuple[bool, str]:
    if (dst.exists() or dst.is_symlink()) and not force:
        return False, "destination exists (use --force to overwrite)"
    if dst.exists() or dst.is_symlink():
        _remove_existing(dst)
    _ensure_parent(dst)
    dst.symlink_to(src, target_is_directory=src.is_dir())
    return True, "linked"


# Strategy dispatch: (TransferMode, ComponentKind) → handler
_TRANSFER_DISPATCH: dict[
    tuple[TransferMode, ComponentKind],
    type[object],  # placeholder — real callable signature below
] = {}  # populated after function definitions


def _transfer(plan: ComponentPlan, *, force: bool) -> tuple[bool, str]:
    """Execute the copy/link for a single component plan."""
    handlers: dict[
        tuple[TransferMode, ComponentKind],
        object,
    ] = {
        (TransferMode.COPY, ComponentKind.DIR): _safe_copy_dir,
        (TransferMode.COPY, ComponentKind.FILE): _safe_copy_file,
        (TransferMode.LINK, ComponentKind.DIR): _safe_link,
        (TransferMode.LINK, ComponentKind.FILE): _safe_link,
    }
    handler = handlers[(plan.mode, plan.kind)]
    return handler(plan.src, plan.dst, force=force)  # type: ignore[operator]


# ──────────────────────────────────────────────────────────────────────
# Plan building  (declarative mapping — DRY)
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _ComponentMapping:
    """Declarative description of one component to install."""

    name: str
    relative_src: str
    relative_dst_template: str  # uses {plugin_name}
    kind: ComponentKind


_COMPONENT_MAPPINGS: tuple[_ComponentMapping, ...] = (
    _ComponentMapping("skills", "skills", "skills/{plugin_name}", ComponentKind.DIR),
    _ComponentMapping(
        "commands", "commands", "commands/{plugin_name}", ComponentKind.DIR
    ),
    _ComponentMapping("agents", "agents", "agents/{plugin_name}", ComponentKind.DIR),
    _ComponentMapping(
        "mcp", ".mcp.json", "mcp/{plugin_name}.mcp.json", ComponentKind.FILE
    ),
)


def build_plan(
    plugin_dir: Path,
    plugin_name: str,
    project_root: Path,
    mode: TransferMode,
) -> list[ComponentPlan]:
    """Create a component plan for every known mapping."""
    opencode_root = project_root / ".opencode"
    plans: list[ComponentPlan] = []

    for mapping in _COMPONENT_MAPPINGS:
        src = plugin_dir / mapping.relative_src
        dst = opencode_root / mapping.relative_dst_template.format(
            plugin_name=plugin_name
        )

        if src.exists():
            plans.append(
                ComponentPlan(
                    name=mapping.name,
                    src=src,
                    dst=dst,
                    kind=mapping.kind,
                    mode=mode,
                )
            )
        else:
            plans.append(
                ComponentPlan(
                    name=mapping.name,
                    src=src,
                    dst=dst,
                    kind=mapping.kind,
                    mode=mode,
                    status=PlanStatus.SKIP,
                    detail=f"missing {mapping.relative_src}; skipped",
                )
            )

    return plans


# ──────────────────────────────────────────────────────────────────────
# Plan execution
# ──────────────────────────────────────────────────────────────────────


def apply_plan(
    plans: list[ComponentPlan],
    *,
    force: bool,
    dry_run: bool,
    log: Logger,
) -> None:
    """Execute each pending component plan entry."""
    for plan in plans:
        if plan.status is PlanStatus.SKIP:
            log.warn(f"{plan.name}: {plan.detail}")
            continue

        if dry_run:
            log.info(f"{plan.name}: would {plan.mode} {plan.kind} → {plan.dst}")
            plan.status = PlanStatus.DONE
            plan.detail = "dry-run"
            continue

        try:
            success, detail = _transfer(plan, force=force)
        except Exception as exc:
            plan.status = PlanStatus.ERROR
            plan.detail = str(exc)
            log.err(f"{plan.name}: failed ({exc})")
            continue

        if success:
            plan.status = PlanStatus.DONE
            plan.detail = detail
            log.ok(f"{plan.name}: {detail} → {plan.dst}")
        else:
            plan.status = PlanStatus.SKIP
            plan.detail = detail
            log.warn(f"{plan.name}: {detail}")


# ──────────────────────────────────────────────────────────────────────
# CLI entry-point
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="Port Claude Plugin",
        description=(
            "Port Claude Code plugins content "
            "into the current OpenCode project (.opencode/*)."
        ),
    )
    parser.add_argument(
        "plugin_name",
        help="Plugin folder name (e.g., product-management)",
    )
    parser.add_argument(
        "--root",
        default="~/dev/claude-plugins",
        help="Root folder to search under (default: ~/dev/claude-plugins)",
    )
    parser.add_argument(
        "--mode",
        choices=list(TransferMode),
        default=TransferMode.COPY.value,
        help="copy = duplicate files; link = symlink into your project (default: copy)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing destinations under .opencode/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without changing anything",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=6,
        help="Max folder depth to search under --root (default: 6)",
    )
    return parser


def main() -> int:
    """CLI entry-point. Returns an integer exit code."""
    parser = _build_parser()
    args = parser.parse_args()

    log = create_logger()
    plugin_name: str = args.plugin_name.strip()
    root = Path(args.root).expanduser()
    project_root = Path.cwd()
    transfer_mode = TransferMode(args.mode)

    log.header(
        "Port Claude Plugin",
        f"plugin={plugin_name} • project={project_root} • search_root={root}",
    )

    # ── Discover plugin ──────────────────────────────────────────────
    log.info("Searching for plugin folder…")
    matches = find_plugin(plugin_name, root, max_depth=args.max_depth)

    if not matches:
        log.err(f"No plugin folder named '{plugin_name}' found under {root}.")
        log.warn("Tip: check your spelling, or increase --max-depth.")
        return 2

    if len(matches) > 1:
        log.err(f"Found multiple matches for '{plugin_name}':")
        for match in matches:
            log.warn(str(match))
        log.err(
            "Make your tree less ambiguous (or temporarily move/rename duplicates)."
        )
        return 3

    plugin_dir = matches[0]
    log.ok(f"Found plugin: {plugin_dir}")

    # ── Build & show plan ────────────────────────────────────────────
    plans = build_plan(plugin_dir, plugin_name, project_root, mode=transfer_mode)
    log.render_plan(plans)

    # ── Execute ──────────────────────────────────────────────────────
    log.info("Applying plan…")
    apply_plan(plans, force=args.force, dry_run=args.dry_run, log=log)

    # ── Summary ──────────────────────────────────────────────────────
    done = sum(1 for p in plans if p.status is PlanStatus.DONE)
    skipped = sum(1 for p in plans if p.status is PlanStatus.SKIP)
    failed = sum(1 for p in plans if p.status is PlanStatus.ERROR)

    log.render_summary(done, skipped, failed)

    if failed:
        return 4

    log.ok(
        "All set. If you copied an MCP file, you still need to "
        "wire it into your OpenCode MCP config if required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
