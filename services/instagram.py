from .base_service import BaseService
import re
import logging
import os

import aiofiles
import aiohttp
from utils import login_user, truncate_string

class InstagramService(BaseService):
    name = "Instagram"
    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r'https://www\.instagram\.com/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)/', url))

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> list:
        result = []
        try:
            cl = login_user()

            media_urls = []
            media_types = []
            temp_medias = []

            media_pk = cl.media_pk_from_url(url)
            media = cl.media_info(media_pk)

            if media.media_type == 8:  # GraphSidecar (multiple photos or videos)
                for i, resource in enumerate(media.resources):
                    media_urls.append(resource.thumbnail_url if resource.media_type == 1 else resource.video_url)
                    media_types.append("photo" if resource.media_type == 1 else "video")
            elif media.media_type == 1:  # GraphImage (single image)
                media_urls.append(media.thumbnail_url)
                media_types.append("photo")
            elif media.media_type == 2:  # GraphVideo (single video)
                media_urls.append(media.video_url)
                media_types.append("video")

            for i, (media_url, media_type) in enumerate(zip(media_urls, media_types)):
                filename_ext = ".jpg" if media_type == "photo" else ".mp4"
                media_filename = os.path.join(self.output_path, f"{media_pk}_{i}{filename_ext}")

                async with aiohttp.ClientSession() as session:
                    async with session.request("GET", url=str(media_url)) as response:
                        if response.status == 200:
                            async with aiofiles.open(media_filename, "wb") as file:
                                await file.write(await response.read())
                                temp_medias.append(media_filename)
                            if media_type == "photo":
                                result.append({"type": "image", "path": media_filename, "title": truncate_string(media.caption_text)})
                            else:
                                result.append({"type": "video", "path": media_filename, "title": truncate_string(media.caption_text)})
                        else:
                            print(f"Failed to download media: {media_url}")

            return result

        except Exception as e:
            logging.error(f"Error downloading Instagram media: {str(e)}")
            return result
