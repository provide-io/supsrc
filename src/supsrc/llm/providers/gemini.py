# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""LLMProvider implementation for Google Gemini."""

import asyncio
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

# Defer google-genai import to avoid pydantic deprecation warnings during test discovery
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


class GeminiProvider:
    """LLMProvider implementation for Google Gemini."""

    def __init__(self, model: str, api_key: str | None = None) -> None:
        # Import google-genai here to avoid pydantic deprecation warnings during test discovery
        try:
            from google import genai
        except ImportError as e:
            raise ImportError("Google GenAI library not found. Please install `supsrc[llm]`.") from e

        self.client = genai.Client(api_key=api_key)  # API key can be None
        self.model_name = model

        # Add rate limiter: Gemini API allows ~60 requests per minute
        self._rate_limiter = TokenBucketRateLimiter(
            capacity=60,  # Max 60 requests
            refill_rate=1.0,  # 1 token per second = 60 per minute
            initial_tokens=10,  # Start with some tokens available
        )

        log.info("GeminiProvider initialized", model=model, rate_limit="60 req/min")

    async def _generate(self, prompt: str) -> str:
        """Internal helper to run generation with rate limiting and timing."""
        # Wait for rate limiter
        await asyncio.to_thread(self._rate_limiter.acquire, 1)

        try:
            with timed_block("gemini_api_call") as timer:
                # The new SDK uses a synchronous generate_content method on the client.
                # We run it in a thread to keep our provider async.
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_name,
                    contents=prompt,
                )
                result = response.text.strip()

            # Log timing information
            log.debug(
                "Gemini API call completed",
                duration_ms=timer.elapsed_ms,
                model=self.model_name,
                tokens_remaining=self._rate_limiter.available_tokens(),
            )
            return result

        except Exception as e:
            log.error("Gemini API call failed", error=str(e), exc_info=True)
            return f"Error: LLM generation failed. {e}"

    async def generate_commit_message(self, diff: str, conventional: bool) -> str:
        log.debug("Generating commit message with Gemini", conventional=conventional)
        prompt_template = CONVENTIONAL_COMMIT_PROMPT_TEMPLATE if conventional else BASIC_COMMIT_PROMPT_TEMPLATE
        prompt = prompt_template.format(diff=diff)
        raw_response = await self._generate(prompt)
        return _clean_llm_output(raw_response)

    async def review_changes(self, diff: str) -> tuple[bool, str]:
        log.debug("Reviewing changes with Gemini")
        prompt = CODE_REVIEW_PROMPT_TEMPLATE.format(diff=diff)
        response = await self._generate(prompt)

        if response.startswith("VETO:"):
            reason = response.removeprefix("VETO:").strip()
            log.warning("Gemini review vetoed commit", reason=reason)
            return True, reason
        return False, "OK"

    async def analyze_test_failure(self, output: str) -> str:
        log.debug("Analyzing test failure with Gemini")
        prompt = TEST_FAILURE_ANALYSIS_PROMPT_TEMPLATE.format(output=output)
        return await self._generate(prompt)

    async def generate_change_fragment(self, diff: str, commit_message: str) -> str:
        log.debug("Generating change fragment with Gemini")
        prompt = CHANGE_FRAGMENT_PROMPT_TEMPLATE.format(commit_message=commit_message, diff=diff)
        raw_response = await self._generate(prompt)
        return _clean_llm_output(raw_response)


# 🧠💎

# 🔼⚙️🔚
