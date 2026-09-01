"""Configuration loaded from .env file and environment variables.

All API keys and user-configurable settings are read from environment, with
sensible defaults. The .env file (gitignored) is the primary configuration
mechanism; environment variables override .env entries.

Usage:
    from src.config import get_config
    cfg = get_config()
    print(cfg.model_provider)     # "deepseek" (default)
    print(cfg.deepseek_api_key)   # "sk-xxxx"
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

# Load .env from project root (one directory above src/)
_project_root = Path(__file__).resolve().parent.parent
_dotenv_path = _project_root / ".env"
load_dotenv(_dotenv_path, override=False)

ModelProvider = Literal["deepseek", "openai", "claude", "glm"]
ReasoningEffort = Literal["low", "medium", "high", "max"]


@dataclass
class Config:
    """Agent configuration loaded from environment.

    All fields are populated from environment variables or sensible defaults.
    API keys default to empty string — the agent validates availability at
    startup and gives a clear error if the configured provider's key is missing.
    """

    # --- Model selection ---
    model_provider: str = field(
        default_factory=lambda: os.getenv("MODEL_PROVIDER", "deepseek")
    )
    agent_model: str = field(
        default_factory=lambda: os.getenv("AGENT_MODEL", "deepseek-v4-pro")
    )

    # --- API keys ---
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    claude_api_key: str = field(
        default_factory=lambda: os.getenv("CLAUDE_API_KEY", "")
    )
    glm_api_key: str = field(
        default_factory=lambda: os.getenv("GLM_API_KEY", "")
    )

    # --- Inference ---
    reasoning_effort: str = field(
        default_factory=lambda: os.getenv("REASONING_EFFORT", "high")
    )

    # --- SageMath ---
    sagemath_cmd: str = field(
        default_factory=lambda: os.getenv("SAGEMATH_CMD", "sage")
    )
    sagemath_timeout: int = field(
        default_factory=lambda: int(os.getenv("SAGEMATH_TIMEOUT", "120"))
    )

    sagemath_use_wsl: bool = field(
        default_factory=lambda: os.getenv("SAGEMATH_USE_WSL", "true").lower() == "true"
    )

    # --- Knowledge base (ChromaDB + math-embed) ---
    chroma_persist_dir: str = field(
        default_factory=lambda: os.getenv(
            "CHROMA_PERSIST_DIR", str(_project_root / "data" / "chroma_agent")
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "RobBobin/math-embed")
    )
    embedding_device: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_DEVICE", "cuda")
    )

    # --- Paths ---
    project_root: Path = _project_root
    data_dir: Path = field(
        default_factory=lambda: _project_root / "data"
    )
    logs_dir: Path = field(
        default_factory=lambda: _project_root / ".logs"
    )

    def validate(self) -> list[str]:
        """Check required configuration is present.

        Returns a list of human-readable error messages (empty = all good).
        """
        errors: list[str] = []
        provider = self.model_provider
        key_map = {
            "deepseek": self.deepseek_api_key,
            "openai": self.openai_api_key,
            "claude": self.claude_api_key,
            "glm": self.glm_api_key,
        }
        if provider not in key_map:
            errors.append(
                f"Unknown MODEL_PROVIDER '{provider}'. "
                f"Must be one of: {', '.join(sorted(key_map))}"
            )
        elif not key_map[provider]:
            env_var = f"{provider.upper()}_API_KEY"
            errors.append(
                f"API key not set for provider '{provider}'. "
                f"Set {env_var} in .env or environment."
            )
        return errors

    def get_api_key(self, provider: Optional[str] = None) -> str:
        """Get the API key for a specific provider, or the active one."""
        p = provider or self.model_provider
        key_map = {
            "deepseek": self.deepseek_api_key,
            "openai": self.openai_api_key,
            "claude": self.claude_api_key,
            "glm": self.glm_api_key,
        }
        return key_map.get(p, "")


# Global singleton — use get_config() to ensure .env is loaded.
_config: Optional[Config] = None


def get_config() -> Config:
    """Return the global Config, loading .env on first call."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Reset the cached config (useful in tests)."""
    global _config
    _config = None
