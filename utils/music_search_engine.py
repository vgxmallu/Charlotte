import logging
import asyncio
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from ytmusicapi import YTMusic


_search_executor = ThreadPoolExecutor(max_workers=5)

async def search_music(artist: str, title: str) -> Optional[str]:
    try:
        yt = await asyncio.get_event_loop().run_in_executor(
            _search_executor,
            YTMusic
        )

        search_results = await asyncio.get_event_loop().run_in_executor(
            _search_executor,
            lambda: yt.search(f"{artist} - {title}", limit=10, filter="songs")
        )

        for track in search_results:
            if not track.get('duration'):
                continue

            if track['duration_seconds'] <= 600:
                return f"https://music.youtube.com/watch?v={track['videoId']}"

        logging.warning("No tracks under 600 seconds found")
        return None

    except Exception as e:
        logging.error(f"Music search error: {str(e)}", exc_info=True)
        return None
