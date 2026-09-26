"""Stage-2 insight provider backed by Cloudflare Workers AI.

Lightweight, opt-in alternative to `claude.py` — reached over Workers AI's
OpenAI-compatible endpoint, so the same `openai` SDK client works, just
pointed at a different base_url. Workers AI's own docs say it "can't
guarantee that the model responds according to the requested JSON Schema" —
a materially weaker guarantee than Claude's structured outputs — so this
goes through Instructor (`client.create(response_model=...)`) instead of the
raw `.beta.chat.completions.parse()` `claude.py` uses: Instructor validates
the response against `CallAnalysis` and, on failure, automatically feeds the
validation error back to the model and re-asks, in-call, up to
`max_retries` times before giving up. That's a real fix for the missing
guarantee, not a workaround — see the spike results in the plan this
provider came out of for why `Mode.JSON` and this model specifically.
"""

from __future__ import annotations

import time
from typing import Any

import instructor
import openai
from instructor.core import InstructorRetryException

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.llm.analysis.base import AnalysisInput
from app.llm.prompts import SYSTEM_PROMPT, build_user_message
from app.llm.schemas import AnalysisResult, CallAnalysis

log = get_logger(__name__)


class WorkersAiAnalysisProvider:
    name = "workers_ai"

    def __init__(
        self,
        client: instructor.AsyncInstructor | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.model = model or settings.workers_ai_model
        self.max_tokens = max_tokens or settings.workers_ai_max_tokens
        self.max_retries = (
            max_retries if max_retries is not None else settings.workers_ai_max_retries
        )
        self._client = client or instructor.from_openai(
            openai.AsyncOpenAI(
                base_url=(
                    f"https://api.cloudflare.com/client/v4/accounts/"
                    f"{settings.workers_ai_account_id}/ai/v1"
                ),
                api_key=settings.workers_ai_api_token or "not-needed",
                timeout=settings.workers_ai_timeout_seconds,
            ),
            mode=instructor.Mode.JSON,
        )

    async def analyse(self, payload: AnalysisInput) -> AnalysisResult:
        user_message = build_user_message(
            transcript_text=payload.transcript_text,
            segments=payload.segments,
            call_context=payload.call_context,
            stopword_stats=payload.stopword_stats,
            categories=payload.categories,
            rating_parameters=payload.rating_parameters,
        )

        started = time.monotonic()
        try:
            analysis, completion = await self._client.chat.completions.create_with_completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_model=CallAnalysis,
                max_tokens=self.max_tokens,
                max_retries=self.max_retries,
            )
        except InstructorRetryException as exc:
            # Schema conformance failed even after in-call retries — the
            # job-level queue retry is the next fallback, not the first one.
            raise ProviderError(
                f"analysis model never produced a valid response: {exc}", retryable=True
            ) from exc
        except openai.RateLimitError as exc:
            raise ProviderError(f"analysis model rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"analysis model unreachable: {exc}") from exc
        except openai.BadRequestError as exc:
            raise ProviderError(f"analysis request rejected: {exc}", retryable=False) from exc
        except openai.AuthenticationError as exc:
            raise ProviderError(
                f"analysis model authentication failed: {exc}", retryable=False
            ) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(
                f"analysis model returned {exc.status_code}: {exc}",
                retryable=exc.status_code >= 500,
            ) from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(
            "call analysed",
            extra={
                "call_id": payload.call_id,
                "model": completion.model,
                "elapsed_ms": elapsed_ms,
            },
        )

        return AnalysisResult(
            provider=self.name,
            model=completion.model or self.model,
            analysis=analysis,
            token_usage=_usage_dict(completion.usage),
            raw={"elapsed_ms": elapsed_ms},
        )


def _usage_dict(usage: Any) -> dict:
    if usage is None:
        return {}
    try:
        return usage.model_dump(exclude_none=True)
    except AttributeError:
        return {
            key: getattr(usage, key, None)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
