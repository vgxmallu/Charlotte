import os
import random
emojis = {"👍",  "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "🎉", "🤩", "🙏", "👌", "🕊", "😍", "🐳", "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆", "🍓", "🍾", "💋", "👻", "👨‍💻", "👀", "🎃", "😇", "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪",  "🆒", "💘", "🦄", "😘", "😎", "👾"}

def random_emoji():
    return random.choice(list(emojis))


def random_cookie_file():
    cookie_files = os.listdir("cookies")
    return random.choice(cookie_files) if cookie_files else None
