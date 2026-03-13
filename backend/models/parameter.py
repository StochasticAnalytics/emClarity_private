"""Pydantic models for emClarity parameter handling.

Parameters control every aspect of the cryo-EM processing pipeline.
Each parameter has a definition (schema) and a concrete value when used
in a parameter file.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    """Supported parameter value types.

    The golden schema (from BH_parseParameterFile.m) uses: numeric,
    numeric_array, string, boolean.  Legacy backend code also references
    integer, float, vector, and enum; those are kept for backward
    compatibility with existing backend tests.
    """

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    VECTOR = "vector"  # e.g., [1, 2, 3] - common in cryo-EM for 3D dimensions
    ENUM = "enum"  # constrained string choice
    NUMERIC = "numeric"  # golden schema numeric type
    NUMERIC_ARRAY = "numeric_array"  # golden schema array type


class ParameterCategory(str, Enum):
    """Logical groupings for parameters in the UI.

    The golden schema uses: alignment, classification, ctf,
    disk_management, dose, fsc, hardware, masking, metadata, microscope,
    template_matching, tomoCPR.  Legacy values (general, reconstruction,
    templateSearch, tomogram, system) are kept for backward compatibility.
    """

    GENERAL = "general"
    ALIGNMENT = "alignment"
    CTF = "ctf"
    RECONSTRUCTION = "reconstruction"
    MASKING = "masking"
    CLASSIFICATION = "classification"
    TEMPLATE_SEARCH = "templateSearch"
    TOMOGRAM = "tomogram"
    SYSTEM = "system"
    MICROSCOPE = "microscope"
    HARDWARE = "hardware"
    METADATA = "metadata"
    DISK_MANAGEMENT = "disk_management"
    DOSE = "dose"
    FSC = "fsc"
    TEMPLATE_MATCHING = "template_matching"
    TOMOCPR = "tomoCPR"


class ParameterDefinition(BaseModel):
    """Schema definition for a single emClarity parameter.

    Describes the name, type, constraints, and documentation for a
    parameter. Used by the frontend to render appropriate input widgets
    and perform client-side validation.
    """

    name: str = Field(..., description="Parameter name as used in the .m parameter file")
    type: ParameterType = Field(..., description="Value type for validation and UI rendering")
    required: bool = Field(default=False, description="Whether the parameter must be set")
    default: Any = Field(default=None, description="Default value if not explicitly set")
    range: list[float] | None = Field(
        default=None,
        description="[min, max] range for numeric parameters",
    )
    allowed_values: list[Any] | None = Field(
        default=None,
        description="Allowed values for enum-type parameters",
    )
    description: str = Field(default="", description="Human-readable description")
    category: ParameterCategory = Field(
        default=ParameterCategory.GENERAL,
        description="UI grouping category",
    )
    units: str | None = Field(default=None, description="Physical units (e.g., angstroms, degrees)")


class ParameterSchemaResponse(BaseModel):
    """API response wrapper for the parameter schema.

    The ``/api/v1/parameters/schema`` endpoint returns this object so
    that the frontend receives a JSON object ``{"parameters": [...]}``
    rather than a bare array.
    """

    parameters: list[ParameterDefinition] = Field(
        ...,
        description="List of parameter definitions from the golden schema",
    )


class ParameterValue(BaseModel):
    """A concrete parameter name-value pair."""

    name: str = Field(..., description="Parameter name")
    value: Any = Field(..., description="Parameter value")


class ParameterFile(BaseModel):
    """Represents a complete emClarity parameter file.

    Contains all parameter values and the filesystem path where the
    file is (or will be) stored.
    """

    parameters: list[ParameterValue] = Field(
        default_factory=list,
        description="List of parameter name-value pairs",
    )
    path: str = Field(..., description="Filesystem path to the parameter file")


class ParameterValidationResult(BaseModel):
    """Result of validating a set of parameter values against the schema."""

    valid: bool = Field(..., description="Whether all parameters passed validation")
    errors: list[str] = Field(
        default_factory=list,
        description="List of validation error messages",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of non-fatal validation warnings",
    )
