import asyncio
import json
import logging
import os
import random
import re
import urllib.parse
from functools import partial
from pathlib import Path
from typing import List, Tuple

import aiofiles
import aiohttp
import yt_dlp

from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import load_proxies, get_instagram_session
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class InstagramService(BaseService):
    name = "Instagram"

    def __init__(self, output_path: str = "other/downloadsTemp"):
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)

    def is_supported(self, url: str) -> bool:
        return bool(
            re.match(
                r"https://www\.instagram\.com/(?:p|reel|tv|stories)/([A-Za-z0-9_-]+)/",
                url,
            )
        )

    def is_playlist(self, url: str) -> bool:
        return False

    async def download(self, url: str) -> List[MediaContent]:
        result = []

        try:
            media_urls, filenames = await self._get_instagram_post(url)

            downloaded = await download_all_media(media_urls, filenames)

            if isinstance(downloaded, BotError):
                raise BotError(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    message=f"{downloaded.message}",
                    url=url,
                    critical=True,
                    is_logged=True,
                )

            for path in downloaded:
                if isinstance(path, str):
                    result.append(
                        MediaContent(
                            type=MediaType.PHOTO if path.endswith(".jpg") else MediaType.VIDEO,
                            path=Path(path)
                        )
                    )

            return result
        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Instagram: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )

    async def _get_instagram_post(self, url: str) -> Tuple[List[str], List[str]]:
        pattern = r'https://www\.instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)'
        match = re.match(pattern, url)
        if match:
            short_code = match.group(1)
        else:
            raise ValueError("Invalid Instagram URL")

        try:
            ig_session = await get_instagram_session()
            if not ig_session:
                raise BotError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Instagram: Failed to get session",
                    url=url,
                    critical=True,
                    is_logged=True,
                )

            variables = {
                'shortcode': short_code,
                'child_comment_count': 3,
                'fetch_comment_count': 40,
                'parent_comment_count': 24,
                'has_threaded_comments': True,
            }

            params = {
                'doc_id': '8845758582119845',
                'variables': json.dumps(variables, separators=(',', ':')),
            }

            cookies = ig_session.get("cookies", {})

            headers = {
                'referer': url,
                'User-Agent': ig_session["headers"]["user-agent"],
                'x-csrftoken': cookies.get("csrftoken", None),
                'x-ig-app-id': '936619743392459',
                'x-ig-www-claim': '0',
                'x-mid': cookies.get("mid", None),
                'x-requested-with': 'XMLHttpRequest',
                'x-web-device-id': cookies.get("ig_did", None),
            }

            cleaned_headers = clean_dict(headers)
            cleaned_cookies = clean_dict(cookies)

            proxies = load_proxies("proxies.txt")

            proxy = random.choice(proxies) if proxies else None

            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.instagram.com/graphql/query/", headers=cleaned_headers, proxy=proxy, cookies=cleaned_cookies, params=params) as response:
                    raw_data = await response.text()

            with open ("temp.json", "w") as f:
                f.write(raw_data)

            data_json = json.loads(raw_data)

            post_info = data_json['data']['xdt_shortcode_media']

            if post_info is None:
                raise BotError(
                    code=ErrorCode.INVALID_URL,
                    message="Instagram: Post not found",
                    url=url,
                    critical=False,
                    is_logged=False,
                )

            images = []
            filenames = []

            if post_info["__typename"] == "XDTGraphSidecar":
                for edge in post_info["edge_sidecar_to_children"]["edges"]:
                    images.append(edge["node"]["display_url"])
                    filenames.append(f"{edge['node']['shortcode']}.jpg")
            elif post_info["__typename"] == "XDTGraphImage":
                images.append(post_info["display_url"])
                filenames.append(f"{short_code}.jpg")
            elif post_info["__typename"] == "XDTGraphVideo":
                images.append(post_info["video_url"])
                filenames.append(f"{short_code}.mp4")
            else:
                raise BotError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Unknown post type: {post_info['__typename']}",
                    url=url,
                    critical=False,
                    is_logged=True,
                )

            return images, filenames
        except BotError as e:
            raise e
        except Exception as e:
            raise BotError(
                code=ErrorCode.DOWNLOAD_FAILED,
                message=f"Instagram: {e.with_traceback}",
                url=url,
                critical=True,
                is_logged=True,
            )

async def run_in_thread(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args))


async def download_media(session, url, filename) -> str:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                async with aiofiles.open(filename, "wb") as f:
                    await f.write(await response.read())
                return filename
            else:
                raise BotError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Failed to download Instagram media: {response.status}",
                    url=url,
                    critical=False,
                    is_logged=True,
                )
    except BotError as e:
        raise e
    except Exception as e:
        raise BotError(
            code=ErrorCode.DOWNLOAD_FAILED,
            message=f"Instagram download: {type(e).__name__} – {e}",
            url=url,
            critical=True,
            is_logged=True,
        )


async def download_all_media(media_urls, filenames):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url, name in zip(media_urls, filenames):
            if name.endswith(".mp4"):
                tasks.append(download_video_with_ytdlp(url, name))
            else:
                tasks.append(download_media(session, url, name))
        results = await asyncio.gather(*tasks)
        return results

async def download_video_with_ytdlp(url: str, filename: str) -> str:
    try:
        def _download():
            ydl_opts = {
                'outtmpl': "other/downloadsTemp/%(id)s.%(ext)s",
                'quiet': True,
                'format': 'mp4',
                'merge_output_format': 'mp4',
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        downloaded_path = await run_in_thread(_download)

        final_path = os.path.join("other/downloadsTemp", filename)
        os.rename(downloaded_path, final_path)
        return final_path

    except Exception as e:
        raise BotError(
            code=ErrorCode.DOWNLOAD_FAILED,
            message=f"yt-dlp failed: {type(e).__name__} – {e}",
            url=url,
            critical=True,
            is_logged=True,
        )

def clean_dict(d):
    return {str(k): str(v) for k, v in d.items() if v is not None and k is not None}
