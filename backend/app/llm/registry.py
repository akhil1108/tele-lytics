"""Provider selection.

One place decides which speech and insight backends the pipeline uses, so a
deployment switches models by environment variable and nothing else changes.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.analysis.base import AnalysisProvider
from app.llm.stt.base import SpeechToTextProvider

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_stt_provider() -> SpeechToTextProvider:
    if settings.stt_provider == "shared_model":
        from app.llm.stt.shared_model import SharedModelSpeechToText

        provider = SharedModelSpeechToText()
    else:
        from app.llm.stt.mock import MockSpeechToText

        provider = MockSpeechToText()

    log.info("speech provider selected", extra={"provider": provider.name})
    return provider


@lru_cache(maxsize=1)
def get_analysis_provider() -> AnalysisProvider:
    if settings.analysis_provider == "claude":
        from app.llm.analysis.claude import ClaudeAnalysisProvider

        provider = ClaudeAnalysisProvider()
    else:
        from app.llm.analysis.mock import MockAnalysisProvider

        provider = MockAnalysisProvider()

    log.info("analysis provider selected", extra={"provider": provider.name})
    return provider


def reset_providers() -> None:
    """Drop cached providers. Used by tests that flip configuration."""
    get_stt_provider.cache_clear()
    get_analysis_provider.cache_clear()
