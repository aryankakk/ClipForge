"""
AI service - Whisper for transcription, GPT for viral title + hashtag generation.
Gracefully degrades if OpenAI key is not set.
"""
import logging
import httpx
import json
from pathlib import Path
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OPENAI_BASE = "https://api.openai.com/v1"


async def transcribe_clip(clip_path: Path) -> Optional[str]:
    """Use OpenAI Whisper to transcribe a video clip's audio."""
    if not settings.OPENAI_API_KEY:
        logger.debug("No OpenAI key; skipping transcription")
        return None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(clip_path, "rb") as f:
                resp = await client.post(
                    f"{OPENAI_BASE}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    files={"file": (clip_path.name, f, "video/mp4")},
                    data={"model": "whisper-1", "language": "en"},
                )
            resp.raise_for_status()
            return resp.json().get("text", "").strip()
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        return None


async def generate_clip_metadata(
    transcript: Optional[str],
    chat_context: list,
    score_breakdown: dict,
    game_name: Optional[str] = None,
    streamer_name: Optional[str] = None,
) -> dict:
    """
    Use GPT-4o-mini to generate:
    - Viral clip title
    - Description
    - Hashtags
    - Excitement summary
    """
    if not settings.OPENAI_API_KEY:
        return _fallback_metadata(score_breakdown, game_name, streamer_name)

    chat_sample = "\n".join([f"{m.get('user')}: {m.get('text')}" for m in chat_context[-15:]])
    breakdown_str = ", ".join([f"{k}: {v:.0f}" for k, v in score_breakdown.items()])

    prompt = f"""You are a TikTok/YouTube Shorts clip metadata generator for Twitch streamers.

Context:
- Streamer: {streamer_name or 'Unknown'}
- Game: {game_name or 'Unknown'}
- Highlight score breakdown: {breakdown_str}
- Transcript: {transcript or '(no transcript)'}
- Recent chat messages:
{chat_sample or '(no chat data)'}

Generate metadata for this clip. Return ONLY valid JSON with these fields:
{{
  "title": "viral, engaging title under 60 chars, no hashtags",
  "description": "2-sentence engaging description of the moment",
  "hashtags": ["list", "of", "10", "relevant", "hashtags", "no", "hash", "symbol"],
  "excitement_level": "one of: epic, funny, hype, fail, clutch, wholesome",
  "hook": "15-word opening hook sentence for the caption"
}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.8,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        logger.error(f"GPT metadata generation failed: {e}")
        return _fallback_metadata(score_breakdown, game_name, streamer_name)


async def semantic_score_transcript(transcript: str) -> float:
    """
    Use GPT to semantically score how exciting/shareable a transcript is.
    Returns 0-50 additional score points.
    """
    if not settings.OPENAI_API_KEY or not transcript:
        return 0.0

    prompt = f"""Rate this stream clip transcript from 0-50 for how exciting, funny, or viral-worthy it is for TikTok/Shorts.

Transcript: "{transcript}"

High scores (40-50): Incredible reactions, shocking moments, hilarious fails, epic plays, emotional moments
Medium scores (20-39): Good moments, funny commentary, solid gameplay
Low scores (0-19): Boring, routine, nothing notable

Return ONLY a JSON object: {{"score": <number>, "reason": "<brief reason>"}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            score = float(data.get("score", 0))
            logger.info(f"Semantic score: {score} — {data.get('reason', '')}")
            return min(50.0, max(0.0, score))
    except Exception as e:
        logger.error(f"Semantic scoring failed: {e}")
        return 0.0


def _fallback_metadata(
    score_breakdown: dict,
    game_name: Optional[str],
    streamer_name: Optional[str],
) -> dict:
    """Generate basic metadata without AI."""
    dominant = max(score_breakdown, key=score_breakdown.get) if score_breakdown else "chat"
    excitement = {
        "chat_velocity": "hype",
        "chat_message": "funny",
        "sub": "wholesome",
        "raid": "hype",
        "cheer": "hype",
        "audio": "epic",
    }.get(dominant, "epic")

    game = game_name or "the game"
    streamer = streamer_name or "the streamer"

    return {
        "title": f"{streamer} goes {excitement.upper()} in {game}!",
        "description": f"An incredible moment from {streamer}'s stream. Chat went crazy!",
        "hashtags": [
            "twitch", "clips", "gaming", "streamer", "viral",
            "twitchclips", "shorts", "funny", excitement,
            game.lower().replace(" ", ""),
        ],
        "excitement_level": excitement,
        "hook": f"You won't believe what just happened on stream...",
    }
