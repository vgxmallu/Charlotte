import aiohttp
import base64
from config.secrets import SPOTIFY_CLIENT_ID, SPOTIFY_SECRET

TOKEN_URL = "https://accounts.spotify.com/api/token"


async def get_access_token(session: aiohttp.ClientSession):
    """Получение токена доступа через Client Credentials Flow"""
    auth_header = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_SECRET}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}

    async with session.post(TOKEN_URL, headers=headers, data=data) as response:
        if response.status != 200:
            print(f"Failed to get token: {response.status} {await response.text()}")
            return None
        result = await response.json()
        return result.get("access_token")
