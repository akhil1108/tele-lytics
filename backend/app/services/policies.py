"""Recording-policy resolution.

Answers one question for the handset: *should this call be recorded?* — and
records why, so the dashboard can explain any gap in coverage.

The rules, in order:

1. An explicit policy on the **customer's** number that disables recording wins
   over everything. That row is how a do-not-record request is honoured, and it
   has to beat the agent's own settings or it is worthless.
2. Otherwise the **agent's** number decides, including its per-direction flags.
3. With no policy on the agent's number, the answer is **no**. Recording by
   default is the wrong failure mode: an unrecorded call is a gap in a report,
   an unlawfully recorded one is a liability.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import CallDirection
from app.db.models import PhoneNumberPolicy
from app.schemas.policies import PolicyDecision


async def get_policy(
    session: AsyncSession, org_id: str, e164: str
) -> PhoneNumberPolicy | None:
    return (
        await session.execute(
            select(PhoneNumberPolicy).where(
                PhoneNumberPolicy.org_id == org_id, PhoneNumberPolicy.e164 == e164
            )
        )
    ).scalar_one_or_none()


async def decide(
    session: AsyncSession,
    *,
    org_id: str,
    agent_number: str,
    customer_number: str | None = None,
    direction: str = CallDirection.OUTBOUND,
) -> PolicyDecision:
    if customer_number:
        customer_policy = await get_policy(session, org_id, customer_number)
        if customer_policy is not None and not customer_policy.recording_enabled:
            return PolicyDecision(
                number=agent_number,
                should_record=False,
                reason="customer_opted_out",
                consent_required=customer_policy.consent_required,
                policy_id=customer_policy.id,
            )

    policy = await get_policy(session, org_id, agent_number)
    if policy is None:
        return PolicyDecision(
            number=agent_number,
            should_record=False,
            reason="no_policy_configured",
            consent_required=True,
        )

    if not policy.recording_enabled:
        return PolicyDecision(
            number=agent_number,
            should_record=False,
            reason="recording_disabled_for_number",
            consent_required=policy.consent_required,
            consent_prompt=policy.consent_prompt,
            policy_id=policy.id,
            retention_days=policy.retention_days,
        )

    allowed = (
        policy.record_inbound if direction == CallDirection.INBOUND else policy.record_outbound
    )
    if not allowed:
        return PolicyDecision(
            number=agent_number,
            should_record=False,
            reason=f"{direction}_calls_not_recorded",
            consent_required=policy.consent_required,
            consent_prompt=policy.consent_prompt,
            policy_id=policy.id,
            retention_days=policy.retention_days,
        )

    return PolicyDecision(
        number=agent_number,
        should_record=True,
        reason="policy_enabled",
        consent_required=policy.consent_required,
        consent_prompt=policy.consent_prompt
        or "This call may be recorded for quality and training purposes.",
        policy_id=policy.id,
        retention_days=policy.retention_days,
    )
