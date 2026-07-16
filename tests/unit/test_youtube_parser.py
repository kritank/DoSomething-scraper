from __future__ import annotations

from app.scraper.youtube_parser import YouTubeParser, parse_iso8601_duration


def test_parse_iso8601_duration_variants():
    assert parse_iso8601_duration("PT12M34S") == 754.0
    assert parse_iso8601_duration("PT1H2M3S") == 3723.0
    assert parse_iso8601_duration("P1DT2H3M4S") == 93784.0
    assert parse_iso8601_duration("PT45S") == 45.0
    assert parse_iso8601_duration("PT0S") == 0.0
    assert parse_iso8601_duration(None) is None
    assert parse_iso8601_duration("") is None
    assert parse_iso8601_duration("garbage") is None


def test_parse_channel_maps_core_fields_and_coerces_string_counts():
    raw = {
        "items": [
            {
                "id": "UC123",
                "snippet": {
                    "title": "Test Channel",
                    "description": "desc",
                    "customUrl": "@testchannel",
                    "publishedAt": "2020-01-01T00:00:00Z",
                    "country": "US",
                },
                "statistics": {
                    "subscriberCount": "12300",
                    "hiddenSubscriberCount": False,
                    # Deliberately larger than Integer's ~2.1B range --
                    # this is exactly why profile_snapshots.total_views is
                    # BigInteger.
                    "viewCount": "9999999999",
                    "videoCount": "42",
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
                "brandingSettings": {"channel": {"keywords": "a b c"}},
                "status": {"madeForKids": False},
                "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/Technology"]},
            }
        ]
    }

    channel = YouTubeParser.parse_channel(raw)

    assert channel.channel_id == "UC123"
    assert channel.subscriber_count == 12300
    assert channel.view_count == 9999999999
    assert channel.uploads_playlist_id == "UU123"
    assert channel.subscribers_hidden is False
    assert channel.topic_categories == ["https://en.wikipedia.org/wiki/Technology"]


def test_parse_channel_empty_items_yields_blank_channel():
    """channels.list 200s with an empty items list for a deleted channel or
    a typo'd handle -- YouTubeJobProcessor treats an empty channel_id as
    "not found" and raises ScraperBlockedError."""
    channel = YouTubeParser.parse_channel({"items": []})
    assert channel.channel_id == ""


def test_parse_channel_hidden_subscriber_count():
    raw = {
        "items": [
            {
                "id": "UC1",
                "snippet": {},
                "statistics": {"hiddenSubscriberCount": True, "subscriberCount": "0"},
                "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}},
            }
        ]
    }
    channel = YouTubeParser.parse_channel(raw)
    assert channel.subscribers_hidden is True
    assert channel.subscriber_count == 0


def test_parse_uploads_page_extracts_ids_and_next_token():
    raw = {
        "items": [
            {"contentDetails": {"videoId": "vid1", "videoPublishedAt": "2026-01-01T00:00:00Z"}},
            {"contentDetails": {"videoId": "vid2", "videoPublishedAt": "2026-01-02T00:00:00Z"}},
        ],
        "nextPageToken": "tok123",
    }
    ids, token = YouTubeParser.parse_uploads_page(raw)
    assert ids == ["vid1", "vid2"]
    assert token == "tok123"


def test_parse_uploads_page_no_next_token():
    ids, token = YouTubeParser.parse_uploads_page({"items": []})
    assert ids == []
    assert token == ""


def _video_item(**overrides):
    base = {
        "id": "vid1",
        "snippet": {
            "title": "Title",
            "description": "Desc",
            "publishedAt": "2026-01-01T00:00:00Z",
            "liveBroadcastContent": "none",
        },
        "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "5"},
        "contentDetails": {"duration": "PT10M0S", "definition": "hd", "dimension": "2d", "caption": "true"},
        "status": {"madeForKids": False},
    }
    base.update(overrides)
    return base


def test_parse_videos_normal_video():
    videos = YouTubeParser.parse_videos({"items": [_video_item()]})
    assert len(videos) == 1
    v = videos[0]
    assert v.video_id == "vid1"
    assert v.view_count == 100
    assert v.like_count == 10
    assert v.comment_count == 5
    assert v.comments_disabled is False
    assert v.media_label == "video"


def test_parse_videos_hidden_likes_and_disabled_comments_stay_none_not_zero():
    """likeCount/commentCount absent (not present as an explicit 0) means
    the creator hid likes / disabled comments -- must stay None so
    PostMetricsSnapshot writes NULL, not a fabricated 0."""
    item = _video_item()
    del item["statistics"]["likeCount"]
    del item["statistics"]["commentCount"]

    videos = YouTubeParser.parse_videos({"items": [item]})
    v = videos[0]
    assert v.like_count is None
    assert v.comment_count is None
    assert v.comments_disabled is True


def test_parse_videos_classifies_short_by_duration():
    item = _video_item(contentDetails={"duration": "PT30S"})
    videos = YouTubeParser.parse_videos({"items": [item]})
    assert videos[0].media_label == "short"
    assert videos[0].duration_s == 30.0


def test_parse_videos_classifies_live():
    item = _video_item()
    item["liveStreamingDetails"] = {"actualStartTime": "2026-01-01T00:00:00Z"}
    item["snippet"]["liveBroadcastContent"] = "live"
    videos = YouTubeParser.parse_videos({"items": [item]})
    assert videos[0].media_label == "live"


def test_parse_videos_paid_product_placement():
    item = _video_item(paidProductPlacementDetails={"hasPaidProductPlacement": True})
    videos = YouTubeParser.parse_videos({"items": [item]})
    assert videos[0].has_paid_product_placement is True


def test_parse_comment_threads_splits_top_level_and_inline_replies():
    raw = {
        "items": [
            {
                "snippet": {
                    "totalReplyCount": 7,
                    "topLevelComment": {
                        "id": "c1",
                        "snippet": {
                            "authorDisplayName": "A",
                            "authorChannelId": {"value": "UCauthor"},
                            "textOriginal": "hey",
                            "likeCount": 3,
                            "publishedAt": "2026-01-01T00:00:00Z",
                        },
                    },
                },
                "replies": {
                    "comments": [
                        {
                            "id": "c1.r1",
                            "snippet": {
                                "authorDisplayName": "B",
                                "textOriginal": "reply",
                                "publishedAt": "2026-01-01T01:00:00Z",
                                "updatedAt": "2026-01-01T02:00:00Z",
                            },
                        }
                    ]
                },
            }
        ],
        "nextPageToken": "tok",
    }

    top_level, inline_replies, next_token = YouTubeParser.parse_comment_threads(raw)

    assert len(top_level) == 1
    assert top_level[0].comment_id == "c1"
    assert top_level[0].total_reply_count == 7
    assert top_level[0].author_channel_id == "UCauthor"

    assert len(inline_replies) == 1
    assert inline_replies[0].comment_id == "c1.r1"
    assert inline_replies[0].parent_comment_id == "c1"
    assert inline_replies[0].is_edited is True  # updatedAt != publishedAt

    assert next_token == "tok"


def test_parse_comment_replies_page():
    raw = {
        "items": [
            {"id": "c1.r2", "snippet": {"authorDisplayName": "C", "textOriginal": "another reply", "publishedAt": "2026-01-01T03:00:00Z"}}
        ],
        "nextPageToken": "",
    }
    replies, next_token = YouTubeParser.parse_comment_replies(raw, "c1")
    assert len(replies) == 1
    assert replies[0].parent_comment_id == "c1"
    assert next_token == ""
