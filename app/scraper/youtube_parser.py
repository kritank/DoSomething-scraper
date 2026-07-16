import re
from datetime import datetime, timezone
from typing import Any

from app.schemas.youtube import YouTubeChannel, YouTubeComment, YouTubeVideo

# ISO8601 duration, e.g. "PT12M34S", "PT1H2M3S", or (rare, long livestream
# VOD archives) "P1DT2H3M4S". YouTube's contentDetails.duration is always in
# this family -- never the Y/M/W date-only components.
_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def parse_iso8601_duration(raw: str | None) -> float | None:
    if not raw:
        return None
    match = _DURATION_RE.match(raw)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_iso8601_to_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


def _parse_iso8601_to_epoch(raw: str | None) -> int:
    dt = parse_iso8601_to_datetime(raw)
    return int(dt.timestamp()) if dt else 0


class YouTubeParser:
    @staticmethod
    def parse_channel(raw_data: dict[str, Any]) -> YouTubeChannel:
        items = raw_data.get("items") or []
        channel = items[0] if items else {}

        snippet = channel.get("snippet") or {}
        statistics = channel.get("statistics") or {}
        content_details = channel.get("contentDetails") or {}
        branding = (channel.get("brandingSettings") or {}).get("channel") or {}
        status = channel.get("status") or {}
        topic_details = channel.get("topicDetails") or {}

        return YouTubeChannel(
            channel_id=channel.get("id", ""),
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            custom_url=snippet.get("customUrl"),
            published_at=snippet.get("publishedAt"),
            country=snippet.get("country"),
            uploads_playlist_id=(
                content_details.get("relatedPlaylists", {}).get("uploads", "")
            ),
            # Counts arrive as strings ("12345") -- coerce explicitly rather
            # than relying on Pydantic's implicit string->int coercion, so a
            # missing/empty value falls back to 0 instead of a validation error.
            subscriber_count=int(statistics.get("subscriberCount") or 0),
            subscribers_hidden=bool(statistics.get("hiddenSubscriberCount", False)),
            view_count=int(statistics.get("viewCount") or 0),
            video_count=int(statistics.get("videoCount") or 0),
            keywords=branding.get("keywords"),
            made_for_kids=bool(status.get("madeForKids", False)),
            topic_categories=topic_details.get("topicCategories") or [],
        )

    @staticmethod
    def parse_uploads_page(raw_data: dict[str, Any]) -> tuple[list[str], str]:
        """Returns (video_ids in feed order, next_page_token)."""
        items = raw_data.get("items") or []
        video_ids = [
            item.get("contentDetails", {}).get("videoId", "")
            for item in items
            if item.get("contentDetails", {}).get("videoId")
        ]
        next_page_token = raw_data.get("nextPageToken", "") or ""
        return video_ids, next_page_token

    @staticmethod
    def parse_videos(raw_data: dict[str, Any]) -> list[YouTubeVideo]:
        items = raw_data.get("items") or []
        parsed: list[YouTubeVideo] = []
        for item in items:
            snippet = item.get("snippet") or {}
            statistics = item.get("statistics") or {}
            content_details = item.get("contentDetails") or {}
            status = item.get("status") or {}
            topic_details = item.get("topicDetails") or {}
            live_details = item.get("liveStreamingDetails")
            paid_placement = item.get("paidProductPlacementDetails") or {}
            thumbnails = snippet.get("thumbnails") or {}
            best_thumb = (
                thumbnails.get("maxres")
                or thumbnails.get("standard")
                or thumbnails.get("high")
                or thumbnails.get("medium")
                or thumbnails.get("default")
                or {}
            )

            live_broadcast_content = snippet.get("liveBroadcastContent", "none") or "none"
            duration_raw = content_details.get("duration")

            parsed.append(
                YouTubeVideo(
                    video_id=item.get("id", ""),
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    published_at=snippet.get("publishedAt") or "",
                    tags=snippet.get("tags") or [],
                    default_language=snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage"),
                    category_id=snippet.get("categoryId"),
                    made_for_kids=bool(status.get("madeForKids", False)),
                    topic_categories=topic_details.get("topicCategories") or [],
                    duration_s=parse_iso8601_duration(duration_raw),
                    duration_raw=duration_raw,
                    definition=content_details.get("definition"),
                    dimension=content_details.get("dimension"),
                    has_captions=(content_details.get("caption") == "true"),
                    is_live_or_upcoming=bool(live_details) or live_broadcast_content in ("live", "upcoming"),
                    live_broadcast_content=live_broadcast_content,
                    # .get(key) (not .get(key, 0)) is deliberate here -- an
                    # absent key means "not publicly available" (hidden
                    # likes, disabled comments) and must stay None, not
                    # silently become a fabricated 0. See
                    # docs/YOUTUBE_SCRAPER_DESIGN.md §3.3.
                    view_count=(
                        int(statistics["viewCount"]) if "viewCount" in statistics else None
                    ),
                    like_count=(
                        int(statistics["likeCount"]) if "likeCount" in statistics else None
                    ),
                    comment_count=(
                        int(statistics["commentCount"]) if "commentCount" in statistics else None
                    ),
                    comments_disabled="commentCount" not in statistics,
                    has_paid_product_placement=bool(
                        paid_placement.get("hasPaidProductPlacement", False)
                    ),
                    thumbnail_width=best_thumb.get("width"),
                    thumbnail_height=best_thumb.get("height"),
                    location=item.get("recordingDetails", {}).get("location"),
                )
            )
        return parsed

    @staticmethod
    def _parse_comment_snippet(comment_id: str, snippet: dict[str, Any], parent_comment_id: str | None) -> YouTubeComment:
        author_channel_id = (snippet.get("authorChannelId") or {}).get("value")
        published_at = snippet.get("publishedAt")
        updated_at = snippet.get("updatedAt")
        return YouTubeComment(
            comment_id=comment_id,
            parent_comment_id=parent_comment_id or snippet.get("parentId"),
            author_display_name=snippet.get("authorDisplayName", ""),
            author_channel_id=author_channel_id,
            author_profile_image_url=snippet.get("authorProfileImageUrl"),
            text=snippet.get("textOriginal", ""),
            like_count=snippet.get("likeCount") or 0,
            total_reply_count=0,
            published_at=_parse_iso8601_to_epoch(published_at),
            is_edited=bool(updated_at and updated_at != published_at),
        )

    @staticmethod
    def parse_comment_threads(
        raw_data: dict[str, Any],
    ) -> tuple[list[YouTubeComment], list[YouTubeComment], str]:
        """Parse a page of commentThreads.list.

        Returns (top_level_comments, inline_replies, next_page_token).
        Inline replies are the up-to-5 replies YouTube embeds directly in
        each thread -- callers only need to page get_comment_replies for a
        thread when its totalReplyCount exceeds what came back here.
        """
        top_level: list[YouTubeComment] = []
        inline_replies: list[YouTubeComment] = []

        for item in raw_data.get("items") or []:
            thread_snippet = item.get("snippet") or {}
            top_comment = thread_snippet.get("topLevelComment") or {}
            comment_id = top_comment.get("id", "")
            parsed_top = YouTubeParser._parse_comment_snippet(
                comment_id, top_comment.get("snippet") or {}, parent_comment_id=None
            )
            parsed_top.total_reply_count = int(thread_snippet.get("totalReplyCount") or 0)
            top_level.append(parsed_top)

            for reply in (item.get("replies") or {}).get("comments") or []:
                inline_replies.append(
                    YouTubeParser._parse_comment_snippet(
                        reply.get("id", ""), reply.get("snippet") or {}, parent_comment_id=comment_id
                    )
                )

        next_page_token = raw_data.get("nextPageToken", "") or ""
        return top_level, inline_replies, next_page_token

    @staticmethod
    def parse_comment_replies(
        raw_data: dict[str, Any], parent_comment_id: str
    ) -> tuple[list[YouTubeComment], str]:
        replies = [
            YouTubeParser._parse_comment_snippet(
                item.get("id", ""), item.get("snippet") or {}, parent_comment_id=parent_comment_id
            )
            for item in raw_data.get("items") or []
        ]
        next_page_token = raw_data.get("nextPageToken", "") or ""
        return replies, next_page_token
