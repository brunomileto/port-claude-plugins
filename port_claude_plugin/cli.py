"""CLI entry-point — argument parsing and orchestration.

This module is the **only** place that knows about ``argparse``.
It wires together config, discovery, planning, and logging.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from port_claude_plugin.config import load_config, PortClaudePluginConfig
from port_claude_plugin.discovery import find_plugin
from port_claude_plugin.domain import PlanStatus, TransferMode
from port_claude_plugin.logging import create_logger
from port_claude_plugin.planner import apply_plan, build_plan


def _build_parser(config: PortClaudePluginConfig) -> argparse.ArgumentParser:
    """Build the CLI parser, using *config* for default values."""
    parser = argparse.ArgumentParser(
        prog=config.prog_name,
        description=(
            "Port Claude-style knowledge-work plugin content "
            "into the current OpenCode project (.opencode/*)."
        ),
    )
    parser.add_argument(
        "plugin_name",
        help="Plugin folder name (e.g., product-management)",
    )
    parser.add_argument(
        "--root",
        default=config.search_root,
        help=f"Root folder to search under (default: {config.search_root})",
    )
    parser.add_argument(
        "--mode",
        choices=list(TransferMode),
        default=config.default_mode,
        help=f"copy = duplicate files; link = symlink into your project (default: {config.default_mode})",
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
        default=config.max_depth,
        help=f"Max folder depth to search under --root (default: {config.max_depth})",
    )
    return parser


def main() -> int:
    """CLI entry-point.  Returns an integer exit code."""
    config = load_config()
    parser = _build_parser(config)
    args = parser.parse_args()

    log = create_logger()
    plugin_name: str = args.plugin_name.strip()
    root = Path(args.root).expanduser()
    project_root = Path.cwd()
    transfer_mode = TransferMode(args.mode)

    log.header(
        config.prog_name,
        f"plugin={plugin_name} • project={project_root} • search_root={root}",
    )

    # ── Discover plugin ──────────────────────────────────────────────
    log.info("Searching for plugin folder…")
    matches = find_plugin(
        plugin_name,
        root,
        max_depth=args.max_depth,
        markers=config.plugin_markers,
    )

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
    plans = build_plan(
        plugin_dir,
        plugin_name,
        project_root,
        mode=transfer_mode,
        config=config,
    )
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
