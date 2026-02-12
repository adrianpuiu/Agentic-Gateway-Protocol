"""
Config loading and saving.
"""

import json
from pathlib import Path
from agp.config.schema import Config


DEFAULT_CONFIG_PATH = Path("~/.agp/config.json").expanduser()


def load_config(path: Path | None = None) -> Config:
    """
    Load configuration from JSON file.

    Args:
        path: Config file path. Defaults to ~/.agp/config.json

    Returns:
        Validated Config object.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH

    if not path.exists():
        # Return default config
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        # Assume camelCase from file (common for JSON config)
        # Pydantic will handle field mapping
        data = json.load(f)

    return Config(**data)


def save_config(config: Config, path: Path | None = None) -> None:
    """
    Save configuration to JSON file.

    Args:
        config: Config object to save
        path: Config file path. Defaults to ~/.agp/config.json
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(mode="json"), f, indent=2)
