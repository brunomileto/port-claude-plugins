"""Plan building and execution.

``build_plan`` turns the declarative component mappings from config into
a list of ``ComponentPlan`` entries.  ``apply_plan`` executes them,
delegating actual I/O to :mod:`import_claude_plugin.filesystem`.
"""

from __future__ import annotations

from pathlib import Path

from port_claude_plugin.config import PortClaudePluginConfig
from port_claude_plugin.domain import (
    ComponentPlan,
    PlanStatus,
    TransferMode,
)
from port_claude_plugin.filesystem import transfer
from port_claude_plugin.logging import Logger


def build_plan(
    plugin_dir: Path,
    plugin_name: str,
    project_root: Path,
    *,
    mode: TransferMode,
    config: PortClaudePluginConfig,
) -> list[ComponentPlan]:
    """Create a ``ComponentPlan`` for every mapping defined in *config*.

    Parameters
    ----------
    plugin_dir:
        Resolved path to the discovered plugin directory.
    plugin_name:
        Human name of the plugin (used in destination templates).
    project_root:
        The project root where ``.opencode/`` lives.
    mode:
        ``copy`` or ``link``.
    config:
        Loaded configuration (carries ``target_dir`` and ``components``).
    """
    target_root = project_root / config.target_dir
    plans: list[ComponentPlan] = []

    for mapping in config.components:
        src = plugin_dir / mapping.src
        dst = target_root / mapping.dst_template.format(plugin_name=plugin_name)

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
                    detail=f"missing {mapping.src}; skipped",
                )
            )

    return plans


def apply_plan(
    plans: list[ComponentPlan],
    *,
    force: bool,
    dry_run: bool,
    log: Logger,
) -> None:
    """Execute each pending ``ComponentPlan`` entry.

    Skipped entries are logged.  Dry-run entries are marked as done
    without touching the filesystem.  Errors are captured per-entry
    so that one failure doesn't abort the rest.
    """
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
            success, detail = transfer(plan, force=force)
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
