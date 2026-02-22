"""Domain types — enums and value objects.

This module contains **zero logic**; it exists solely to define the
shared vocabulary used by every other module in the package.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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
