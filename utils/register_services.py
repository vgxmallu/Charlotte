import importlib.util
import inspect
import logging
import os

from services import base_service

logger = logging.getLogger(__name__)

SERVICES = {}

def register_service(name, handler):
    if name in SERVICES:
        logger.warning(f"{name} is already registered.")
    else:
        SERVICES[name] = handler
        logger.info(f"{name} registered")


def get_service_handler(url):
    for name, handler in SERVICES.items():
        if handler.is_supported(url):
            return handler
    raise ValueError("Сервис не поддерживается")


def initialize_services():
    for filename in os.listdir('./services'):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            module_path = os.path.join('./services', filename)

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, base_service.BaseService) and obj is not base_service.BaseService:
                    handler = obj()
                    register_service(name, handler)
