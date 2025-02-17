import logging
from typing import Optional

from ytmusicapi import YTMusic


async def search_music(artist: str, title: str) -> Optional[str]:
    try:
        yt = YTMusic()
        search_results = yt.search(f"{artist} - {title}", limit=1)
        return f"https://music.youtube.com/watch?v={search_results[0]["videoId"]}"

    except Exception as e:
        # Log the error here if you have a logging system
        logging.error(f"Error searching for music: {str(e)}")
        return None
