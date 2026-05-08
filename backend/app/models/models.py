from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class ClipStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"


class Streamer(Base):
    __tablename__ = "streamers"

    id = Column(String, primary_key=True, default=gen_uuid)
    twitch_id = Column(String, unique=True, nullable=False, index=True)
    login = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    profile_image_url = Column(String)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    token_expires_at = Column(DateTime, nullable=True)
    broadcaster_type = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    clips = relationship("Clip", back_populates="streamer")
    streams = relationship("Stream", back_populates="streamer")


class Stream(Base):
    __tablename__ = "streams"

    id = Column(String, primary_key=True, default=gen_uuid)
    streamer_id = Column(String, ForeignKey("streamers.id"), nullable=False)
    twitch_stream_id = Column(String, unique=True, nullable=True)
    game_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    is_live = Column(Boolean, default=False)
    viewer_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    streamer = relationship("Streamer", back_populates="streams")
    clips = relationship("Clip", back_populates="stream")


class Clip(Base):
    __tablename__ = "clips"

    id = Column(String, primary_key=True, default=gen_uuid)
    streamer_id = Column(String, ForeignKey("streamers.id"), nullable=False)
    stream_id = Column(String, ForeignKey("streams.id"), nullable=True)

    # Twitch clip data
    twitch_clip_id = Column(String, nullable=True, index=True)
    twitch_clip_url = Column(String, nullable=True)
    twitch_thumbnail_url = Column(String, nullable=True)

    # Highlight detection metadata
    highlight_score = Column(Float, default=0.0)
    score_breakdown = Column(JSON, default=dict)  # {chat: 30, audio: 20, transcript: 10}
    detected_at = Column(DateTime, default=datetime.utcnow)
    stream_timestamp_seconds = Column(Integer, nullable=True)

    # Content
    transcript = Column(Text, nullable=True)
    chat_context = Column(JSON, default=list)   # Last N chat messages
    ai_title = Column(String, nullable=True)
    ai_description = Column(Text, nullable=True)
    ai_hashtags = Column(JSON, default=list)

    # Video processing
    status = Column(SAEnum(ClipStatus), default=ClipStatus.PENDING)
    raw_clip_path = Column(String, nullable=True)
    processed_clip_path = Column(String, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Human review
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String, nullable=True)
    exported_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    streamer = relationship("Streamer", back_populates="clips")
    stream = relationship("Stream", back_populates="clips")
