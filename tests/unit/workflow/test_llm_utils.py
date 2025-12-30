#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for LLMProviderManager."""

from __future__ import annotations

import os

from attrs import evolve
from provide.testkit.mocking import MagicMock, patch
import pytest

from supsrc.config import LLMConfig
from supsrc.runtime.workflow.llm_utils import LLMProviderManager


@pytest.fixture
def llm_config():
    """Provide a sample LLM configuration."""
    return LLMConfig(
        enabled=True,
        provider="gemini",
        model="gemini-pro",
        api_key_env_var="GEMINI_API_KEY",
        review_changes=True,
        generate_commit_message=True,
        run_tests=False,
        analyze_test_failures=False,
        generate_change_fragment=False,
        use_conventional_commit=True,
        test_command=None,
        change_fragment_dir=None,
    )


class TestLLMProviderManager:
    """Test suite for LLMProviderManager class."""

    def test_init(self):
        """Test LLMProviderManager initialization."""
        manager = LLMProviderManager()
        assert manager._llm_providers == {}

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_success(self, mock_gemini_provider, llm_config):
        """Test successful LLM provider creation."""
        mock_provider_instance = MagicMock()
        mock_gemini_provider.return_value = mock_provider_instance

        manager = LLMProviderManager()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            provider = manager.get_llm_provider(llm_config)

        assert provider == mock_provider_instance
        mock_gemini_provider.assert_called_once_with(model="gemini-pro", api_key="test-api-key")

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_cached(self, mock_gemini_provider, llm_config):
        """Test that LLM provider is cached after first creation."""
        mock_provider_instance = MagicMock()
        mock_gemini_provider.return_value = mock_provider_instance

        manager = LLMProviderManager()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            provider1 = manager.get_llm_provider(llm_config)
            provider2 = manager.get_llm_provider(llm_config)

        assert provider1 == provider2 == mock_provider_instance
        # Should only be called once due to caching
        mock_gemini_provider.assert_called_once()

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", False)
    def test_get_llm_provider_unavailable(self, llm_config):
        """Test LLM provider when LLM is not available."""
        manager = LLMProviderManager()
        provider = manager.get_llm_provider(llm_config)

        assert provider is None

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    def test_get_llm_provider_unsupported_provider(self, llm_config):
        """Test LLM provider with unsupported provider."""
        # Use evolve() to modify frozen dataclass
        llm_config = evolve(llm_config, provider="unsupported_provider")
        manager = LLMProviderManager()

        provider = manager.get_llm_provider(llm_config)

        assert provider is None

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.OllamaProvider")
    def test_get_llm_provider_ollama(self, mock_ollama_provider, llm_config):
        """Test LLM provider creation for Ollama."""
        # Use evolve() to modify frozen dataclass
        llm_config = evolve(llm_config, provider="ollama", model="llama2", api_key_env_var=None)

        mock_provider_instance = MagicMock()
        mock_ollama_provider.return_value = mock_provider_instance

        manager = LLMProviderManager()
        provider = manager.get_llm_provider(llm_config)

        assert provider == mock_provider_instance
        mock_ollama_provider.assert_called_once_with(model="llama2", api_key=None)

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_no_api_key_env(self, mock_gemini_provider, llm_config):
        """Test LLM provider creation without API key environment variable."""
        # Use evolve() to modify frozen dataclass
        llm_config = evolve(llm_config, api_key_env_var=None)
        mock_provider_instance = MagicMock()
        mock_gemini_provider.return_value = mock_provider_instance

        manager = LLMProviderManager()
        provider = manager.get_llm_provider(llm_config)

        assert provider == mock_provider_instance
        mock_gemini_provider.assert_called_once_with(model="gemini-pro", api_key=None)

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_import_error(self, mock_gemini_provider, llm_config):
        """Test LLM provider creation with ImportError."""
        mock_gemini_provider.side_effect = ImportError("Module not found")

        manager = LLMProviderManager()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            provider = manager.get_llm_provider(llm_config)

        assert provider is None

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_value_error(self, mock_gemini_provider, llm_config):
        """Test LLM provider creation with ValueError."""
        mock_gemini_provider.side_effect = ValueError("Invalid configuration")

        manager = LLMProviderManager()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            provider = manager.get_llm_provider(llm_config)

        assert provider is None

    @patch("supsrc.runtime.workflow.llm_utils.LLM_AVAILABLE", True)
    @patch("supsrc.runtime.workflow.llm_utils.GeminiProvider")
    def test_get_llm_provider_different_configs(self, mock_gemini_provider, llm_config):
        """Test that different configs create different cached providers."""
        mock_provider1 = MagicMock()
        mock_provider2 = MagicMock()
        mock_gemini_provider.side_effect = [mock_provider1, mock_provider2]

        # Create second config with different model
        llm_config2 = LLMConfig(
            enabled=True,
            provider="gemini",
            model="gemini-pro-vision",
            api_key_env_var="GEMINI_API_KEY",
            review_changes=True,
            generate_commit_message=True,
            run_tests=False,
            analyze_test_failures=False,
            generate_change_fragment=False,
            use_conventional_commit=True,
            test_command=None,
            change_fragment_dir=None,
        )

        manager = LLMProviderManager()

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            provider1 = manager.get_llm_provider(llm_config)
            provider2 = manager.get_llm_provider(llm_config2)

        assert provider1 == mock_provider1
        assert provider2 == mock_provider2
        assert provider1 != provider2
        assert mock_gemini_provider.call_count == 2


# 🔼⚙️🔚
