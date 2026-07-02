import re
import emoji
from langdetect import detect

def extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#(\w+)", text)

def extract_mentions(text: str) -> list[str]:
    return re.findall(r"@(\w+)", text)

def count_words(text: str) -> int:
    # Remove hashtags and mentions before counting words
    clean_text = re.sub(r"[#@]\w+", "", text)
    return len(re.findall(r"\w+", clean_text))

def extract_emojis(text: str) -> list[str]:
    return [c for c in text if c in emoji.EMOJI_DATA]

def detect_language(text: str) -> str:
    if not text.strip():
        return "unknown"
    try:
        return detect(text)
    except:
        return "unknown"

def has_question(text: str) -> bool:
    return "?" in text

def has_cta(text: str) -> bool:
    ctas = ["link in bio", "comment below", "tag a friend", "swipe up", "buy now", "check out"]
    lower_text = text.lower()
    return any(cta in lower_text for cta in ctas)
