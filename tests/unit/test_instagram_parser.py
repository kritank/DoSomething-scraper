from __future__ import annotations

from app.scraper.parser import InstagramParser


def _feed_item(**overrides):
    item = {
        "id": "1", "pk": "1", "code": "abc",
        "like_count": 42, "comment_count": 3, "media_type": 1, "taken_at": 1700000000,
    }
    item.update(overrides)
    return item


def test_like_count_missing_is_none_not_zero():
    """Regression test: the creator hiding like counts must stay
    distinguishable from a genuine 0 likes -- CreatorStatsService's
    engagement-rate calc relies on `likes is None` to exclude these posts
    rather than counting them as a real zero, which understates the rate.
    Previously `or 0` silently coerced a missing/null like_count into 0."""
    raw = {"items": [_feed_item(like_count=None)]}
    items, _ = InstagramParser.parse_feed(raw)
    assert items[0].like_count is None


def test_like_count_missing_key_is_also_none():
    item = _feed_item()
    del item["like_count"]
    raw = {"items": [item]}
    items, _ = InstagramParser.parse_feed(raw)
    assert items[0].like_count is None


def test_like_count_real_zero_is_preserved_as_zero():
    raw = {"items": [_feed_item(like_count=0)]}
    items, _ = InstagramParser.parse_feed(raw)
    assert items[0].like_count == 0


def test_like_count_real_value_is_preserved():
    raw = {"items": [_feed_item(like_count=42)]}
    items, _ = InstagramParser.parse_feed(raw)
    assert items[0].like_count == 42


def test_comment_count_null_still_coerces_to_zero():
    """Unlike like_count, comment_count is a non-optional int on
    InstagramMediaItem -- an explicit JSON null must still fall back to 0
    or Pydantic validation would fail."""
    raw = {"items": [_feed_item(comment_count=None)]}
    items, _ = InstagramParser.parse_feed(raw)
    assert items[0].comment_count == 0
