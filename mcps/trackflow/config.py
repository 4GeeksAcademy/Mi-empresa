"""Explicit environment configuration; no environment files are read implicitly."""

import os
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.api.service_urls import validate_url


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRACKFLOW_MCP_", extra="ignore")

    issuer: str = Field(min_length=1)
    resource_url: str = Field(min_length=1)
    backend_url: str = "http://localhost:8000"
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    allowed_origins: list[str] = Field(default_factory=list)

    @classmethod
    def from_environment(cls) -> Self:
        return cls(
            issuer=os.environ.get("TRACKFLOW_MCP_ISSUER", ""),
            resource_url=os.environ.get("TRACKFLOW_MCP_RESOURCE_URL", ""),
        )

    @field_validator("issuer", "resource_url", "backend_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        return validate_url(value)

    @field_validator("resource_url")
    @classmethod
    def mcp_path(cls, value: str) -> str:
        if urlsplit(value).path != "/mcp":
            raise ValueError("Resource URL must end in /mcp (without a trailing slash).")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def valid_origins(cls, values: list[str]) -> list[str]:
        for value in values:
            validate_url(value)
            if urlsplit(value).path:
                raise ValueError("Allowed origins must contain only scheme and authority, without a path.")
        return values
