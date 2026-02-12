"""
Configuration schema using Pydantic v2.
"""

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pathlib import Path


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    """
    Custom LLM provider configuration.

    Set these to route the Claude CLI through a compatible API proxy
    (e.g., z.ai, OpenRouter, LiteLLM).
    """

    base_url: str = ""  # ANTHROPIC_BASE_URL
    auth_token: str = ""  # ANTHROPIC_AUTH_TOKEN
    model_override: str = ""  # Override all model slots


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    type: Literal["stdio", "sse"] = "stdio"
    # stdio options
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # sse options
    url: str | None = None


class ChannelConfigs(BaseModel):
    """All channel configurations."""

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    # Add more channels as needed: discord, slack, etc.


class Config(BaseSettings):
    """
    Root configuration.

    Loads from ~/.agp/config.json and environment variables
    with AGP_ prefix.
    """

    workspace: Path = Field(default=Path("~/.agp/workspace"))
    model: str = "sonnet"
    env: dict[str, str] = Field(default_factory=dict)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    channels: ChannelConfigs = Field(default_factory=ChannelConfigs)

    model_config = SettingsConfigDict(
        env_prefix="AGP_",
        env_nested_delimiter="__",
    )

    @field_validator("workspace")
    @classmethod
    def expand_workspace(cls, v: str) -> Path:
        """Expand ~ in workspace path."""
        return Path(v).expanduser().resolve()
