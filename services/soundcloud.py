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

from utils import random_cookie_file, update_metadata

from .base_service import BaseService


class SoundCloudService(BaseService):
    name = "SoundCloud"
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
        return bool(re.match(r"https?://soundcloud\.com/([\w-]+)/([\w-]+)", url))

    def is_playlist(self, url: str) -> bool:
        return bool(
            re.match(r"^https?:\/\/(www\.)?soundcloud\.com\/[\w\-]+\/sets\/[\w\-]+$", url)
        )

    async def download(self, url: str) -> list:
        result = []

        options = self._get_audio_options()
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info_dict:
                    raise ValueError("Failed to get audio info")

                title = info_dict.get("title")
                if title is None:
                    title = ""

                artist = info_dict.get("uploader")
                if artist is None:
                    artist = ""

                cover_url = self._get_cover_url(info_dict)

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([url])
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
            logging.error(f"Error downloading YouTube Audio: {str(e)}")
            return [{
                "type": "error",
                "message": e
            }]

    async def get_playlist_tracks(self, url: str) -> list[str]:
        """
        Extracts all track URLs from a SoundCloud playlist.

        Args:
            url (str): The URL of the SoundCloud playlist.

        Returns:
            list[str]: A list of track URLs. Returns None if there is an error.
        """
        try:
            options = {"noplaylist": False, "extract_flat": True}

            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                playlist_info = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not playlist_info:
                    raise ValueError("Failed to get audio info")

            track_urls = [
                entry.get("url")
                for entry in playlist_info.get("entries", [])
                if entry.get("url")
            ]

            return track_urls

        except Exception as e:
            logging.error(f"Error extracting track URLs from playlist: {e}")
            return []

    def _get_cover_url(self, info_dict: dict):
        """
        Extracts the cover URL from the track's information.

        Parameters:
        ----------
        info_dict : dict
            The information dictionary for the SoundCloud track.

        Returns:
        -------
        str or None
            The URL of the cover image, or None if no appropriate image is found.
        """
        thumbnails = info_dict.get("thumbnails", [])
        return next(
            (
                thumbnail["url"]
                for thumbnail in thumbnails
                if thumbnail.get("width") == 500
            ),
            None,
        )
