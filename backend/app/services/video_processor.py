"""
Video processor - downloads Twitch clips and converts them to vertical 9:16 format
with dynamic captions for TikTok, Reels, and Shorts.
"""
import asyncio
import logging
import os
import re
import httpx
from pathlib import Path
from typing import Optional
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VideoProcessor:
    def __init__(self):
        self.clips_dir = Path(settings.CLIPS_DIR)
        self.processed_dir = Path(settings.PROCESSED_DIR)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    async def download_clip(self, twitch_clip_url: str, clip_id: str) -> Optional[Path]:
        """
        Downloads a Twitch clip from its thumbnail URL.
        Twitch clip URLs follow the pattern:
        https://clips-media-assets2.twitch.tv/{clip_id}-preview-480x272.jpg
        → replace with: https://clips-media-assets2.twitch.tv/{clip_id}.mp4
        """
        # Convert thumbnail URL to video URL
        if "preview" in twitch_clip_url:
            video_url = re.sub(r"-preview-\d+x\d+\.jpg$", ".mp4", twitch_clip_url)
        else:
            video_url = twitch_clip_url.replace(".jpg", ".mp4")

        output_path = self.clips_dir / f"{clip_id}_raw.mp4"

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", video_url) as resp:
                    resp.raise_for_status()
                    with open(output_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
            logger.info(f"Downloaded clip: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Failed to download clip {clip_id}: {e}")
            return None

    async def process_for_short(
        self,
        input_path: Path,
        clip_id: str,
        transcript: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Optional[Path]:
        """
        Full pipeline:
        1. Crop to 9:16 with smart content detection
        2. Add dynamic burned-in subtitles
        3. Add title overlay
        4. Export optimized for TikTok
        """
        output_path = self.processed_dir / f"{clip_id}_short.mp4"

        # Step 1: Get video dimensions
        dims = await self._get_dimensions(input_path)
        if not dims:
            return None

        width, height = dims
        logger.info(f"Input dimensions: {width}x{height}")

        # Step 2: Build FFmpeg filter chain
        filter_complex = self._build_filter_chain(width, height, transcript, title)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-r", "30",
            "-movflags", "+faststart",
            "-t", "60",  # Max 60 seconds
            str(output_path),
        ]

        success = await self._run_ffmpeg(cmd)
        if success:
            logger.info(f"Processed clip saved: {output_path}")
            return output_path

        # Fallback: simple crop without captions
        return await self._simple_crop(input_path, clip_id, width, height)

    def _build_filter_chain(
        self,
        width: int,
        height: int,
        transcript: Optional[str],
        title: Optional[str],
    ) -> str:
        """Build FFmpeg filtergraph for vertical video with captions."""

        # Target: 1080x1920 (9:16 TikTok/Reels)
        target_w, target_h = 1080, 1920

        if width > height:
            # Landscape → crop center to 9:16
            # Calculate crop width from height
            crop_w = int(height * 9 / 16)
            crop_x = (width - crop_w) // 2
            crop_filter = f"crop={crop_w}:{height}:{crop_x}:0"
        else:
            # Already portrait or square
            crop_h = int(width * 16 / 9)
            crop_y = max(0, (height - crop_h) // 2)
            crop_filter = f"crop={width}:{crop_h}:0:{crop_y}"

        scale_filter = f"scale={target_w}:{target_h}"

        filters = [crop_filter, scale_filter]

        # Add title overlay at top
        if title:
            safe_title = title.replace("'", "\\'").replace(":", "\\:")[:60]
            filters.append(
                f"drawtext=text='{safe_title}'"
                f":fontsize=48:fontcolor=white"
                f":x=(w-text_w)/2:y=80"
                f":shadowcolor=black:shadowx=3:shadowy=3"
                f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            )

        # Add transcript as subtitles at bottom
        if transcript and len(transcript) > 5:
            # Split transcript into chunks of ~6 words
            words = transcript.split()
            chunks = [" ".join(words[i:i+6]) for i in range(0, len(words), 6)]
            chunk_duration = 2.5  # seconds per chunk

            for i, chunk in enumerate(chunks[:20]):  # Max 20 chunks
                safe_chunk = chunk.replace("'", "\\'").replace(":", "\\:")
                start_t = i * chunk_duration
                end_t = start_t + chunk_duration
                filters.append(
                    f"drawtext=text='{safe_chunk}'"
                    f":fontsize=52:fontcolor=white"
                    f":x=(w-text_w)/2:y=h-200"
                    f":shadowcolor=black:shadowx=4:shadowy=4"
                    f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                    f":enable='between(t\\,{start_t:.1f}\\,{end_t:.1f})'"
                )

        filter_str = ",".join(filters)
        return f"[0:v]{filter_str}[vout]"

    async def _simple_crop(
        self, input_path: Path, clip_id: str, width: int, height: int
    ) -> Optional[Path]:
        """Fallback: simple center-crop to 9:16."""
        output_path = self.processed_dir / f"{clip_id}_short.mp4"
        if width > height:
            crop_w = int(height * 9 / 16)
            crop_x = (width - crop_w) // 2
            vf = f"crop={crop_w}:{height}:{crop_x}:0,scale=1080:1920"
        else:
            vf = f"scale=1080:1920"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        success = await self._run_ffmpeg(cmd)
        return output_path if success else None

    async def _get_dimensions(self, path: Path) -> Optional[tuple[int, int]]:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            str(path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        import json
        data = json.loads(stdout)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream["width"], stream["height"]
        return None

    async def _run_ffmpeg(self, cmd: list) -> bool:
        logger.info(f"FFmpeg: {' '.join(cmd[:6])}...")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"FFmpeg failed: {stderr.decode()[-500:]}")
            return False
        return True

    def cleanup_raw(self, clip_id: str):
        raw = self.clips_dir / f"{clip_id}_raw.mp4"
        if raw.exists():
            raw.unlink()
