"""ORM 模型 — 故乡来信 v2 数据库"""
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    hometown = relationship("Hometown", back_populates="user", uselist=False,
                            cascade="all, delete-orphan")
    profile = relationship("Profile", back_populates="user", uselist=False,
                           cascade="all, delete-orphan")
    landmarks = relationship("Landmark", back_populates="user",
                             cascade="all, delete-orphan")
    postcards = relationship("Postcard", back_populates="user",
                             cascade="all, delete-orphan")
    letters = relationship("Letter", back_populates="user",
                           cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="user",
                            cascade="all, delete-orphan")
    past_self_profile = relationship("PastSelfProfile", back_populates="user",
                                     uselist=False, cascade="all, delete-orphan")


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


# ──────────── landmarks ────────────

class Landmark(Base):
    __tablename__ = "landmarks"
    __table_args__ = (
        Index("ix_landmarks_user_used", "user_id", "is_used"),
        Index("ix_landmarks_user_tier", "user_id", "tier"),
        Index("ix_landmarks_user_name", "user_id", "name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    scene_type = Column(String(32), default="other")
    tier = Column(String(8), default="county")
    used_count = Column(Integer, default=0)
    last_used_day = Column(Integer, nullable=True)
    source = Column(String(32), default="web_search_seed")
    is_used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="landmarks")


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
    landmark_id = Column(Integer, ForeignKey("landmarks.id"), nullable=True)
    landmark_description = Column(Text, default="")
    mood = Column(String(32), default="平静")
    image_path = Column(String(512), default="")
    image_prompt = Column(Text, default="")
    search_image_urls = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    letter_text = Column(Text, default="")
    tags = Column(JSON, default=list)
    used_fallback = Column(Boolean, default=False)

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
