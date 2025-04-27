import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import aiohttp
import yt_dlp
from aiofiles import os as aios
from yt_dlp.utils import sanitize_filename

from services.base_service import BaseService
from utils import (
    get_access_token,
    get_spotify_author,
    random_cookie_file,
    search_music,
    update_metadata,
)

logger = logging.getLogger(__name__)


class SpotifyService(BaseService):
    name = "Spotify"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def _get_audio_options(self):
        return {
            "format": "bestaudio",
            "outtmpl": f"{self.output_path}/{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                }
            ],
        }

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r"https?://open\.spotify\.com/(track|playlist)/([\w-]+)", url))

    def is_playlist(self, url: str) -> bool:
        return bool(re.match(r"https?://open\.spotify\.com/playlist/([\w-]+)", url))

    async def download(self, url: str) -> list:
        result = []

        artist, title, cover_url = await get_spotify_author(url)
        if not artist or not title:
            logger.error("Failed to get artist and title from Spotify")
            return result

        video_link = await search_music(artist, title)
        options = self._get_audio_options()
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(video_link, download=False)
                )
                if not info_dict:
                    raise ValueError("Failed to get audio info")

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([video_link])
                )

                base_path = os.path.join(
                    self.output_path,
                    f"{sanitize_filename(info_dict['title'])}"
                )
                audio_path = f"{base_path}.mp3"
                cover_path = f"{base_path}.jpg"

                if cover_url is None:
                    cover_url = info_dict.get("thumbnail", None)

                if cover_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(cover_url) as response:
                            response.raise_for_status()
                            async with aiofiles.open(cover_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    await f.write(chunk)

                assert cover_path, "Cover URL is not available"

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: update_metadata(
                        audio_path,
                        title=title,
                        artist=artist,
                        cover_file=cover_path
                    )
                )

                if await aios.path.exists(audio_path) or await aios.path.exists(cover_path):
                    result.append(
                        {"type": "audio", "path": audio_path, "cover": cover_path}
                    )
            return result

        except Exception as e:
            logger.error(f"Error downloading YouTube Audio: {str(e)}")
            return [{
                "type": "error",
                "message": e
            }]

    async def get_playlist_tracks(self, url: str) -> list[str]:
        tracks = []
        offset = 0

        match = re.search(r"playlist/([^/?]+)", url)
        if not match:
            logger.error(f"Invalid playlist URL: {url}")
            return []

        try:
            async with aiohttp.ClientSession() as session:
                token = await get_access_token(session)
                if not token:
                    return []

                headers = {"Authorization": f"Bearer {token}"}
                params = {"offset": offset}
                playlist_id = match.group(1)
                playlist_url = (f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks")

                async with session.get(
                    playlist_url, headers=headers, params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        for track in data["items"]:
                            tracks.append(track["track"]["external_urls"]["spotify"])

        except Exception as e:
            logger.error(f"Error fetching playlist tracks: {e}")
        return tracks
