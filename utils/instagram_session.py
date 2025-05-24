import asyncio
import re
import json
import aiohttp
import os
from datetime import datetime, timedelta
from fake_useragent import UserAgent

SESSION_FILE = "ig_session.json"
USER_AGENT = UserAgent(platforms="desktop").random
COOKIE_EXPIRY_HOURS = 24

async def fetch_initial_data():
    headers = {"user-agent": USER_AGENT}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.instagram.com/", headers=headers) as response:
            html = await response.text()
            set_cookies = response.headers.getall("Set-Cookie", [])

    # Парсинг куки из заголовков
    cookies = {}
    for header in set_cookies:
        key, rest = header.split("=", 1)
        val = rest.split(";", 1)[0]
        cookies[key] = val

    csrf_token = cookies.get("csrftoken")

    # Парсинг deferredCookies
    match = re.search(r'"deferredCookies"\s*:\s*({.*?})\s*,\s*"blLoggingCavalryFields"', html)
    parsed_cookies = {}
    if match:
        try:
            cookies_json = json.loads(match.group(1))
            parsed_cookies = {name: data["value"] for name, data in cookies_json.items()}
        except Exception as e:
            print("❌ Ошибка при парсинге deferredCookies:", e)

    # Парсинг LSD
    match = re.search(r'\["MRequestConfig",\[\],({.*?})\s*,\d+\]', html)
    if not match:
        raise Exception("Не найден блок MRequestConfig")

    config_json = json.loads(match.group(1))
    lsd = config_json.get("lsd")

    ig_did = parsed_cookies.get("_js_ig_did")
    ig_datr = parsed_cookies.get("_js_datr")
    ig_mid = parsed_cookies.get("_js_mid")

    session_cookies = {
        "csrftoken": csrf_token,
        "ig_did": ig_did,
        "datr": ig_datr,
    }

    if ig_mid is not None:
        cookies['mid'] = ig_mid

    return session_cookies, csrf_token, lsd

async def register_device(cookies, csrf_token, lsd):
    headers = {
        "user-agent": USER_AGENT,
        "x-ig-app-id": "936619743392459",
        "x-csrftoken": csrf_token,
        "content-type": "application/x-www-form-urlencoded",
        "x-fb-friendly-name": "PolarisCookieMutation",
        "x-fb-lsd": lsd,
        "referer": "https://www.instagram.com/",
    }

    data = {
        "lsd": lsd,
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "PolarisCookieMutation",
        "variables": json.dumps({
            "ig_did": cookies["ig_did"],
            "first_party_tracking_opt_in": True,
            "third_party_tracking_opt_in": True,
            "opted_in_categories": [],
            "opted_in_controls": [],
            "consent_to_everything": True
        }),
        "server_timestamps": "true",
        "doc_id": "9831756296889252",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://www.instagram.com/api/graphql",
                                headers=headers, cookies=cookies, data=data) as response:
            if response.status != 200:
                raise Exception("Регистрация устройства не удалась")

async def get_instagram_session():
    # Проверка на существование и валидность сохранённой сессии
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            session_data = json.load(f)
            timestamp = datetime.fromisoformat(session_data["timestamp"])
            if datetime.now() - timestamp < timedelta(hours=COOKIE_EXPIRY_HOURS):
                return session_data

    # Получение новых куки
    cookies, csrf_token, lsd = await fetch_initial_data()
    await register_device(cookies, csrf_token, lsd)

    session_data = {
        "timestamp": datetime.now().isoformat(),
        "cookies": cookies,
        "headers": {
            "user-agent": USER_AGENT,
            "x-csrftoken": csrf_token,
        }
    }

    with open(SESSION_FILE, "w") as f:
        json.dump(session_data, f, indent=2)

    return session_data
