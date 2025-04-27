import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

import aiofiles
import aiohttp
import yt_dlp
from aiofiles import os as aios
from bs4 import BeautifulSoup
from yt_dlp.utils import sanitize_filename

from utils import (
    get_applemusic_author,
    random_cookie_file,
    search_music,
    update_metadata,
)

from services.base_service import BaseService

logger = logging.getLogger(__name__)


class AppleMusicService(BaseService):
    name = "AppleMusic"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def _get_audio_options(self):
        return {
            "format": "bestaudio",
            "writethumbnail": True,
            "outtmpl": f"{self.output_path}/{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                },
            ],
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/music\.apple\.com\/[\w]{2}\/(song\/([\w-]+)\/(\d+)|album\/([^\/]+)\/(\d+)(\?i=(\d+))?|playlist\/([\w-]+)\/([\w.-]+))", url)
        )

    def is_playlist(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/music\.apple\.com\/[\w]{2}\/playlist\/([\w-]+)\/([\w.-]+)", url)
        )
    async def download(self, url: str) -> list:
        result = []

        options = self._get_audio_options()
        try:
            artist, title, cover_url = await get_applemusic_author(url)

            video_link = await search_music(artist, title)

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

                async with aiohttp.ClientSession() as session:
                    async with session.get(cover_url) as response:
                        response.raise_for_status()
                        async with aiofiles.open(cover_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(1024):
                                await f.write(chunk)

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
            logger.error(f"Error downloading YouTube Audio: {e}", exc_info=True)
            return [{
                "type": "error",
                "message": e
            }]

    async def get_playlist_tracks(self, url: str) -> list[str]:
        match = re.search(r"playlist/([^/?]+)", url)
        if not match:
            logger.error(f"Invalid playlist URL: {url}")
            return []

        playlist_id = match.group(1)
        logger.info(f"Parsing playlist with ID: {playlist_id}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()

                    soup = BeautifulSoup(await response.text(), 'html.parser')

                    script_tag = soup.find('script', {'id': 'serialized-server-data'})
                    if not script_tag:
                        logger.error("Не удалось найти JSON в странице.")
                        return []

                    json_data = json.loads(script_tag.string)

                    track_urls = []

                    sections = json_data[0].get('data', {}).get('sections', [])
                    for section in sections:
                        if "track-list" in section.get("id", ""):
                            tracks = section.get('items', [])
                            for track in tracks:
                                try:
                                    track_id = track["id"]
                                    match = re.search(r" - (\d+)$", track_id)
                                    if match:
                                        track_id_extracted = match.group(1)
                                        track_urls.append("https://music.apple.com/pl/song/"+track_id_extracted)
                                except (KeyError, IndexError):
                                    logger.warning(f"Не удалось извлечь URL для трека: {track}")

                            break

                    return track_urls

        except aiohttp.ClientError as e:
            logger.error(f"Ошибка при запросе страницы: {e}")
        except json.JSONDecodeError:
            logger.error("Ошибка при декодировании JSON.")

        return []
