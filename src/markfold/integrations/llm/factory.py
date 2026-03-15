from __future__ import annotations

from markfold.config import Settings, get_settings
from markfold.integrations.llm.base import LlmProvider
from markfold.integrations.llm.openai_provider import OpenAILlmProvider


def get_llm_provider(settings: Settings | None = None) -> LlmProvider:
    settings = settings or get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "未配置 LLM API。请在 .env 中设置 MARKFOLD_OPENAI_API_KEY，"
            "并按需设置 MARKFOLD_OPENAI_BASE_URL 和 MARKFOLD_OPENAI_MODEL。"
        )
    return OpenAILlmProvider(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        model=settings.openai_model,
    )
