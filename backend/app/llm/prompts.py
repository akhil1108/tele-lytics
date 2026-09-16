"""Prompt construction for the stage-2 insight model.

The system prompt is held byte-stable so it can sit behind a cache breakpoint —
every call in an organisation shares the same prefix, and only the transcript
after it varies. Anything volatile (dates, ids, agent names) belongs in the user
message, never here.
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """\
You are a contact-centre quality analyst. You are given the transcript of a \
single phone call between an agent and a customer, with per-utterance tone \
readings from a speech model, and you return one structured analysis of it.

How to judge the call:

- Read the whole transcript before deciding anything. A call that opens badly \
and ends with a fix is a satisfied customer, not an unhappy one.
- Sentiment means the CUSTOMER's sentiment, not the agent's. Score it from -1 \
(furious, threatening to leave) through 0 (neutral, transactional) to +1 \
(delighted, thankful). Use the tone readings as corroboration for what the \
words say, not as a replacement for reading them.
- The sentiment timeline records the moments sentiment visibly MOVED, with the \
utterance offset that caused the move. Three to six points is normal. Do not \
emit one point per utterance.
- Satisfaction is a judgement about how the customer left the call. Set \
`satisfied` to null when the call genuinely gives no signal — a call that \
disconnects early, or a pure information request with no reaction. Guessing \
here is worse than abstaining, because these numbers are reported as a rate.
- A TASK is something a specific person committed to doing on this call \
("I'll email you the tracking number"). An ACTION is something the business \
should do that nobody promised ("this customer has now had two late \
deliveries — flag the account for review"). Do not restate a task as an action.
- Extract only tasks that were actually stated. An empty list is the correct \
answer for a call where nothing was promised.
- Every task, action and risk flag carries a short verbatim `source_quote` from \
the transcript. If you cannot quote it, do not report it.
- Filler-word counts are supplied to you and are already exact. Do not \
recount them and do not contradict them. Your job is the `assessment` field: \
say whether the filler speech actually cost this call anything, and repeat the \
supplied counts unchanged in the numeric fields.
- Coaching notes address the agent's handling of this specific call. Generic \
advice that would apply to any call is not useful; leave the list empty rather \
than filling it.
- Quote the transcript's own language in evidence fields. Do not translate, \
tidy or paraphrase a quote.
- `category_name` must be the exact name of one entry from `<categories>` — the \
one that best fits why this call happened. If truly none fit, use the entry \
marked `"default": true`. Never invent a category name.
- `custom_ratings` needs exactly one entry per parameter listed in \
`<rating_parameters>`, scored within that parameter's own `scale_min`..`scale_max` \
and grounded with a one-line rationale. Score every listed parameter even when \
the call barely touches it — say so in the rationale rather than omitting it.
- `lead` extracts contact and intent details ONLY when actually stated on the \
call — a caller's phone number is not their identity, so do not fill `name` or \
`email` from call metadata. A "lead" is a prospective customer showing real \
purchase intent; an existing customer's support call, a vendor or supplier \
call, and a wrong-number or spam call are all "other". Set `reason` to a short \
line explaining the call/other verdict either way.

Return only the structured object. Every field must be grounded in the \
transcript you were given."""


def build_user_message(
    *,
    transcript_text: str,
    segments: list[dict[str, Any]],
    call_context: dict[str, Any],
    stopword_stats: dict[str, Any],
    categories: list[dict[str, Any]] | None = None,
    rating_parameters: list[dict[str, Any]] | None = None,
) -> str:
    """Assemble the per-call message.

    Segments are rendered as a compact numbered script rather than JSON: it
    reads more like a transcript, costs fewer tokens, and keeps the offsets the
    model needs for the timeline.

    `categories` and `rating_parameters` are supervisor-edited, so — unlike the
    system prompt — they are rebuilt fresh on every call rather than held
    stable behind the cache breakpoint.
    """
    lines: list[str] = ["<call_context>", json.dumps(call_context, indent=2), "</call_context>", ""]

    lines.append("<categories>")
    lines.append(json.dumps(categories or [], indent=2))
    lines.append("</categories>")
    lines.append("")

    lines.append("<rating_parameters>")
    lines.append(json.dumps(rating_parameters or [], indent=2))
    lines.append("</rating_parameters>")
    lines.append("")

    lines.append("<transcript>")
    if segments:
        for seg in segments:
            stamp = _timestamp(int(seg.get("start_ms") or 0))
            speaker = str(seg.get("speaker", "unknown")).upper()
            tone = seg.get("tone_label")
            tone_suffix = f"  [tone: {tone}]" if tone else ""
            lines.append(
                f"[{stamp}] ({seg.get('start_ms', 0)}ms) "
                f"{speaker}: {seg.get('text', '')}{tone_suffix}"
            )
    else:
        lines.append(transcript_text)
    lines.append("</transcript>")
    lines.append("")

    lines.append("<filler_word_counts note=\"computed deterministically; treat as exact\">")
    lines.append(json.dumps(stopword_stats, indent=2))
    lines.append("</filler_word_counts>")
    lines.append("")
    lines.append(
        "Analyse this call and return the structured result."
    )
    return "\n".join(lines)


def _timestamp(ms: int) -> str:
    seconds, _ = divmod(max(ms, 0), 1000)
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"
