"""Public-demo protection: per-IP and daily caps. Only enforced with real providers."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import JevProviderName, Settings
from app.db.models import Conversation, JevDecisionRow
from app.services.errors import LimitExceededError


def hash_ip(ip: str | None, salt: str) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def _start_of_day() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def check_start_limits(session: AsyncSession, settings: Settings, ip_hash: str | None) -> None:
    if not settings.uses_real_providers:
        return
    today = await session.scalar(
        select(func.count()).select_from(Conversation).where(Conversation.created_at >= _start_of_day())
    )
    if (today or 0) >= settings.daily_conversation_cap:
        raise LimitExceededError("DAILY_LIMIT", "The demo has reached today's limit. Please come back tomorrow.")
    if ip_hash:
        recent = await session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.client_ip_hash == ip_hash)
            .where(Conversation.created_at >= datetime.now(UTC) - timedelta(hours=1))
        )
        if (recent or 0) >= settings.conversations_per_ip_per_hour:
            raise LimitExceededError(
                "RATE_LIMITED", "You've started several conversations recently. Please try again later."
            )


async def jev_daily_cap_reached(session: AsyncSession, settings: Settings) -> bool:
    if settings.jev_provider != JevProviderName.REAL:
        return False
    count = await session.scalar(
        select(func.count()).select_from(JevDecisionRow).where(JevDecisionRow.created_at >= _start_of_day())
    )
    return (count or 0) >= settings.daily_jev_call_cap
