from .base_service import BaseService
import logging
import os
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

import yt_dlp


class BiliBiliService(BaseService):
    name = "BiliBili"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def _get_video_options(self):
        return {
            "format": "bv*[filesize < 50M][ext=mp4] + ba/w",
            "outtmpl": f"{self.output_path}/%(title)s.%(ext)s",
        }

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r"https?://(?:www\.)?bilibili\.(?:com|tv)/[\w/?=&]+", url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []

        try:
            options = self._get_video_options()
            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(url, download=False)
                )
                if not info_dict:
                    raise ValueError("Failed to get video info")

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([url])
                )

                return [{
                    "type": "video",
                    "path": ydl.prepare_filename(info_dict),
                    "title": info_dict.get("title", "video")
                }]
        except yt_dlp.DownloadError as e:
            logging.error(f"Error downloading YouTube video: {str(e)}")
        except Exception as e:
            logging.error(f"Error downloading YouTube video: {str(e)}")

        return result
