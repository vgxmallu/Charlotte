from .base_service import BaseService
import re
import os
import logging
import urllib.request
from utils import update_metadata, random_cookie_file
import asyncio

import yt_dlp
from yt_dlp.utils import sanitize_filename

class SoundCloudService(BaseService):
    name = "SoundCloud"
    def __init__(self, output_path: str = "other/downloadsTemp") -> None:
        super().__init__()
        self.output_path = output_path
        os.makedirs(self.output_path, exist_ok=True)
        self.yt_dlp_options = {
            "format": "bestaudio",
            "writethumbnail": True,
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
        return bool(re.match(r"https?://soundcloud\.com/([\w-]+)/([\w-]+)", url))

    def is_playlist(self, url: str) -> bool:
        return bool(re.match(r"^https?:\/\/(www\.)?soundcloud\.com\/[\w\-]+\/sets\/[\w\-]+$", url))

    async def download(self, url: str) -> list:
        result = []

        ydl = yt_dlp.YoutubeDL(self.yt_dlp_options)
        info_dict = await asyncio.to_thread(ydl.extract_info, url, download=False)
        if info_dict is None:
            return []

        title = info_dict.get("title")
        if title is None:
            title =""

        artist = info_dict.get("uploader")
        if artist is None:
            artist = ""

        cover_url = self._get_cover_url(info_dict)

        # Download the track
        await asyncio.to_thread(ydl.download, [url])

        # Filenames for audio and cover
        audio_filename = os.path.join(self.output_path, f"{sanitize_filename(title)}.mp3")
        cover_filename = os.path.join(self.output_path, f"{sanitize_filename(title)}.jpg")

        # Download the cover image
        if cover_url:
            urllib.request.urlretrieve(cover_url, cover_filename)

        # Update metadata
        update_metadata(audio_file=audio_filename, title=title, artist=artist, cover_file=cover_filename)

        # Return file paths if files exist
        if os.path.exists(audio_filename) and os.path.exists(cover_filename):
            result.append({"type": "audio", "path": audio_filename, "cover": cover_filename})
        return result

    async def get_playlist_tracks(self, url: str) -> list[str]:
        """
        Extracts all track URLs from a SoundCloud playlist.

        Args:
            url (str): The URL of the SoundCloud playlist.

        Returns:
            list[str]: A list of track URLs. Returns None if there is an error.
        """
        try:
            options = {
                "noplaylist": False,
                "extract_flat": True
            }

            with yt_dlp.YoutubeDL(options) as ydl:
                playlist_info = ydl.extract_info(url, download=False)

            track_urls = [entry.get('url') for entry in playlist_info.get('entries', []) if entry.get('url')]


            print("Return")
            return track_urls

        except Exception as e:
            logging.error(f"Error extracting track URLs from playlist: {e}")
            return []

    def _get_cover_url(self, info_dict: dict):
        """
        Extracts the cover URL from the track's information.

        Parameters:
        ----------
        info_dict : dict
            The information dictionary for the SoundCloud track.

        Returns:
        -------
        str or None
            The URL of the cover image, or None if no appropriate image is found.
        """
        thumbnails = info_dict.get("thumbnails", [])
        return next((thumbnail["url"] for thumbnail in thumbnails if thumbnail.get("width") == 500), None)
