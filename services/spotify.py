import asyncio
import logging
import os
import re
import urllib.request

import yt_dlp
from yt_dlp.utils import sanitize_filename

import aiohttp

from utils import get_spotify_author, search_music, update_metadata, get_access_token, random_cookie_file

from .base_service import BaseService

class SpotifyService(BaseService):
    name = "Spotify"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.yt_dlp_options = {
            "format": "bestaudio",
            "outtmpl": f"{output_path}/{sanitize_filename('%(title)s')}",
            "cookiefile": random_cookie_file(),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                },
            ],
        }

    def is_supported(self, url: str) -> bool:
        return bool(re.match(r"https?://open\.spotify\.com/(track|playlist)/([\w-]+)", url))

    def is_playlist(self, url: str) -> bool:
        return bool(re.match(r"https?://open\.spotify\.com/playlist/([\w-]+)", url))

    async def download(self, url: str) -> list:
        result = []

        artist, title, cover_url = await get_spotify_author(url)
        if not artist or not title:
            logging.error("Failed to get artist and title from Spotify")
            return result

        video_link = await search_music(artist, title)

        try:
            ydl = yt_dlp.YoutubeDL(self.yt_dlp_options)

            info_dict = await asyncio.to_thread(ydl.extract_info, video_link, download=False)
            ydl_title = info_dict.get("title")

            await asyncio.to_thread(ydl.download, [video_link])

            audio_filename = os.path.join(self.output_path, f"{sanitize_filename(ydl_title)}.mp3")

            if cover_url:
                cover_filename  = os.path.join(self.output_path, f"{sanitize_filename(ydl_title)}.jpg")
                urllib.request.urlretrieve(cover_url, cover_filename)
            else:
                cover_filename = None
            assert cover_filename, "Cover URL is not available"

            update_metadata(audio_filename, artist=artist, title=title, cover_file=cover_filename)

            if os.path.exists(audio_filename) or os.path.exists(cover_filename):
                result.append({"type": "audio", "path": audio_filename, "cover": cover_filename})
            return result

        except Exception as e:
            logging.error(f"Error downloading YouTube Audio: {str(e)}")
            return result

    async def get_playlist_tracks(self, url: str) -> list[str]:
        tracks = []
        offset = 0

        match = re.search(r"playlist/([^/?]+)", url)
        if not match:
            logging.error(f"Invalid playlist URL: {url}")
            return []

        try:
            async with aiohttp.ClientSession() as session:
                token = await get_access_token(session)
                if not token:
                    return []

                headers = {"Authorization": f"Bearer {token}"}
                params = {"offset": offset}
                playlist_id = match.group(1)
                playlist_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

                async with session.get(playlist_url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        for track in data["items"]:
                            tracks.append(track["track"]["external_urls"]["spotify"])

        except Exception as e:
            logging.error(f"Error fetching playlist tracks: {e}")
            print(f"Error fetching playlist tracks: {e}")
        return tracks
