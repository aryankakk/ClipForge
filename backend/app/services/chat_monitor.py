"""
Monitors Twitch chat via IRC WebSocket.
Tracks message velocity, emote frequency, and hype keywords.
Emits score events to Redis pub/sub.
"""
import asyncio
import websockets
import logging
import re
import time
from collections import deque
from typing import Optional, Callable
from app.core.config import get_settings
from app.core.redis_client import add_score_event, publish

logger = logging.getLogger(__name__)
settings = get_settings()

TWITCH_IRC_WS = "wss://irc-ws.chat.twitch.tv:443"

# High-signal hype keywords
HYPE_KEYWORDS = {
    "high": [
        "clip", "clip it", "clipper", "clip that", "lmao", "lmfao",
        "no way", "no fucking way", "omg", "wtf", "what", "holy",
        "holy shit", "bro", "gg", "lets go", "let's go", "pog",
        "poggers", "pogchamp", "incredible", "insane", "insane",
    ],
    "medium": [
        "lol", "haha", "hehe", "xd", "XD", "nice", "ez", "rip",
        "F", "oof", "wow", "dang", "damn", "crazy", "sheesh",
    ],
}

# Common Twitch emotes that signal hype
HYPE_EMOTES = {
    "high": ["PogChamp", "Pog", "POGGERS", "KEKW", "LUL", "OMEGALUL",
             "monkaW", "monkaS", "PauseChamp", "Kreygasm", "HYPERS",
             "LETS GO", "catJAM", "OMEGALUL", "LULW", "Sadge"],
    "medium": ["Kappa", "KappaPride", "NotLikeThis", "BibleThump",
               "TriHard", "ResidentSleeper", "4Head", "EleGiggle"],
}


class ChatMonitor:
    def __init__(
        self,
        broadcaster_login: str,
        broadcaster_id: str,
        access_token: str,
        bot_nick: str = "justinfan12345",
    ):
        self.broadcaster_login = broadcaster_login.lower()
        self.broadcaster_id = broadcaster_id
        self.access_token = access_token
        self.bot_nick = bot_nick

        self._running = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None

        # Rolling message window for velocity detection
        self._message_times: deque = deque(maxlen=500)
        self._baseline_rate: float = 0.0
        self._recent_messages: deque = deque(maxlen=30)

        self.on_chat_spike: Optional[Callable] = None

    async def start(self):
        self._running = True
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                logger.error(f"Chat monitor error for {self.broadcaster_login}: {e}")
                if self._running:
                    await asyncio.sleep(5)

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()

    async def _connect(self):
        logger.info(f"Connecting to chat: #{self.broadcaster_login}")
        async with websockets.connect(TWITCH_IRC_WS) as ws:
            self._ws = ws
            # Capabilities: request tags for metadata
            await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            await ws.send(f"PASS oauth:{self.access_token}")
            await ws.send(f"NICK {self.bot_nick}")
            await ws.send(f"JOIN #{self.broadcaster_login}")

            async for raw_message in ws:
                if not self._running:
                    break
                await self._handle_message(raw_message)

    async def _handle_message(self, raw: str):
        if raw.startswith("PING"):
            if self._ws:
                await self._ws.send("PONG :tmi.twitch.tv")
            return

        if "PRIVMSG" not in raw:
            return

        now = time.time()
        self._message_times.append(now)

        # Parse message text
        match = re.search(r"PRIVMSG #\w+ :(.+)", raw)
        if not match:
            return
        text = match.group(1).strip()

        # Parse display name from tags
        display_name = "unknown"
        name_match = re.search(r"display-name=([^;]+)", raw)
        if name_match:
            display_name = name_match.group(1)

        msg_data = {"user": display_name, "text": text, "ts": now}
        self._recent_messages.append(msg_data)

        # Score this message
        score = self._score_message(text)
        if score > 0:
            await add_score_event(self.broadcaster_id, score, "chat_message")
            await publish(f"stream:{self.broadcaster_id}:chat", {
                "user": display_name,
                "text": text,
                "score_contribution": score,
            })

        # Check for velocity spike
        velocity_score = self._check_velocity_spike(now)
        if velocity_score > 0:
            await add_score_event(self.broadcaster_id, velocity_score, "chat_velocity")
            logger.info(f"Chat velocity spike detected: +{velocity_score}")

    def _score_message(self, text: str) -> float:
        score = 0.0
        text_lower = text.lower()

        # High-signal keywords
        for keyword in HYPE_KEYWORDS["high"]:
            if keyword in text_lower:
                score += 8.0
                break

        # Medium keywords
        for keyword in HYPE_KEYWORDS["medium"]:
            if keyword in text_lower:
                score += 3.0
                break

        # Emotes
        for emote in HYPE_EMOTES["high"]:
            if emote in text:
                score += 6.0
                break
        for emote in HYPE_EMOTES["medium"]:
            if emote in text:
                score += 2.0
                break

        # ALL CAPS (screaming = hype)
        if len(text) > 4 and text.upper() == text and not text.startswith("!"):
            score += 5.0

        # Repetition like "LMAOOO" or "NOOO"
        if re.search(r"(.)\1{3,}", text):
            score += 3.0

        return score

    def _check_velocity_spike(self, now: float) -> float:
        """Detect if current message rate is significantly above baseline."""
        window = settings.CHAT_VELOCITY_WINDOW

        # Count messages in current window
        current_count = sum(1 for t in self._message_times if now - t <= window)

        # Update baseline using older window
        old_count = sum(1 for t in self._message_times if window < now - t <= window * 3)
        self._baseline_rate = old_count / (window * 2)

        current_rate = current_count / window

        if self._baseline_rate > 0:
            multiplier = current_rate / self._baseline_rate
            if multiplier >= settings.CHAT_SPIKE_MULTIPLIER:
                return min(30.0, multiplier * 5.0)  # Cap at 30

        return 0.0

    def get_recent_messages(self, n: int = 20) -> list:
        return list(self._recent_messages)[-n:]
