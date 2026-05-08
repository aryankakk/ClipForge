import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TWITCH_API_BASE = "https://api.twitch.tv/helix"
TWITCH_AUTH_BASE = "https://id.twitch.tv/oauth2"


class TwitchAPIClient:
    def __init__(self, access_token: str, refresh_token: str = None, streamer_id: str = None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.streamer_id = streamer_id
        self._app_token: Optional[str] = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Client-Id": settings.TWITCH_CLIENT_ID,
        }

    async def _app_headers(self) -> dict:
        if not self._app_token:
            self._app_token = await self._get_app_token()
        return {
            "Authorization": f"Bearer {self._app_token}",
            "Client-Id": settings.TWITCH_CLIENT_ID,
        }

    async def _get_app_token(self) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TWITCH_AUTH_BASE}/token",
                params={
                    "client_id": settings.TWITCH_CLIENT_ID,
                    "client_secret": settings.TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def refresh_access_token(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TWITCH_AUTH_BASE}/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": settings.TWITCH_CLIENT_ID,
                    "client_secret": settings.TWITCH_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self.refresh_token = data.get("refresh_token", self.refresh_token)
            return data

    async def get_user(self) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{TWITCH_API_BASE}/users", headers=self._headers())
            resp.raise_for_status()
            return resp.json()["data"][0]

    async def get_stream(self, broadcaster_id: str) -> Optional[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TWITCH_API_BASE}/streams",
                params={"user_id": broadcaster_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return data[0] if data else None

    async def create_clip(self, broadcaster_id: str) -> Optional[dict]:
        """Create a clip via Twitch API. Returns clip edit_url and id."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{TWITCH_API_BASE}/clips",
                params={"broadcaster_id": broadcaster_id},
                headers=self._headers(),
            )
            if resp.status_code == 401:
                await self.refresh_access_token()
                resp = await client.post(
                    f"{TWITCH_API_BASE}/clips",
                    params={"broadcaster_id": broadcaster_id},
                    headers=self._headers(),
                )
            resp.raise_for_status()
            data = resp.json()["data"]
            return data[0] if data else None

    async def get_clip(self, clip_id: str) -> Optional[dict]:
        """Fetch clip metadata from Twitch (includes thumbnail_url, duration, etc)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{TWITCH_API_BASE}/clips",
                params={"id": clip_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return data[0] if data else None

    async def get_channel_info(self, broadcaster_id: str) -> Optional[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{TWITCH_API_BASE}/channels",
                params={"broadcaster_id": broadcaster_id},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return data[0] if data else None


# ─── EventSub registration ────────────────────────────────────────────────────

async def register_eventsub(broadcaster_id: str) -> dict:
    """Register EventSub subscriptions for a broadcaster."""
    app_token = await _get_app_token_static()
    headers = {
        "Authorization": f"Bearer {app_token}",
        "Client-Id": settings.TWITCH_CLIENT_ID,
        "Content-Type": "application/json",
    }
    callback_url = f"{settings.BACKEND_URL}/api/webhooks/twitch"

    subscriptions = [
        ("stream.online", "1", {"broadcaster_user_id": broadcaster_id}),
        ("stream.offline", "1", {"broadcaster_user_id": broadcaster_id}),
        ("channel.subscribe", "1", {"broadcaster_user_id": broadcaster_id}),
        ("channel.cheer", "1", {"broadcaster_user_id": broadcaster_id}),
        ("channel.raid", "1", {"to_broadcaster_user_id": broadcaster_id}),
        ("channel.channel_points_custom_reward_redemption.add", "1", {"broadcaster_user_id": broadcaster_id}),
    ]

    results = []
    async with httpx.AsyncClient() as client:
        for event_type, version, condition in subscriptions:
            try:
                resp = await client.post(
                    f"{TWITCH_API_BASE}/eventsub/subscriptions",
                    headers=headers,
                    json={
                        "type": event_type,
                        "version": version,
                        "condition": condition,
                        "transport": {
                            "method": "webhook",
                            "callback": callback_url,
                            "secret": settings.TWITCH_WEBHOOK_SECRET,
                        },
                    },
                )
                if resp.status_code not in (200, 202, 409):  # 409 = already exists
                    logger.warning(f"EventSub sub failed for {event_type}: {resp.text}")
                else:
                    results.append({"type": event_type, "status": "ok"})
            except Exception as e:
                logger.error(f"Failed to register EventSub {event_type}: {e}")
    return {"subscriptions": results}


async def _get_app_token_static() -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TWITCH_AUTH_BASE}/token",
            params={
                "client_id": settings.TWITCH_CLIENT_ID,
                "client_secret": settings.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def build_oauth_url(state: str) -> str:
    scopes = [
        "clips:edit",
        "channel:read:subscriptions",
        "bits:read",
        "channel:read:redemptions",
        "chat:read",
        "user:read:email",
        "moderator:read:chat_settings",
    ]
    params = httpx.QueryParams({
        "client_id": settings.TWITCH_CLIENT_ID,
        "redirect_uri": settings.TWITCH_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "force_verify": "false",
    })
    return f"{TWITCH_AUTH_BASE}/authorize?{params}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TWITCH_AUTH_BASE}/token",
            data={
                "client_id": settings.TWITCH_CLIENT_ID,
                "client_secret": settings.TWITCH_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.TWITCH_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()
