"""ORM 模型 — 故乡来信数据库"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ──────────── users ────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    current_day = Column(Integer, default=0, nullable=False)
    postcard_limit = Column(Integer, default=5, nullable=False)
    postcard_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    is_developer = Column(Boolean, default=False, nullable=False)

    hometown = relationship("Hometown", back_populates="user", uselist=False,
                            cascade="all, delete-orphan")
    profile = relationship("Profile", back_populates="user", uselist=False,
                           cascade="all, delete-orphan")
    postcards = relationship("Postcard", back_populates="user",
                             cascade="all, delete-orphan")
    letters = relationship("Letter", back_populates="user",
                           cascade="all, delete-orphan")
    letter_summaries = relationship("LetterSummary", back_populates="user",
                                    cascade="all, delete-orphan")
    letter_memories = relationship("LetterMemory", back_populates="user",
                                   cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user",
                            cascade="all, delete-orphan")
    past_self_profile = relationship("PastSelfProfile", back_populates="user",
                                     uselist=False, cascade="all, delete-orphan")
    letter_likes = relationship("LetterLike", back_populates="user",
                                 cascade="all, delete-orphan")
    sent_mails = relationship("Mail", foreign_keys="Mail.sender_id",
                              back_populates="sender", cascade="all, delete-orphan")
    received_mails = relationship("Mail", foreign_keys="Mail.recipient_id",
                                  back_populates="recipient", cascade="all, delete-orphan")


# ──────────── hometowns ────────────

class Hometown(Base):
    __tablename__ = "hometowns"
    __table_args__ = (UniqueConstraint("user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    province = Column(String(32), default="")
    city = Column(String(32), default="")
    county = Column(String(32), default="")
    hometown_name = Column(String(64), default="")

    user = relationship("User", back_populates="hometown")


# ──────────── profiles ────────────

class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    data = Column(JSON, default=dict)

    user = relationship("User", back_populates="profile")


# ──────────── postcards ────────────

class Postcard(Base):
    __tablename__ = "postcards"
    __table_args__ = (
        Index("ix_postcards_user_time", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(256), default="")
    body = Column(Text, default="")
    poem = Column(Text, default="")
    place = Column(String(128), default="")
    generation_place = Column(String(128), default="")
    mood = Column(String(32), default="平静")
    image_thumb_key = Column(String(512), nullable=False, default="")
    image_card_key = Column(String(512), nullable=False, default="")
    image_original_key = Column(String(512), nullable=False, default="")
    image_prompt = Column(Text, default="")
    search_image_urls = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    letter_text = Column(Text, default="")
    tags = Column(JSON, default=list)

    user = relationship("User", back_populates="postcards")


# ──────────── letters ────────────

class Letter(Base):
    __tablename__ = "letters"
    __table_args__ = (
        Index("ix_letters_user_time", "user_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, default="")
    place = Column(String(128), default="")
    mood = Column(String(32), default="平静")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="letters")
    likes = relationship("LetterLike", back_populates="letter", cascade="all, delete-orphan")


# ──────────── letter_summaries ────────────

class LetterSummary(Base):
    __tablename__ = "letter_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "batch_no"),
        Index("ix_letter_summaries_user_batch", "user_id", "batch_no"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    batch_no = Column(Integer, nullable=False)
    start_letter_id = Column(Integer, ForeignKey("letters.id"), nullable=False)
    end_letter_id = Column(Integer, ForeignKey("letters.id"), nullable=False)
    letter_count = Column(Integer, default=5, nullable=False)
    summary_text = Column(Text, default="")
    source_letter_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="letter_summaries")
    memory = relationship("LetterMemory", back_populates="summary", uselist=False,
                          cascade="all, delete-orphan")


# ──────────── letter_memories ────────────

class LetterMemory(Base):
    __tablename__ = "letter_memories"
    __table_args__ = (
        UniqueConstraint("summary_id"),
        Index("ix_letter_memories_user_summary", "user_id", "summary_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    summary_id = Column(Integer, ForeignKey("letter_summaries.id"), unique=True, nullable=False)
    memory_overview = Column(Text, default="")
    emotion_signals = Column(JSON, default=list)
    place_signals = Column(JSON, default=list)
    theme_signals = Column(JSON, default=list)
    people_signals = Column(JSON, default=list)
    sensory_signals = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="letter_memories")
    summary = relationship("LetterSummary", back_populates="memory")


# ──────────── memories ────────────

class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_time", "user_id", "timestamp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, default="")
    tags = Column(JSON, default=list)
    place_hint = Column(String(128), default="")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    analysis_status = Column(String(16), default="pending")
    summary = Column(Text, default="")

    user = relationship("User", back_populates="memories")


# ──────────── past_self_profiles ────────────

class PastSelfProfile(Base):
    __tablename__ = "past_self_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    summary = Column(Text, default="")
    latent_place_affinities = Column(JSON, default=list)
    sensory_biases = Column(JSON, default=list)
    identity_signals = Column(JSON, default=list)
    recent_memory_signals = Column(JSON, default=list)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="past_self_profile")


# ──────────── mails ────────────

class Mail(Base):
    __tablename__ = "mails"
    __table_args__ = (
        Index("ix_mails_recipient_time", "recipient_id", "sent_at"),
        Index("ix_mails_sender_time", "sender_id", "sent_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(256), default="")
    content = Column(Text, default="")
    attached_postcard_id = Column(Integer, ForeignKey("postcards.id"), nullable=True)
    attached_letter_id = Column(Integer, ForeignKey("letters.id"), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    sender_deleted = Column(Boolean, default=False, nullable=False)
    recipient_deleted = Column(Boolean, default=False, nullable=False)
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_mails")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="received_mails")
    attached_postcard = relationship("Postcard", foreign_keys=[attached_postcard_id])
    attached_letter = relationship("Letter", foreign_keys=[attached_letter_id])


# ──────────── letter_likes ────────────

class LetterLike(Base):
    """用户点赞的社区信件 — 点赞后出现在桌面上"""
    __tablename__ = "letter_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "letter_id"),
        Index("ix_letter_likes_user", "user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    letter_id = Column(Integer, ForeignKey("letters.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="letter_likes")
    letter = relationship("Letter", back_populates="likes")


# ──────────── system events ────────────

class SystemEvent(Base):
    """本地可查询的运行事件，用于开发者后台和故障排查。"""
    __tablename__ = "system_events"
    __table_args__ = (
        Index("ix_system_events_created", "created_at"),
        Index("ix_system_events_level_created", "level", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(16), nullable=False, default="info")
    event_type = Column(String(64), nullable=False)
    message = Column(Text, default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    request_id = Column(String(64), default="")
    event_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class RateLimitEvent(Base):
    """持久化认证限流事件，服务重启后仍然有效。"""
    __tablename__ = "rate_limit_events"
    __table_args__ = (Index("ix_rate_limit_events_key_time", "key", "created_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ApiMetric(Base):
    """按方法和归一化路径聚合的 API 指标。"""
    __tablename__ = "api_metrics"
    __table_args__ = (UniqueConstraint("method", "path"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    method = Column(String(12), nullable=False)
    path = Column(String(256), nullable=False)
    count = Column(Integer, default=0, nullable=False)
    success = Column(Integer, default=0, nullable=False)
    client_errors = Column(Integer, default=0, nullable=False)
    server_errors = Column(Integer, default=0, nullable=False)
    total_ms = Column(Integer, default=0, nullable=False)
    max_ms = Column(Integer, default=0, nullable=False)
    last_status = Column(Integer, default=0, nullable=False)
    last_at = Column(DateTime, nullable=True)


class StorageDeletionTask(Base):
    """OSS 删除失败时的重试任务。"""
    __tablename__ = "storage_deletion_tasks"
    __table_args__ = (Index("ix_storage_tasks_status_updated", "status", "updated_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(Integer, nullable=False)
    object_keys = Column(JSON, nullable=False)
    status = Column(String(16), default="pending", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
