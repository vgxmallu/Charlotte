from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_SECRET = os.getenv("SPOTIFY_SECRET")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
APPLEMUSIC_DEV_TOKEN = os.getenv("APPLEMUSIC_DEV_TOKEN")
