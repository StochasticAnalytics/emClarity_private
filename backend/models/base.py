"""Base model with camelCase JSON serialization.

Provides a common base for models that need snake_case Python attributes
but camelCase JSON output — the standard convention when a Python backend
serves a JavaScript/TypeScript frontend.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelCaseModel(BaseModel):
    """BaseModel subclass that serializes field names to camelCase.

    Python code uses snake_case attributes; JSON output uses camelCase.
    ``populate_by_name=True`` allows construction from either form.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
