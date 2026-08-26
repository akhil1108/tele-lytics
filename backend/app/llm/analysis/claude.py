"""Stage-2 insight provider backed by the Claude API.

Uses structured outputs so the response validates against `CallAnalysis`
directly — there is no JSON parsing or repair step, and a malformed response is
impossible rather than merely unlikely.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.llm.analysis.base import AnalysisInput
from app.llm.prompts import SYSTEM_PROMPT, build_user_message
from app.llm.schemas import AnalysisResult, CallAnalysis

log = get_logger(__name__)

# Server-side refusal fallback: if a safety classifier declines the request,
# the API re-runs it on a fallback model inside the same call rather than
# returning nothing. Without this a declined call would simply have no analysis.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeAnalysisProvider:
    name = "claude"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        effort: str | None = None,
    ) -> None:
        key = api_key or settings.anthropic_api_key
        self.model = model or settings.analysis_model
        self.max_tokens = max_tokens or settings.analysis_max_tokens
        self.effort = effort or settings.analysis_effort
        # A bare client also resolves an `ant auth login` profile, so an unset
        # ANTHROPIC_API_KEY is not by itself a misconfiguration.
        self._client = anthropic.AsyncAnthropic(api_key=key) if key else anthropic.AsyncAnthropic()

    async def analyse(self, payload: AnalysisInput) -> AnalysisResult:
        user_message = build_user_message(
            transcript_text=payload.transcript_text,
            segments=payload.segments,
            call_context=payload.call_context,
            stopword_stats=payload.stopword_stats,
        )

        started = time.monotonic()
        try:
            response = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                # The system prompt is identical for every call, so caching it
                # makes the per-call cost essentially the transcript alone.
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                output_format=CallAnalysis,
                betas=[_FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"analysis model rate limited: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"analysis model unreachable: {exc}") from exc
        except anthropic.BadRequestError as exc:
            # A malformed request will fail identically on every retry.
            raise ProviderError(f"analysis request rejected: {exc}", retryable=False) from exc
        except anthropic.AuthenticationError as exc:
            raise ProviderError(
                f"analysis model authentication failed: {exc}", retryable=False
            ) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"analysis model returned {exc.status_code}: {exc}",
                retryable=exc.status_code >= 500,
            ) from exc

        if response.stop_reason == "refusal":
            detail = getattr(response.stop_details, "category", None) or "unspecified"
            raise ProviderError(
                f"analysis declined by safety classifier (category: {detail})",
                retryable=False,
            )

        analysis = response.parsed_output
        if analysis is None:
            raise ProviderError("analysis model returned no structured output")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "call analysed",
            extra={
                "call_id": payload.call_id,
                "model": response.model,
                "elapsed_ms": elapsed_ms,
                "request_id": response._request_id,
            },
        )

        return AnalysisResult(
            provider=self.name,
            model=response.model or self.model,
            analysis=analysis,
            token_usage=_usage_dict(response.usage),
            raw={
                "request_id": response._request_id,
                "stop_reason": response.stop_reason,
                "elapsed_ms": elapsed_ms,
            },
        )


def _usage_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    try:
        return usage.model_dump(exclude_none=True)
    except AttributeError:
        return {
            key: getattr(usage, key, None)
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
            )
        }
