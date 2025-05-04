import asyncio
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import aiofiles
import aiohttp
import yt_dlp
from aiofiles import os as aios
from yt_dlp.utils import sanitize_filename

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import random_cookie_file, update_metadata
from utils.error_handler import BotError, ErrorCode


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
        return bool(re.match(r"^https:\/\/(?:on\.soundcloud\.com\/[a-zA-Z0-9]+|soundcloud\.com\/[^\/]+\/(sets\/[^\/]+|[^\/\?\s]+))(?:\?.*)?$", url))

    def is_playlist(self, url: str) -> bool:
        return bool(
            re.match(r"^https?:\/\/(www\.)?soundcloud\.com\/[\w\-]+\/sets\/[\w\-]+$", url)
        )

    async def download(self, url: str) -> List[MediaContent]:
        options = self._get_audio_options()
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info_dict:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="SoundCloud: Failed to fetch track info",
                        url=url,
                        critical=False,
                        is_logged=True
                    )

                title = info_dict.get("title")
                if title is None:
                    title = ""

                permofer = info_dict.get("uploader")
                if permofer is None:
                    permofer = ""

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

                if cover_url:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(cover_url) as response:
                                response.raise_for_status()
                                cover_path = f"{base_path}.jpg"
                                async with aiofiles.open(cover_path, 'wb') as f:
                                    async for chunk in response.content.iter_chunked(1024):
                                        await f.write(chunk)

                        if not await aios.path.exists(cover_path):
                            cover_path = None

                    except Exception:
                        cover_path = None

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: update_metadata(
                        audio_path,
                        title=title,
                        artist=permofer,
                        cover_file=cover_path
                    )
                )

                if await aios.path.exists(audio_path):
                    return [MediaContent(
                        type=MediaType.AUDIO,
                        path=Path(audio_path),
                        duration=info_dict.get("duration", None),
                        title=title,
                        performer=permofer,
                        cover=Path(cover_path) if cover_path else None
                    )]
                else:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="Audio file not found after download",
                        url=url,
                        is_logged=True
                    )

        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"SoundCloud: {e}",
                url=url,
                critical=True,
                is_logged=True
            )

    async def get_playlist_tracks(self, url: str) -> list[str]:
        # SoundCloud playlist URLs must contain '/sets/'
        if not self.is_playlist(url):
            raise BotError(
                code=ErrorCode.INVALID_URL,
                message=f"Invalid SoundCloud playlist URL: {url}",
                url=url,
                critical=False,
                is_logged=False
            )

        try:
            options = {"noplaylist": False, "extract_flat": True}
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()
                info = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info or "entries" not in info:
                    raise BotError(
                        code=ErrorCode.PLAYLIST_INFO_ERROR,
                        message="Failed to fetch playlist info",
                        url=url,
                        critical=True,
                        is_logged=False
                    )

                tracks = [
                    entry["url"]
                    for entry in info["entries"]
                    if entry.get("url")
                ]
                return tracks

        except BotError:
            raise
        except Exception as e:
            raise BotError(
                code=ErrorCode.PLAYLIST_INFO_ERROR,
                message=f"Error extracting SoundCloud playlist tracks: {e}",
                url=url,
                critical=True,
                is_logged=False
            )

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
