from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MODEL = "openai:gpt-4o-mini"


def load_runtime_config(env_path: str | Path = ".env") -> None:
    load_dotenv(env_path)
    # 对于 OpenAI 兼容提供商，复制通用 API_KEY/BASE_URL 到对应环境变量
    # 这样用户只需要写 API_KEY 就能用，不用区分是哪个 provider
    openai_compatible_providers = ["OPENAI", "OPENROUTER", "DEEPSEEK", "PERPLEXITY", "TOGETHER"]
    for provider in openai_compatible_providers:
        if not os.getenv(f"{provider}_API_KEY") and os.getenv("API_KEY"):
            os.environ[f"{provider}_API_KEY"] = os.getenv("API_KEY", "")
        if not os.getenv(f"{provider}_BASE_URL") and os.getenv("BASE_URL"):
            os.environ[f"{provider}_BASE_URL"] = os.getenv("BASE_URL", "")


def get_default_model() -> str:
    return (
        os.getenv("TUTORMATCH_MODEL")
        or os.getenv("MODEL")
        or os.getenv("LLM_MODEL")
        or DEFAULT_MODEL
    )


def get_amap_mcp_url() -> str | None:
    return os.getenv("AMAP_MCP_URL") or None
