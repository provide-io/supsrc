#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""LLMProvider implementation for Ollama."""

import re

from provide.foundation.logger import get_logger

# Add Foundation utilities for rate limiting and timing
from provide.foundation.utils import TokenBucketRateLimiter, timed_block

from supsrc.llm.prompts import (
    BASIC_COMMIT_PROMPT_TEMPLATE,
    CHANGE_FRAGMENT_PROMPT_TEMPLATE,
    CODE_REVIEW_PROMPT_TEMPLATE,
    CONVENTIONAL_COMMIT_PROMPT_TEMPLATE,
    TEST_FAILURE_ANALYSIS_PROMPT_TEMPLATE,
)

# Defer ollama import to avoid issues during test discovery
# Import happens in __init__ when the provider is actually instantiated
log = get_logger(__name__)


def _clean_llm_output(raw_text: str) -> str:
    """Strips conversational boilerplate and markdown from LLM responses."""
    # First, try to find a markdown code block and extract its content
    match = re.search(r"```(?:\w*\n)?(.*?)```", raw_text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no markdown, find the last non-empty line, which is often the answer
    lines = [line.strip() for line in raw_text.strip().split("\n")]
    non_empty_lines = [line for line in lines if line]
    return non_empty_lines[-1] if non_empty_lines else raw_text


class OllamaProvider:
    """LLMProvider implementation for a local Ollama instance."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        # Import ollama here to defer loading until actually needed
        try:
            import ollama
        except ImportError as e:
            raise ImportError("Ollama library not found. Please install `supsrc[llm]`.") from e

        # Store reference to ollama module for exception handling
        self._ollama = ollama
        self.model = model
        self.client = ollama.AsyncClient()

        # Add rate limiter: Local Ollama is more generous, but still limit to avoid overwhelming
        self._rate_limiter = TokenBucketRateLimiter(
            capacity=30,  # Max 30 concurrent requests
            refill_rate=2.0,  # 2 tokens per second = 120 per minute
            initial_tokens=5,  # Start with some tokens available
        )

        log.info("OllamaProvider initialized", model=model, rate_limit="120 req/min")

    async def _generate(self, prompt: str) -> str:
        """Internal helper to run generation with rate limiting and timing."""
        # Wait for rate limiter
        self._rate_limiter.acquire(1)

        try:
            with timed_block("ollama_api_call") as timer:
                response = await self.client.generate(model=self.model, prompt=prompt)
                result = response["response"].strip()

            # Log timing information
            log.debug(
                "Ollama API call completed",
                duration_ms=timer.elapsed_ms,
                model=self.model,
                tokens_remaining=self._rate_limiter.available_tokens(),
            )
            return result

        except self._ollama.ResponseError as e:
            log.error(
                "Ollama API call failed",
                error=str(e.body),
                status_code=e.status_code,
                exc_info=True,
            )
            return f"Error: LLM generation failed. Status: {e.status_code}"
        except Exception as e:
            log.error("An unexpected error occurred with the Ollama provider", error=str(e), exc_info=True)
            return f"Error: An unexpected error occurred. {e}"

    async def generate_commit_message(self, diff: str, conventional: bool) -> str:
        log.debug("Generating commit message with Ollama", conventional=conventional)
        prompt_template = CONVENTIONAL_COMMIT_PROMPT_TEMPLATE if conventional else BASIC_COMMIT_PROMPT_TEMPLATE
        prompt = prompt_template.format(diff=diff)
        raw_response = await self._generate(prompt)
        return _clean_llm_output(raw_response)

    async def review_changes(self, diff: str) -> tuple[bool, str]:
        log.debug("Reviewing changes with Ollama")
        prompt = CODE_REVIEW_PROMPT_TEMPLATE.format(diff=diff)
        response = await self._generate(prompt)

        if response.startswith("VETO:"):
            reason = response.removeprefix("VETO:").strip()
            log.warning("Ollama review vetoed commit", reason=reason)
            return True, reason
        return False, "OK"

    async def analyze_test_failure(self, output: str) -> str:
        log.debug("Analyzing test failure with Ollama")
        prompt = TEST_FAILURE_ANALYSIS_PROMPT_TEMPLATE.format(output=output)
        return await self._generate(prompt)

    async def generate_change_fragment(self, diff: str, commit_message: str) -> str:
        log.debug("Generating change fragment with Ollama")
        prompt = CHANGE_FRAGMENT_PROMPT_TEMPLATE.format(commit_message=commit_message, diff=diff)
        raw_response = await self._generate(prompt)
        return _clean_llm_output(raw_response)


# 🧠🦙

# 🔼⚙️🔚
