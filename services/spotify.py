import asyncio
import logging
import os
import re
import urllib.request

import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials
from yt_dlp.utils import sanitize_filename

from config.secrets import SPOTIFY_CLIENT_ID, SPOTIFY_SECRET
from utils import get_spotify_author, search_music, update_metadata

from .base_service import BaseService

auth_manager = SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_SECRET
)
spotify = spotipy.Spotify(auth_manager=auth_manager)


class SpotifyService(BaseService):
    name = "Spotify"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.yt_dlp_options = {
            "format": "bestaudio",
            "outtmpl": f"{output_path}/{sanitize_filename('%(title)s')}",
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
            cover_filename = os.path.join(self.output_path, f"{sanitize_filename(ydl_title)}.jpg")

            urllib.request.urlretrieve(cover_url, cover_filename)

            update_metadata(audio_filename, artist=artist, title=title, cover_file=cover_filename)

            if os.path.exists(audio_filename) and os.path.exists(cover_filename):
                result.append({"type": "audio", "path": audio_filename, "cover": cover_filename})
            return result

        except Exception as e:
            logging.error(f"Error downloading YouTube Audio: {str(e)}")
            return result

    def get_playlist_tracks(self, url: str) -> list[str]:
        match = re.search(r"playlist/([^/?]+)", url)
        if not match:
            logging.error(f"Invalid playlist URL: {url}")
            return []

        playlist_id = match.group(1)
        all_tracks = []
        offset = 0
        limit = 100

        while True:
            try:
                results = spotify.playlist_items(playlist_id, limit=limit, offset=offset)
                tracks = results["items"]
                all_tracks.extend(tracks)
                if len(tracks) < limit:
                    break
                offset += limit
            except Exception as e:
                logging.error(f"Error fetching tracks: {e}")
                break

        track_urls = []

        for item in all_tracks:
            track = item.get("track")
            if track:
                track_url = track.get("external_urls", {}).get("spotify")
                if track_url:
                    track_urls.append(track_url)

        return track_urls
