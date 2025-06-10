import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import aiofiles
import aiohttp
import yt_dlp
from aiofiles import os as aios
from bs4 import BeautifulSoup
from yt_dlp.utils import sanitize_filename

from config.secrets import APPLEMUSIC_DEV_TOKEN
from models.media_models import MediaContent, MediaType
from services.base_service import BaseService
from utils import (
    get_applemusic_author,
    random_cookie_file,
    search_music,
    update_metadata,
)
from utils.error_handler import BotError, ErrorCode

logger = logging.getLogger(__name__)


class AppleMusicService(BaseService):
    name = "AppleMusic"
    _download_executor = ThreadPoolExecutor(max_workers=10)

    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.api_headers = {
            'accept': '*/*',
            'authorization': f'Bearer {APPLEMUSIC_DEV_TOKEN}',
            'origin': 'https://music.apple.com',
            'referer': 'https://music.apple.com/',
        }

    def _get_audio_options(self):
        return {
            "format": "bestaudio",
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
        return bool(
            re.match(r"https:\/\/music\.apple\.com\/[\w]{2}\/(song\/([\w-]+)\/(\d+)|album\/([^\/]+)\/(\d+)(\?i=(\d+))?|playlist\/([\w-]+)\/([\w.-]+))", url)
        )

    def is_playlist(self, url: str) -> bool:
        return bool(
            re.match(r"https:\/\/music\.apple\.com\/[\w]{2}\/playlist\/([\w-]+)\/([\w.-]+)", url)
        )
    async def download(self, url: str) -> List[MediaContent]:
        options = self._get_audio_options()
        try:
            permofer, title, cover_url = await get_applemusic_author(url)

            if not permofer or not title:
                raise BotError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Failed to get artist and title from Apple Music",
                    url=url,
                    critical=True,
                    is_logged=True
                )

            video_link = await search_music(permofer, title)

            with yt_dlp.YoutubeDL(options) as ydl:
                loop = asyncio.get_event_loop()

                info_dict = await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.extract_info(video_link, download=False)
                )
                if not info_dict:
                    raise BotError(
                        code=ErrorCode.DOWNLOAD_FAILED,
                        message="Failed to extract info from Apple Music",
                        url=url,
                        critical=False,
                        is_logged=True,
                    )

                await loop.run_in_executor(
                    self._download_executor,
                    lambda: ydl.download([video_link])
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
                message=f"Apple Music: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )

    async def get_playlist_tracks(self, url: str) -> list[str]:
        match = re.search(r'/playlist/[^/]+/(pl\.[\w-]+)', url)
        if not match:
            raise BotError(
                code=ErrorCode.INVALID_URL,
                message="Failed to extract playlist ID from URL",
                url=url,
                critical=False,
                is_logged=False,
            )

        playlist_id = match.group(1)
        logger.info(f"Parsing playlist with ID: {playlist_id}")

        # --- Attempt to use API first if token is available ---
        if APPLEMUSIC_DEV_TOKEN:
            logger.info(f"Attempting to fetch playlist {playlist_id} using Apple Music API.")
            try:
                params = {
                    'fields[songs]': 'name,artistName,artwork,url',
                }
                api_url = f'https://amp-api.music.apple.com/v1/catalog/tr/playlists/{playlist_id}'

                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=self.api_headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            if (data and 'data' in data and len(data['data']) > 0 and
                                    'relationships' in data['data'][0] and
                                    'tracks' in data['data'][0]['relationships'] and
                                    'data' in data['data'][0]['relationships']['tracks']):

                                track_urls: list[str] = []
                                tracks_data = data['data'][0]['relationships']['tracks']['data']
                                for track in tracks_data:
                                    if "attributes" in track and "url" in track["attributes"]:
                                        track_urls.append(track["attributes"]["url"])
                                    else:
                                        logger.warning(f"Skipping track in API response due to missing attributes/url: {track}")

                                if track_urls:
                                    logger.info(f"Successfully fetched {len(track_urls)} tracks from API for playlist {playlist_id}.")
                                    return track_urls
                                else:
                                    logger.warning(f"API returned no tracks or invalid track data for playlist {playlist_id}. Falling back to HTML parsing.")
                            else:
                                logger.warning(f"Unexpected API response structure for playlist {playlist_id}. Falling back to HTML parsing.")
                        else:
                            logger.error(f"API request failed with status {response.status} for playlist {playlist_id}. Falling back to HTML parsing.")

            except aiohttp.ClientError as e:
                logger.error(f"Apple Music API request error for playlist {playlist_id}: {e}. Falling back to HTML parsing.")
            except KeyError as e:
                logger.error(f"KeyError in Apple Music API playlist response parsing for {playlist_id}: {e}. Falling back to HTML parsing.")
            except Exception as e:
                logger.error(f"General error during Apple Music API attempt for playlist {playlist_id}: {e}. Falling back to HTML parsing.")

        # --- Fallback to HTML parsing ---
        logger.info(f"Falling back to HTML parsing for playlist {playlist_id}.")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()

                    soup = BeautifulSoup(await response.text(), 'html.parser')

                    script_tag = soup.find('script', {'id': 'serialized-server-data'})
                    if not script_tag or not script_tag.string:
                        logger.error(f"Could not find JSON in page for playlist {playlist_id} (serialized-server-data script tag missing or empty).")
                        return []

                    json_data = json.loads(script_tag.string)

                    track_urls: list[str] = []

                    sections = json_data[0].get('data', {}).get('sections', [])
                    for section in sections:
                        if "track-list" in section.get("id", ""):
                            tracks = section.get('items', [])
                            for track in tracks:
                                try:
                                    track_id_raw = track.get("id")
                                    numerical_track_id = None

                                    if isinstance(track_id_raw, str):
                                        id_match = re.search(r'(\d+)$', track_id_raw)
                                        if id_match:
                                            numerical_track_id = id_match.group(1)
                                        else:
                                            if track_id_raw.isdigit():
                                                numerical_track_id = track_id_raw
                                    elif isinstance(track_id_raw, (int, float)):
                                        numerical_track_id = str(int(track_id_raw))

                                    if numerical_track_id:
                                        track_urls.append("https://music.apple.com/pl/song/"+numerical_track_id)
                                    else:
                                        logger.warning(f"Could not extract numerical track ID for: {track}")

                                except (KeyError, IndexError) as e:
                                    logger.warning(f"Failed to extract URL for track from HTML (KeyError/IndexError): {track}. Error: {e}")
                                except Exception as e:
                                    logger.warning(f"An unexpected error occurred during HTML track extraction: {track}. Error: {e}")
                            break

                    if not track_urls:
                        logger.warning(f"No tracks found after HTML parsing for playlist {playlist_id}.")
                    else:
                        logger.info(f"Successfully parsed {len(track_urls)} tracks from HTML for playlist {playlist_id}.")
                    return track_urls

        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch playlist HTML: {e}")
            raise BotError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to fetch playlist data from HTML: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from HTML for playlist {playlist_id}: {e}")
            raise BotError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Failed to parse playlist data from HTML (JSON error): {e}",
                url=url,
                critical=True,
                is_logged=True,
            )
        except Exception as e:
            logger.error(f"An unexpected error occurred during HTML playlist parsing: {e}")
            raise BotError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"An unexpected error occurred during HTML playlist parsing: {e}",
                url=url,
                critical=True,
                is_logged=True,
            )
