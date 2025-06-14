import asyncio
import importlib
import logging
import os
import pkgutil
from logging.handlers import TimedRotatingFileHandler

from database.database_manager import create_table_settings
from loader import bot, dp
from utils.language_middleware import CustomI18nMiddleware
from aiogram.utils.i18n import I18n, FSMI18nMiddleware
from utils.register_services import initialize_services
from utils.set_bot_commands import set_default_commands

# Initialize CustomMiddleware and connect it to dispatcher
i18n = I18n(path="locales", default_locale="en", domain="messages")
fsm_i18n = FSMI18nMiddleware(i18n)
dp.update.middleware(fsm_i18n)

custom_i18n = CustomI18nMiddleware(i18n)
dp.update.middleware(custom_i18n)

# Setup Logger
log_dir = "other/logs"
os.makedirs(log_dir, exist_ok=True)

log_format = "%(asctime)s - %(filename)s - %(funcName)s - %(lineno)d - %(name)s - %(levelname)s - %(message)s"
log_file = os.path.join(log_dir, "logging.log")

# File to log with rotation
file_handler = TimedRotatingFileHandler(
    log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(log_format))

# Console Handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(log_format))

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add logger handler to console and file
if not logger.hasHandlers():
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Bot Startup
async def main():
    """
    The main asynchronous function to start the bot and perform initial setup.
    """
    logger.info("Bot is starting...")

    try:
        logger.info("Setting up database...")
        await create_table_settings()

        logger.info("Setting default commands...")
        await set_default_commands()

        logger.info("Loading modules...")
        load_modules(
            ["handlers.user", "handlers.admin"], ignore_files=["__init__.py", "help.py"]
        )

        logger.info("Initializing services...")
        initialize_services()

        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"An error occurred while starting the bot: {e}")


def load_modules(plugin_packages, ignore_files=[]):
    ignore_files.append("__init__")
    for plugin_package in plugin_packages:
        package = importlib.import_module(plugin_package)
        for _, name, is_pkg in pkgutil.iter_modules(package.__path__):
            if not is_pkg and name not in ignore_files:
                logger.info(f"Loading module: {plugin_package}.{name}")
                importlib.import_module(f"{plugin_package}.{name}")


if __name__ == "__main__":
    asyncio.run(main())
