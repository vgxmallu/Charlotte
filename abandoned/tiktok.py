import logging
import re
from pathlib import Path
from typing import List

from ttsave_api import ContentType, TTSave

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import truncate_string
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class TikTokService(BaseService):
    name = "Tiktok"

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        self.output_path = output_path
        self.ttsave_client = TTSave()

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
            saved_files = self.ttsave_client.download(
                url=url,
                content_type=ContentType.Original,
                downloads_dir=self.output_path,
            )

            if saved_files is None:
                raise BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message="Failed to download TikTok. PyTTSave returned empty",
                    critical=False,
                    is_logged=True
                )

            title = saved_files["meta"]["desc"] if saved_files["meta"]["desc"] else ""

            for file in saved_files["files"]:
                if file.endswith(".mp4"):
                    result.append(
                        MediaContent(
                            type=MediaType.VIDEO,
                            path=Path(file),
                            title=truncate_string(title)
                        )
                        )
                elif file.endswith(".jpg") or file.endswith(".png"):
                    result.append(
                        MediaContent(
                            type=MediaType.PHOTO,
                            path=Path(file),
                            title=truncate_string(title)
                        )
                        )
                elif file.endswith(".mp3"):
                    result.append(
                        MediaContent(
                            type=MediaType.AUDIO,
                            path=Path(file)
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
