import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple, Union

import aiofiles
import aiohttp
import yt_dlp
from yt_dlp.utils import sanitize_filename

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import random_cookie_file, update_metadata
from utils.error_handler import BotError, ErrorCode
from config.settings import LOCAL_SERVER

logger = logging.getLogger(__name__)


class YouTubeService(BaseService):
    name = "Youtube"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path

    def _get_video_options(self):
        return {
            "format": "bv*[filesize < 50M][ext=mp4][vcodec^=avc1] + ba[ext=m4a]",
            "outtmpl": f"{self.output_path}/%(id)s_{sanitize_filename('%(title)s')}.%(ext)s",
            "noplaylist": True,
            "cookiefile": random_cookie_file(),
        }

    def _get_audio_options(self):
        return {
            "format": "ba[filesize<50M][acodec^=mp4a]/ba[filesize<50M][acodec=opus]/best[filesize<50M]",
            "outtmpl": f"{self.output_path}/%(id)s_{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
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
                r"https?://(?:www\.)?(?:m\.)?(?:youtu\.be/|youtube\.com/(?:shorts/|watch\?v=))([\w-]+)",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        return False

    def supports_format_choice(self) -> bool:
        return True

    async def download(self, url: str, format_choice: Optional[str] = None) -> List[MediaContent]:
        if format_choice == "audio":
            return await self.download_audio(url)
        return await self.download_video(url)

    async def download_video(self, url: str) -> List[MediaContent]:
        try:
            is_valid, best_format = await self._check_video_size(url)
            if is_valid is False and best_format is None:
                raise BotError(
                    code=ErrorCode.SIZE_CHECK_FAIL,
                    message="Video size is too large",
                    url=url,
                    critical=False,
                    is_logged=False
                )

            options = self._get_video_options()
            options["format"] = best_format
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )

                if not info_dict:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="Failed to get video info",
                        url=url,
                        critical=True,
                        is_logged=True
                    )

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([url])
                )

                return [
                    MediaContent(
                        type=MediaType.VIDEO,
                        path=Path(ydl.prepare_filename(info_dict)),
                        width=info_dict.get("width", None),
                        height=info_dict.get("height", None),
                        duration=info_dict.get("duration", None),
                        title=info_dict.get("title", "video"),
                    )
                ]

        except BotError as e:
            raise e

        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Youtube: {str(e)}",
                url=url,
                critical=True,
                is_logged=True
            )

    async def download_audio(self, url: str) -> List[MediaContent]:
        try:
            is_valid, best_format = await self._check_audio_size(url)
            if is_valid is False or best_format is None:
                raise BotError(
                    code=ErrorCode.SIZE_CHECK_FAIL,
                    message="Audio size is too large",
                    url=url
                )

            options = self._get_audio_options()
            options["format"] = best_format
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_running_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info_dict:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="Failed to get audio info",
                        url=url
                    )

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([url])
                )

                base_path = os.path.join(
                    self.output_path,
                    f"{info_dict['id']}_{sanitize_filename(info_dict['title'])}"
                )
                audio_path = f"{base_path}.mp3"
                thumbnail_path = f"{base_path}.jpg"

                thumbnail_url = info_dict.get("thumbnail", None)
                if thumbnail_url:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(thumbnail_url) as response:
                            response.raise_for_status()
                            async with aiofiles.open(thumbnail_path, 'wb') as f:
                                async for chunk in response.content.iter_chunked(1024):
                                    await f.write(chunk)

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: update_metadata(
                        audio_path,
                        title=info_dict.get("title", "audio"),
                        artist=info_dict.get("uploader", "unknown"),
                        cover_file=thumbnail_path
                    )
                )
                return [MediaContent(
                    type=MediaType.AUDIO,
                    path=Path(audio_path),
                    duration=info_dict.get("duration", 0),
                    title=info_dict.get("title", "audio"),
                    cover=Path(thumbnail_path)
                )]
        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"YouTube audio: {str(e)}",
                url=url,
                critical=True,
                is_logged=True
            )


    async def _check_video_size(self, url: str, max_size_mb: int =50) -> Tuple[bool, Union[str, None]]:
        """
        Checks if there is an available option to download video and audio up to a given size (default 50 MB).

        Args:
            url (str): YouTube video URL.
            max_size_mb (int): Maximum allowed size in megabytes.

        Returns:
            Tuple[bool, Optional[str]]:
            - (True, format string like '137+140') if a suitable pair is found.
            - (False, None) otherwise.
        """
        ydl_opts = {
            'skip_download': True,
            'force_ipv4': True,
            'quiet': True,
            "cookiefile": random_cookie_file(),
        }
        if LOCAL_SERVER:
            max_size_mb = 100
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                loop = asyncio.get_running_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )

            if not info_dict:
                return False, None

            formats = info_dict.get('formats', [])
            video_formats = []
            audio_formats = []

            for f in formats:
                ext = f.get('ext')
                vcodec = f.get('vcodec', '')
                acodec = f.get('acodec', '')
                filesize = f.get('filesize') or f.get('filesize_approx')

                if not filesize:
                    continue

                if vcodec != 'none' and vcodec and ext == "mp4":
                    if vcodec.startswith('avc1'):
                        video_formats.append(f)
                if acodec != 'none' and vcodec == "none" and acodec.startswith('mp4a'):
                    audio_formats.append(f)

            best_pair = None
            best_score = (-1, -1)

            for v in video_formats:
                for a in audio_formats:
                    v_size = v.get('filesize') or v.get('filesize_approx') or 0
                    a_size = a.get('filesize') or a.get('filesize_approx') or 0

                    total_size_mb = (v_size + a_size) / (1024 * 1024)

                    if total_size_mb <= max_size_mb:
                        score = (
                            v.get('height', 0),
                            a.get('abr', 0)
                        )
                        if score > best_score:
                            best_score = score
                            best_pair = f'{v["format_id"]}+{a["format_id"]}'

            if best_pair:
                return True, best_pair
            else:
                return False, None
        except Exception as e:
            if isinstance(e, yt_dlp.utils.DownloadError):
                error_msg = str(e).lower()

                if "private video" in error_msg or "this video is private" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is private",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "sign in to confirm your age" in error_msg or "age-restricted" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is age-restricted",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "video unavailable" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is unavailable",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "this video is no longer available" in error_msg or "has been removed" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video has been removed",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "unavailable in your country" in error_msg or "not available in your country" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is geo-blocked",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "no video formats" in error_msg or "requested format not available" in error_msg:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="No suitable video format found",
                        url=url,
                        critical=True,
                        is_logged=True
                    )
                else:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message=f"yt-dlp error: {str(e)}",
                        url=url,
                        critical=True,
                        is_logged=True
                    )
            else:
                return False, None


    async def _check_audio_size(self, url: str, max_size_mb: int =50) -> Tuple[bool, Union[str, None]]:
        """
        Checks if there is an available option to download audio up to a given size (default 50 MB).

        Args:
            url (str): YouTube video URL.
            max_size_mb (int): Maximum allowed size in megabytes.

        Returns:
            Tuple[bool, Optional[str]]:
            - (True, format string like '251') if a suitable format is found.
            - (False, None) otherwise.
        """
        ydl_opts = {
            'skip_download': True,
            'force_ipv4': True,
            'quiet': True,
            "format": "ba[filesize<50M][acodec^=mp4a]/ba[filesize<50M][acodec=opus]/best[filesize<50M]",
            "cookiefile": random_cookie_file(),
        }
        if LOCAL_SERVER:
            ydl_opts["format"] = "ba[filesize<100M][acodec^=mp4a]/ba[filesize<100M][acodec=opus]/best[filesize<100M]"
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                loop = asyncio.get_running_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info_dict or not info_dict.get("formats"):
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is unavailable or private",
                        url=url,
                        critical=False,
                        is_logged=False
                    )

            if not info_dict:
                return False, None

            best_format =  info_dict.get('format_id', None)

            if best_format:
                return True, best_format
            else:
                return False, None
        except BotError as e:
            raise e
        except Exception as e:
            if isinstance(e, yt_dlp.utils.DownloadError):
                error_msg = str(e).lower()

                if "private video" in error_msg or "this video is private" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is private",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "sign in to confirm your age" in error_msg or "age-restricted" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is age-restricted",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "video unavailable" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is unavailable",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "this video is no longer available" in error_msg or "has been removed" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video has been removed",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "unavailable in your country" in error_msg or "not available in your country" in error_msg:
                    raise BotError(
                        code=ErrorCode.INVALID_URL,
                        message="Video is geo-blocked",
                        url=url,
                        critical=False,
                        is_logged=False
                    )
                elif "no video formats" in error_msg or "requested format not available" in error_msg:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="No suitable video format found",
                        url=url,
                        critical=True,
                        is_logged=True
                    )
                else:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message=f"yt-dlp error: {str(e)}",
                        url=url,
                        critical=True,
                        is_logged=True
                    )
            else:
                return False, None