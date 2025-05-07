import os
import logging

def load_proxies(file_path: str) -> list[str]:
    if not os.path.exists(file_path):
        logging.info("Файл с прокси не найден, продолжаем без прокси.")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]
