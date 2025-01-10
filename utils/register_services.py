from services import (
    TikTokService,
    YouTubeService,
    SoundCloudService,
    SpotifyService,
    PinterestService,
    AppleMusicService,
    BiliBiliService,
    TwitterService,
    InstagramService
)

SERVICES = {}

def register_service(name, handler):
    SERVICES[name] = handler

def get_service_handler(url):
    for name, handler in SERVICES.items():
        if handler.is_supported(url):
            return handler
    raise ValueError("Сервис не поддерживается")

register_service("youtube", YouTubeService())
register_service("soundcloud", SoundCloudService())
register_service("tiktok", TikTokService())
register_service("spotify", SpotifyService())
register_service("pinterest", PinterestService())
register_service("apple_music", AppleMusicService())
register_service("bilibili", BiliBiliService())
register_service("twitter", TwitterService())
register_service("instagram", InstagramService())
