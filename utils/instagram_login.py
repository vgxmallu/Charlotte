from instagrapi import Client
from instagrapi.exceptions import LoginRequired
import logging
import os

from config.secrets import INSTA_PASSWORD, INSTA_USERNAME

logger = logging.getLogger()


def login_user():
    """
    Attempts to log in to Instagram using either session data or username/password.
    """
    cl = Client()

    session_file = "session.json"
    login_via_session = False

    # Try loading session if exists
    if os.path.exists(session_file):
        try:
            session = cl.load_settings(session_file)
            cl.set_settings(session)
            cl.login(INSTA_USERNAME, INSTA_PASSWORD)

            # Verify if session is still valid
            try:
                cl.get_timeline_feed()
                login_via_session = True
                logger.info("Logged in via session successfully.")
            except LoginRequired:
                logger.info(
                    "Session expired. Re-logging in with username and password."
                )
        except Exception as e:
            logger.warning("Failed to load session: %s", e)

    # If session login fails, try username/password
    if not login_via_session:
        try:
            cl.login(INSTA_USERNAME, INSTA_PASSWORD)
            cl.dump_settings(session_file)
            logger.info("Logged in via username and password successfully.")
        except Exception as e:
            logger.error("Login failed: %s", e)
            raise Exception("Couldn't log in via either session or username/password.")

    return cl
