from app.models.post import Post
from app.models.feature_store import FeatureStore
from app.feature_extraction.nlp_utils import (
    extract_hashtags, extract_mentions, count_words, 
    extract_emojis, detect_language, has_question, has_cta
)

class FeatureExtractor:
    @staticmethod
    def extract_features(post: Post, media_type: str = "unknown") -> FeatureStore:
        caption = post.caption or ""

        return FeatureStore(
            post_id=post.id,
            caption_length=len(caption),
            word_count=count_words(caption),
            hashtag_count=len(extract_hashtags(caption)),
            mention_count=len(extract_mentions(caption)),
            emoji_count=len(extract_emojis(caption)),
            has_cta=has_cta(caption),
            has_question=has_question(caption),
            keywords={}, # Optional: keyword extraction could go here
            detected_language=detect_language(caption),
            posting_hour=post.posted_at.hour,
            posting_weekday=post.posted_at.weekday(),
            media_type=media_type,
        )
