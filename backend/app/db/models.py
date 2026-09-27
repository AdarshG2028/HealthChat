"""SQLAlchemy 2.0 models (§31). JSON columns become JSONB on Postgres."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(32))
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    ask_more_rounds: Mapped[int] = mapped_column(Integer, default=0)
    reevaluations: Mapped[int] = mapped_column(Integer, default=0)
    llm_provider: Mapped[str] = mapped_column(String(32))
    jev_provider: Mapped[str] = mapped_column(String(32))
    client_ip_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.seq", cascade="all, delete-orphan"
    )
    patient_state: Mapped["PatientStateRow | None"] = relationship(cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "idempotency_key", name="uq_message_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(64))
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class PatientStateRow(Base):
    __tablename__ = "patient_states"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[dict[str, Any]] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class JevDecisionRow(Base):
    __tablename__ = "jev_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    # Raw Jev answers
    action: Mapped[str] = mapped_column(String(32))
    department: Mapped[str] = mapped_column(String(32))
    urgency: Mapped[str] = mapped_column(String(16))
    complexity: Mapped[str] = mapped_column(String(16))
    missing_info: Mapped[str] = mapped_column(String(32))
    action_confidence: Mapped[float] = mapped_column(Float)
    department_confidence: Mapped[float] = mapped_column(Float)
    human_review_probability: Mapped[float] = mapped_column(Float)
    # After the deterministic safety policy
    final_action: Mapped[str] = mapped_column(String(32))
    final_department: Mapped[str] = mapped_column(String(32))
    final_urgency: Mapped[str] = mapped_column(String(16))
    final_complexity: Mapped[str] = mapped_column(String(16))
    human_review_recommended: Mapped[bool]
    emergency: Mapped[bool]
    crisis_support: Mapped[bool]
    policy_overrides: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    # Metadata
    provider: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    probabilities: Mapped[dict[str, Any]] = mapped_column(JSONType)
    raw_request: Mapped[dict[str, Any]] = mapped_column(JSONType)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (Index("ix_workflow_events_conversation_id_id", "conversation_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(48))
    # `metadata` is reserved on declarative classes, so the attribute is `data`.
    data: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
