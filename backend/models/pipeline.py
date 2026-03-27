"""Pydantic models for the pipeline registry.

The pipeline registry (registry.yaml) tracks work items through stages
from idea to completion. These models define the data shapes for CRUD
operations and enriched read-time views.

Schema reference: dot-claude/.claude/pipeline/SCHEMA.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.models.base import CamelCaseModel

# ---------------------------------------------------------------------------
# Literal types — values must match SCHEMA.md exactly
# ---------------------------------------------------------------------------

PipelineStage = Literal[
    "idea",
    "research",
    "plan",
    "prd",
    "queued",
    "running",
    "done",
]

PlanSubStatus = Literal[
    "draft",
    "reviewed",
    "accepted",
    "needs-prd",
]

PipelinePriority = Literal[
    "critical",
    "high",
    "medium",
    "low",
    "someday",
]

# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class PipelineOrigin(CamelCaseModel):
    """Where this work item originated."""

    type: Literal["idea", "research", "external", "conversation"]
    path: str | None = Field(
        default=None,
        description="Relative path to the origin file (relative to dot-claude/.claude/)",
    )


class PipelineLink(CamelCaseModel):
    """Cross-reference between work items."""

    id: str = Field(..., description="Target work item ID (e.g. WI-NNN)")
    relation: str = Field(
        ...,
        description="Relationship type (e.g. depends-on, supersedes, promoted-from)",
    )


# ---------------------------------------------------------------------------
# Core registry model
# ---------------------------------------------------------------------------


class PipelineItem(CamelCaseModel):
    """A single entry in the pipeline registry."""

    id: str = Field(..., description="Unique identifier (e.g. WI-001)")
    title: str = Field(..., description="Short description of the work item")
    stage: PipelineStage = Field(..., description="Current pipeline stage")
    sub_status: PlanSubStatus | None = Field(
        default=None,
        description="Stage-specific refinement (currently used for plan stage)",
    )
    priority: PipelinePriority = Field(..., description="Item priority level")
    origin: PipelineOrigin | None = Field(
        default=None,
        description="Where this item started",
    )
    plan_path: str | None = Field(
        default=None,
        description="Path to plan file (relative to dot-claude/.claude/)",
    )
    prd_path: str | None = Field(
        default=None,
        description="Path to PRD file (relative to autonomous-build/)",
    )
    run_command: str | None = Field(
        default=None,
        description="Command to execute this item",
    )
    links: list[PipelineLink] = Field(
        default_factory=list,
        description="Cross-references to other work items",
    )
    created: str = Field(..., description="ISO date when the item was created")
    updated: str = Field(..., description="ISO date when the item was last updated")
    notes: str | None = Field(
        default=None,
        description="Free-form context",
    )


# ---------------------------------------------------------------------------
# PRD task summary (for enriched view)
# ---------------------------------------------------------------------------


class PrdTaskSummary(CamelCaseModel):
    """Aggregated task counts from a PRD JSON file."""

    total: int = Field(..., description="Total number of tasks in the PRD")
    completed: int = Field(..., description="Tasks with status 'done'")
    pending: int = Field(..., description="Tasks not yet started")
    blocked: int = Field(..., description="Tasks that are blocked")


# ---------------------------------------------------------------------------
# Enriched model (read-time computed fields)
# ---------------------------------------------------------------------------


class PipelineItemEnriched(PipelineItem):
    """PipelineItem with computed fields added at read time.

    The backend enriches registry entries by comparing the ``updated``
    field against file mtimes and reading PRD task statuses.
    """

    is_stale: bool = Field(
        default=False,
        description="True when the referenced file has been modified since 'updated'",
    )
    file_mtime: str | None = Field(
        default=None,
        description="ISO datetime of the most recently referenced file's mtime",
    )
    prd_task_summary: PrdTaskSummary | None = Field(
        default=None,
        description="Aggregated task counts from the PRD (if stage is prd/queued/running/done)",
    )


# ---------------------------------------------------------------------------
# Request models (create / update)
# ---------------------------------------------------------------------------


class CreatePipelineItemRequest(CamelCaseModel):
    """Request body for creating a new pipeline item.

    ``id``, ``created``, and ``updated`` are set server-side.
    """

    title: str = Field(..., description="Short description of the work item")
    stage: PipelineStage = Field(..., description="Initial pipeline stage")
    sub_status: PlanSubStatus | None = Field(default=None)
    priority: PipelinePriority = Field(..., description="Item priority level")
    origin: PipelineOrigin | None = Field(default=None)
    plan_path: str | None = Field(default=None)
    prd_path: str | None = Field(default=None)
    run_command: str | None = Field(default=None)
    links: list[PipelineLink] = Field(default_factory=list)
    notes: str | None = Field(default=None)


class UpdatePipelineItemRequest(CamelCaseModel):
    """Request body for PATCH-updating a pipeline item.

    All fields are optional — only provided fields are applied.
    """

    title: str | None = Field(default=None)
    stage: PipelineStage | None = Field(default=None)
    sub_status: PlanSubStatus | None = Field(default=None)
    priority: PipelinePriority | None = Field(default=None)
    origin: PipelineOrigin | None = Field(default=None)
    plan_path: str | None = Field(default=None)
    prd_path: str | None = Field(default=None)
    run_command: str | None = Field(default=None)
    links: list[PipelineLink] | None = Field(default=None)
    notes: str | None = Field(default=None)
