"""Output abstraction — Logger protocol with Rich and plain implementations.

Follows the Dependency-Inversion Principle: callers depend on the
``Logger`` protocol, never on a concrete class.
"""

from __future__ import annotations

from typing import Protocol, Sequence

from port_claude_plugin.domain import ComponentPlan, PlanStatus


# ──────────────────────────────────────────────────────────────────────
# Protocol  (structural subtyping)
# ──────────────────────────────────────────────────────────────────────


class Logger(Protocol):
    """Presentation-layer abstraction used by every subsystem."""

    def info(self, msg: str) -> None: ...
    def ok(self, msg: str) -> None: ...
    def warn(self, msg: str) -> None: ...
    def err(self, msg: str) -> None: ...
    def header(self, title: str, subtitle: str | None = None) -> None: ...
    def render_plan(self, plans: Sequence[ComponentPlan]) -> None: ...
    def render_summary(self, done: int, skipped: int, failed: int) -> None: ...


# ──────────────────────────────────────────────────────────────────────
# Plain implementation
# ──────────────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────────────
# Rich implementation
# ──────────────────────────────────────────────────────────────────────

_STATUS_STYLE: dict[PlanStatus, str] = {
    PlanStatus.PENDING: "[cyan]PENDING[/]",
    PlanStatus.SKIP: "[yellow]SKIP[/]",
    PlanStatus.DONE: "[green]DONE[/]",
    PlanStatus.ERROR: "[red]ERROR[/]",
}


class RichLogger:
    """Pretty output powered by the ``rich`` library.

    Raises ``ImportError`` at construction time if Rich is missing,
    letting the factory fall back gracefully.
    """

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


# ──────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────


def create_logger() -> Logger:
    """Return ``RichLogger`` when Rich is importable, else ``PlainLogger``."""
    try:
        return RichLogger()
    except ImportError:
        return PlainLogger()
