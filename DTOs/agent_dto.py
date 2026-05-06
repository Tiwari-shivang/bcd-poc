from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    data_source: Optional[str] = Field(
        default=None,
        description='Pin catalogue + execution DB: salesforce/sf/oip.',
    )

    @field_validator("data_source", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v.strip()

    @field_validator("data_source")
    @classmethod
    def _normalize_source(cls, v: str | None) -> str | None:
        from helpers import datasource as ds

        if v is None:
            return None
        normalized = ds.normalize_source(v)
        if normalized is None:
            raise ValueError(
                'data_source must be "salesforce", "sf", or "oip" if provided.'
            )
        return normalized


class AgentChatResponse(BaseModel):
    response: Any
    needs_database_choice: bool = False
    resolved_data_source: Optional[str] = None
    error: Optional[str] = None

    class Config:
        from_attributes = True
