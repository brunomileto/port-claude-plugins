"""Configuration loading and defaults.

Reads ``import_claude_plugin.toml`` from the current working directory (if present)
and merges it with built-in defaults.  CLI flags always win.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from port_claude_plugin.domain import ComponentKind


# ──────────────────────────────────────────────────────────────────────
# Typed config structures
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ComponentMapping:
    """Declarative description of one plugin component to install."""

    name: str
    src: str
    dst_template: str  # may contain ``{plugin_name}``
    kind: ComponentKind


@dataclass(frozen=True, slots=True)
class PortClaudePluginConfig:
    """Merged configuration used by every subsystem."""

    prog_name: str = "import_claude_plugin"
    search_root: str = "~/dev/claude-plugins"
    max_depth: int = 6
    default_mode: str = "copy"
    target_dir: str = ".opencode"
    plugin_markers: frozenset[str] = frozenset(
        {"skills", "commands", "agents", ".mcp.json"}
    )
    components: tuple[ComponentMapping, ...] = (
        ComponentMapping("skills", "skills", "skills/{plugin_name}", ComponentKind.DIR),
        ComponentMapping(
            "commands", "commands", "commands/{plugin_name}", ComponentKind.DIR
        ),
        ComponentMapping("agents", "agents", "agents/{plugin_name}", ComponentKind.DIR),
        ComponentMapping(
            "mcp", ".mcp.json", "mcp/{plugin_name}.mcp.json", ComponentKind.FILE
        ),
    )


# ──────────────────────────────────────────────────────────────────────
# TOML parsing helpers
# ──────────────────────────────────────────────────────────────────────

_CONFIG_FILENAME = "import_claude_plugin.toml"


def _parse_component(raw: dict[str, str]) -> ComponentMapping:
    """Convert a raw TOML ``[[import_claude_plugin.components]]`` entry."""
    return ComponentMapping(
        name=raw["name"],
        src=raw["src"],
        dst_template=raw["dst"],
        kind=ComponentKind(raw["kind"]),
    )


def load_config(config_dir: Path | None = None) -> PortClaudePluginConfig:
    """Load config from *config_dir* / ``import_claude_plugin.toml``, falling back to defaults.

    Parameters
    ----------
    config_dir:
        Directory to search for the TOML file.  Defaults to ``Path.cwd()``.
    """
    config_path = (config_dir or Path.cwd()) / _CONFIG_FILENAME

    if not config_path.is_file():
        return PortClaudePluginConfig()

    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    section = raw.get("import_claude_plugin", {})

    markers_raw = section.get("markers", {}).get("names")
    markers = (
        frozenset(markers_raw)
        if markers_raw is not None
        else PortClaudePluginConfig.plugin_markers
    )

    components_raw = section.get("components")
    components = (
        tuple(_parse_component(c) for c in components_raw)
        if components_raw is not None
        else PortClaudePluginConfig.components
    )

    return PortClaudePluginConfig(
        prog_name=section.get("prog_name", PortClaudePluginConfig.prog_name),
        search_root=section.get("search_root", PortClaudePluginConfig.search_root),
        max_depth=section.get("max_depth", PortClaudePluginConfig.max_depth),
        default_mode=section.get("default_mode", PortClaudePluginConfig.default_mode),
        target_dir=section.get("target_dir", PortClaudePluginConfig.target_dir),
        plugin_markers=markers,
        components=components,
    )
