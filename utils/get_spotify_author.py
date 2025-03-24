import logging
import re

import aiohttp
from .spotify_login import get_access_token


async def get_track_info(track_id: str):
    """Получение данных о треке по его ID"""
    url = f"https://api.spotify.com/v1/tracks/{track_id}"

    async with aiohttp.ClientSession() as session:
        token = await get_access_token(session)
        headers = {"Authorization": f"Bearer {token}"}

        async with session.get(url, headers=headers) as response:
            return await response.json()


def extract_track_id(url: str) -> str | None:
    match = re.search(r"track/(\w+)", url)
    return match.group(1) if match else None


async def get_spotify_author(url: str):
    track_id = extract_track_id(url)
    if not track_id:
        logging.error("Invalid Spotify URL")
        return None, None, None

    try:
        track_info = await get_track_info(track_id)

        artist = ", ".join(artist["name"] for artist in track_info["artists"])
        title = track_info["name"]
        cover_url = track_info["album"]["images"][0]["url"]

        return artist, title, cover_url
    except Exception as e:
        logging.error(f"Error fetching track: {e}")
        return None, None, None
