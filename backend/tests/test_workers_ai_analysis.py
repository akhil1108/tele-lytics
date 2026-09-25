"""Unit tests for the Workers AI analysis provider.

No network access, no running Cloudflare endpoint — the Instructor-wrapped
client is a stub whose `create_with_completion` is mocked directly, same
seam `client`/`model`/`max_tokens` overrides give `ClaudeAnalysisProvider`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
from instructor.core import InstructorRetryException

from app.core.errors import ProviderError
from app.llm.analysis.base import AnalysisInput
from app.llm.analysis.workers_ai import WorkersAiAnalysisProvider
from app.llm.schemas import CallAnalysis


def _stub_client(create_with_completion: AsyncMock) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create_with_completion=create_with_completion)
        )
    )


def _payload() -> AnalysisInput:
    return AnalysisInput(
        call_id="call-1",
        transcript_text="hello",
        segments=[],
        call_context={},
        stopword_stats={},
        categories=[{"name": "Support Request", "description": "", "default": True}],
        rating_parameters=[],
    )


async def test_happy_path_returns_analysis_result() -> None:
    analysis = CallAnalysis(
        summary="Customer called about billing.", category_name="Support Request"
    )
    completion = SimpleNamespace(model="@cf/ibm-granite/granite-4.0-h-micro", usage=None)
    client = _stub_client(AsyncMock(return_value=(analysis, completion)))

    provider = WorkersAiAnalysisProvider(client=client, model="test-model")
    result = await provider.analyse(_payload())

    assert result.provider == "workers_ai"
    assert result.model == "@cf/ibm-granite/granite-4.0-h-micro"
    assert result.analysis is analysis


async def test_retry_exhaustion_raises_retryable_provider_error() -> None:
    err = InstructorRetryException(
        "gave up", n_attempts=2, messages=[], last_completion=None, total_usage=0
    )
    client = _stub_client(AsyncMock(side_effect=err))

    provider = WorkersAiAnalysisProvider(client=client, model="test-model")
    with pytest.raises(ProviderError) as exc_info:
        await provider.analyse(_payload())

    assert exc_info.value.retryable is True


def _http_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://example.com"))


async def test_authentication_error_is_not_retryable() -> None:
    err = openai.AuthenticationError(
        message="invalid token", response=_http_response(401), body=None
    )
    client = _stub_client(AsyncMock(side_effect=err))

    provider = WorkersAiAnalysisProvider(client=client, model="test-model")
    with pytest.raises(ProviderError) as exc_info:
        await provider.analyse(_payload())

    assert exc_info.value.retryable is False


async def test_server_error_is_retryable() -> None:
    err = openai.APIStatusError(message="server error", response=_http_response(503), body=None)
    client = _stub_client(AsyncMock(side_effect=err))

    provider = WorkersAiAnalysisProvider(client=client, model="test-model")
    with pytest.raises(ProviderError) as exc_info:
        await provider.analyse(_payload())

    assert exc_info.value.retryable is True
