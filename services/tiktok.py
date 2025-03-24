from .base_service import BaseService
import re
import logging
from ttsave_api import TTSave, ContentType


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

    async def download(self, url: str) -> list:
        result = []
        try:
            saved_files = self.ttsave_client.download(
                url=url,
                content_type=ContentType.Original,
                downloads_dir=self.output_path,
            )

            if saved_files is None:
                raise ValueError("Failed to download TikTok content")

            for file in saved_files["files"]:
                if file.endswith(".mp4"):
                    result.append({"type": "video", "path": file})
                elif file.endswith(".jpg") or file.endswith(".png"):
                    result.append({"type": "image", "path": file})
                elif file.endswith(".mp3"):
                    result.append({"type": "audio", "path": file, "cover": None})

            title = saved_files["meta"]["desc"] if saved_files["meta"]["desc"] else ""

            result.append({"type": "title", "title": title})

            return result

        except Exception as e:
            logging.error(f"Error downloading TikTok: {str(e)}")
            return result
