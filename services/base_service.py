from abc import ABC, abstractmethod


class BaseService(ABC):
    @abstractmethod
    def is_supported(self, url: str) -> bool:
        pass

    @abstractmethod
    def is_playlist(self, url: str) -> bool:
        """Проверяет, является ли ссылка плейлистом."""
        pass

    @abstractmethod
    async def download(self, url: str) -> list:
        """Возвращает список скачанного контента:
        [
            {"type": "image", "path": "path/to/image.jpg"},
            {"type": "audio", "path": "path/to/audio.mp3"},
        ]
        """
        pass
