import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from aiofiles import os as aios
from bilix.sites.bilibili import DownloaderBilibili

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class BiliBiliService(BaseService):
    name = "BiliBili"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r"https?://(?:www\.)?bilibili\.(?:com|tv)/[\w/?=&]+", url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        try:
            async with DownloaderBilibili() as d:
                video_path =  await d.get_video(url, path=Path("other/downloadsTemp"),time_range=(0, 180))


            if video_path and await aios.path.exists(video_path):
                return [MediaContent(
                    type=MediaType.VIDEO,
                    path=Path(video_path),
                )]
            else:
                raise BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message="Video file not found after download. BiliBili",
                    url=url,
                    is_logged=True
                )

        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Bilibili: {e}",
                url=url,
                critical=False,
                is_logged=True,
            )
