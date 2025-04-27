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
from ytmusicapi import YTMusic

from services.base_service import BaseService
from utils import random_cookie_file, update_metadata

logger = logging.getLogger(__name__)


_search_executor = ThreadPoolExecutor(max_workers=5)

class YtMusicService(BaseService):
    name = "YTMusic"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path

    def _get_playlist_options(self):
        return {
            "format": "bestaudio",
            "outtmpl": f"{self.output_path}/{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
        }

    def _get_audio_options(self):
        return {
            "format": "bestaudio",
            "outtmpl": f"{self.output_path}/{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                }
            ],
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(
                r"https:\/\/music\.youtube\.com\/(watch\?v=[\w-]+(&[\w=-]+)*|playlist\?list=[\w-]+(&[\w=-]+)*)",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        return bool(re.match(r"https:\/\/music\.youtube\.com\/playlist\?list=[\w-]+(&[\w=-]+)*", url))

    def supports_format_choice(self) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []

        options = self._get_audio_options()
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                # Получаем информацию и сразу скачиваем
                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=True)
                )
                if not info_dict:
                    raise ValueError("Failed to get audio info")

                base_path = os.path.join(
                    self.output_path,
                    f"{sanitize_filename(info_dict['title'])}"
                )
                audio_path = f"{base_path}.mp3"
                cover_path = f"{base_path}.jpg"

                # Скачивание cover изображения
                cover_url = info_dict.get("thumbnail", None)
                if cover_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(cover_url) as response:
                            response.raise_for_status()
                            async with aiofiles.open(cover_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    await f.write(chunk)

                # Обновление метаданных
                await loop.run_in_executor(
                    self._download_executor,
                    lambda: update_metadata(
                        audio_path,
                        title=info_dict.get("title", "audio"),
                        artist=info_dict.get("uploader", "unknown"),
                        cover_file=cover_path
                    )
                )

                if await aios.path.exists(audio_path) and await aios.path.exists(cover_path):
                    result.append(
                        {"type": "audio", "path": audio_path, "cover": cover_path}
                    )
            return result

        except Exception as e:
            logger.error(f"Error downloading YouTube Audio: {str(e)}")
            return [{
                "type": "error",
                "message": str(e)
            }]


    async def get_playlist_tracks(self, url: str) -> list[str]:
        tracks = []
        try:
            yt = await asyncio.get_event_loop().run_in_executor(
                _search_executor,
                YTMusic
            )

            match = re.search(r'list=([\w-]+)', url)

            if match:
                playlist_id = match.group(1)

                playlist_entries = yt.get_playlist(playlist_id, limit=None)
                for entry in playlist_entries['tracks']:
                    videoid = entry.get('videoId', None)
                    if not videoid:
                        continue
                    tracks.append(f"https://music.youtube.com/watch?v={videoid}")
            else:
                raise ValueError(f"Invalid playlist URL: {url}")
        except Exception as e:
            logger.error(f"Error fetching playlist tracks: {e}")
        return tracks
