# ⚡ ClipForge — AI Twitch Clipping System

Automatically detects and clips highlight moments from Twitch streams, then converts them to vertical TikTok/Reels/Shorts format.

## Architecture

```
Twitch Stream
     │
     ├── EventSub Webhooks ─────→ FastAPI Backend
     │       (stream.online,          │
     │        channel.raid, subs)     │
     │                                ├── Stream Manager
     ├── Chat IRC/WS ──────────→      │       ├── Chat Monitor (IRC WebSocket)
     │                                │       └── Highlight Scorer (Redis)
     └── Twitch Clip API ←────────────┤
                                      │   When score ≥ threshold:
                                      ├── Twitch Create Clip API
                                      ├── Video Worker (FFmpeg)
                                      │       ├── Download raw clip
                                      │       ├── Whisper transcription
                                      │       ├── GPT title/hashtags
                                      │       └── 9:16 vertical crop
                                      └── PostgreSQL + Redis
                                               │
                                        Next.js Dashboard
                                        (WebSocket live score)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12, asyncio |
| Database | PostgreSQL 16 (SQLAlchemy async) |
| Cache/Queue | Redis 7 (pub/sub + job queue) |
| Video | FFmpeg (crop, captions, 9:16) |
| AI/STT | OpenAI Whisper + GPT-4o-mini |
| Infra | Docker Compose |

## Scoring System

Every 30 seconds, all events are aggregated and scored:

| Event | Score |
|---|---|
| Chat velocity spike (3x baseline) | +5–30 |
| Hype keyword (CLIP, OMG, NO WAY) | +8 per message |
| Emote (PogChamp, KEKW, OMEGALUL) | +6 per message |
| ALL CAPS message | +5 |
| Subscription | +25 |
| Gift sub | +20 |
| Gift bomb (5+) | +40 |
| Raid | +30–50 |
| Bits/Cheer (1000+) | +35 |
| Channel points | +10 |

**Default threshold: 60 points → triggers a clip**

## Quick Start

### 1. Twitch Developer Setup

1. Go to https://dev.twitch.tv/console
2. Create a new Application
3. Set OAuth Redirect URL to: `http://localhost:8000/api/auth/callback`
4. Copy Client ID and Client Secret

### 2. ngrok (for EventSub webhooks)

Twitch EventSub requires a public HTTPS URL for webhooks.

```bash
# Install ngrok: https://ngrok.com
ngrok http 8000
# Copy the https URL (e.g. https://abc123.ngrok.io)
```

### 3. Configure Environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your values:
# TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_WEBHOOK_SECRET
# BACKEND_URL=https://abc123.ngrok.io
# OPENAI_API_KEY=sk-... (optional)
```

### 4. Run with Docker

```bash
docker-compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 5. First Login

1. Open http://localhost:3000
2. Click "Connect with Twitch"
3. Authorize the app
4. You'll be redirected to the dashboard

## Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Configure your .env

# Start PostgreSQL and Redis (or use Docker for just those):
docker-compose up postgres redis -d

uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

## How Clipping Works

1. **Stream goes live** → Twitch EventSub fires `stream.online` → `start_stream_session()` called
2. **Chat monitor connects** to Twitch IRC via WebSocket
3. **Every message** is scored for hype keywords, emotes, ALL CAPS
4. **Every 30s**, the scorer aggregates all Redis events:
   - If total ≥ 60 AND not on cooldown → create clip
5. **Twitch Create Clip API** creates the clip
6. **Video worker** picks up approved clips:
   - Downloads raw MP4
   - Whisper transcribes audio
   - GPT-4o-mini generates title + hashtags
   - FFmpeg crops to 9:16, burns in subtitles
7. **Dashboard** shows clips for human review

## Configuration

Key env vars in `backend/.env`:

```bash
CLIP_SCORE_THRESHOLD=60.0    # Score needed to trigger a clip
SCORE_WINDOW_SECONDS=30      # How often to evaluate the score
COOLDOWN_SECONDS=90          # Min time between clips
CHAT_VELOCITY_WINDOW=10      # Seconds to measure chat rate
CHAT_SPIKE_MULTIPLIER=3.0    # x above baseline = spike
```

## Project Structure

```
twitch-clipper/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app + WebSocket
│   │   ├── core/
│   │   │   ├── config.py              # Settings (pydantic)
│   │   │   ├── database.py            # Async SQLAlchemy
│   │   │   └── redis_client.py        # Redis helpers
│   │   ├── models/models.py           # Streamer, Stream, Clip
│   │   ├── api/routes/
│   │   │   ├── auth.py                # Twitch OAuth
│   │   │   ├── clips.py               # Clip CRUD
│   │   │   ├── streams.py             # Stream status
│   │   │   └── webhooks.py            # EventSub handler
│   │   ├── services/
│   │   │   ├── twitch_api.py          # Twitch REST client
│   │   │   ├── chat_monitor.py        # IRC WebSocket
│   │   │   ├── highlight_scorer.py    # Score aggregation
│   │   │   ├── clip_creator.py        # Create + store clips
│   │   │   ├── video_processor.py     # FFmpeg pipeline
│   │   │   ├── ai_service.py          # Whisper + GPT
│   │   │   └── stream_manager.py      # Session lifecycle
│   │   └── workers/
│   │       └── video_worker.py        # Redis queue worker
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx               # Landing + OAuth
│       │   ├── dashboard/page.tsx     # Main dashboard
│       │   ├── clips/page.tsx         # Clip review queue
│       │   └── auth/callback/page.tsx # OAuth callback
│       ├── components/
│       │   ├── ClipCard.tsx           # Clip with controls
│       │   ├── LiveMonitor.tsx        # Real-time score
│       │   └── Navigation.tsx
│       └── lib/
│           ├── api.ts                 # API client
│           └── types.ts               # TypeScript types
├── docker-compose.yml
└── README.md
```

## Phase 2 Additions (with Claude Code)

When you're ready to extend, here's what to build next:

### Audio Analysis
```bash
# Add to backend/app/services/
# audio_monitor.py - tap stream audio via streamlink, analyze with librosa
pip install streamlink librosa soundfile
```

### Deepgram Real-time STT
```python
# Replace Whisper batch transcription with streaming STT
# DEEPGRAM_API_KEY in .env
# Much faster - transcription as streamer speaks
```

### Auto-posting to TikTok/Instagram
```python
# backend/app/services/social_poster.py
# TikTok API v2: https://developers.tiktok.com/
# Instagram Graph API for Reels
```

### Semantic Re-scoring
```python
# After Whisper transcribes, use GPT to re-score the transcript
# ai_service.semantic_score_transcript() is already implemented!
# Wire it into the video worker to upgrade/downgrade clips
```

### Game-specific Detection
```python
# backend/app/services/game_detector.py
# Use Twitch's game API + OpenCV screenshot analysis
# Detect: kill, death, win/loss screens per game
```

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/auth/login` | Get Twitch OAuth URL |
| GET | `/api/auth/callback` | OAuth callback (redirects) |
| GET | `/api/auth/me?token=` | Get current user |
| GET | `/api/streams/status?token=` | Stream status + scores |
| GET | `/api/clips/?token=` | List clips (filter, paginate) |
| POST | `/api/clips/{id}/approve` | Approve clip → video queue |
| POST | `/api/clips/{id}/reject` | Reject clip |
| PATCH | `/api/clips/{id}/title` | Update AI-generated title |
| GET | `/api/clips/{id}/download` | Download processed MP4 |
| POST | `/api/webhooks/twitch` | EventSub receiver |
| WS | `/ws/{broadcaster_login}` | Real-time score stream |

## Troubleshooting

**EventSub not firing?**
- Make sure `BACKEND_URL` is your ngrok URL (public HTTPS)
- Check `/api/webhooks/twitch` is reachable from the internet
- Re-login to trigger `register_eventsub()` again

**Clips not creating?**
- Check your Twitch OAuth token has `clips:edit` scope
- Streamers need to be live for 30+ seconds before clips work
- Check backend logs: `docker-compose logs backend -f`

**Video processing failing?**
- FFmpeg must be installed in the container (it is via Dockerfile)
- Twitch clip URLs can change format — check `video_processor.py`

**Score never reaches threshold?**
- Lower `CLIP_SCORE_THRESHOLD` in `.env` for testing
- Use `CLIP_SCORE_THRESHOLD=20` to test with minimal activity
