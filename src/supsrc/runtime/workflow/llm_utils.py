#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.config import LLMConfig

# LLM imports are conditional - use Foundation's optional dependency pattern
from provide.foundation.utils.optional_deps import OptionalDependency

# Create dependency handler for LLM features
_llm_dep = OptionalDependency("google-generativeai", "llm")
LLM_AVAILABLE = _llm_dep.is_available()

if LLM_AVAILABLE:
    from supsrc.llm.providers.base import LLMProvider
    from supsrc.llm.providers.gemini import GeminiProvider
    from supsrc.llm.providers.ollama import OllamaProvider
else:
    from provide.foundation.utils import create_dependency_stub

    LLMProvider = create_dependency_stub("google-generativeai", "llm")
    GeminiProvider = create_dependency_stub("google-generativeai", "llm")
    OllamaProvider = create_dependency_stub("ollama", "llm")

log = get_logger("runtime.workflow.llm_utils")


class LLMProviderManager:
    """Manages LLM provider instances and configuration."""

    def __init__(self) -> None:
        """Initialize the LLM provider manager."""
        self._llm_providers: dict[str, LLMProvider] = {}

    def get_llm_provider(self, llm_config: LLMConfig) -> LLMProvider | None:
        """Instantiates and returns an LLM provider based on config.

        Args:
            llm_config: LLM configuration object

        Returns:
            LLM provider instance or None if unavailable/failed
        """
        if not LLM_AVAILABLE:
            return None

        provider_key = f"{llm_config.provider}:{llm_config.model}"
        if provider_key in self._llm_providers:
            return self._llm_providers[provider_key]

        api_key = os.environ.get(llm_config.api_key_env_var) if llm_config.api_key_env_var else None

        provider_map = {"gemini": GeminiProvider, "ollama": OllamaProvider}
        provider_class = provider_map.get(llm_config.provider)

        if not provider_class:
            log.error("Unsupported LLM provider specified", provider=llm_config.provider)
            return None

        try:
            provider = provider_class(model=llm_config.model, api_key=api_key)
            self._llm_providers[provider_key] = provider
            return provider
        except (ImportError, ValueError) as e:
            log.error("Failed to instantiate LLM provider", error=str(e), exc_info=True)
            return None


# 🔼⚙️🔚
