import logging
import re
from pathlib import Path
from typing import List
import yt_dlp
import asyncio

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import truncate_string
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class TikTokService(BaseService):
    name = "Tiktok"

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        self.output_path = output_path
        self.yt_dlp_video_options = {
            "format": "mp4",
            "outtmpl": f"{output_path}/%(title)s.%(ext)s",
        }

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(
                r"https?://(?:www\.)?(?:tiktok\.com/.*|(vm|vt)\.tiktok\.com/.+)", url
            )
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        result = []
        try:
            with yt_dlp.YoutubeDL(self.yt_dlp_video_options) as ydl:
                info_dict = await asyncio.to_thread(ydl.extract_info, url, download=False)
                filename = ydl.prepare_filename(info_dict)
                await asyncio.to_thread(ydl.download, [url])

            result.append(
                MediaContent(
                    type=MediaType.VIDEO,
                    path=Path(filename),
                    title=truncate_string(info_dict["title"])
                )
            )

            return result
        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"TikTok: {str(e)}",
                critical=False,
                is_logged=True
            )
