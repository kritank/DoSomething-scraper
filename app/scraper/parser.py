from typing import Any
from app.schemas.instagram import InstagramUser, InstagramMediaItem, InstagramComment


class InstagramParser:
    @staticmethod
    def parse_user_info(raw_data: dict[str, Any]) -> InstagramUser:
        user_data = raw_data.get("user", {})
        return InstagramUser(
            pk=user_data.get("pk", ""),
            username=user_data.get("username", ""),
            full_name=user_data.get("full_name", ""),
            is_private=user_data.get("is_private", False),
            profile_pic_url=user_data.get("profile_pic_url", ""),
            follower_count=user_data.get("follower_count", 0),
            following_count=user_data.get("following_count", 0),
            media_count=user_data.get("media_count", 0),
            biography=user_data.get("biography", ""),
            biography_with_entities=user_data.get("biography_with_entities"),
            bio_links=user_data.get("bio_links", []),
            pronouns=user_data.get("pronouns", []),
            external_url=user_data.get("external_url"),
            is_verified=user_data.get("is_verified", False),
            is_business_account=user_data.get("is_business_account", False),
            is_professional_account=user_data.get("is_professional_account", False),
            category_name=user_data.get("category_name"),
            category_enum=user_data.get("category_enum"),
            overall_category_name=user_data.get("overall_category_name"),
            business_contact_method=user_data.get("business_contact_method"),
            business_email=user_data.get("business_email"),
            business_phone_number=user_data.get("business_phone_number"),
            highlight_reel_count=user_data.get("highlight_reel_count", 0),
            has_clips=user_data.get("has_clips", False),
            has_guides=user_data.get("has_guides", False),
            has_channel=user_data.get("has_channel", False),
            mutual_followers_count=user_data.get("mutual_followers_count", 0),
            is_verified_by_mv4b=user_data.get("is_verified_by_mv4b", False),
            hide_like_and_view_counts=user_data.get("hide_like_and_view_counts", False),
            has_ar_effects=user_data.get("has_ar_effects", False),
            business_category_name=user_data.get("business_category_name"),
        )
        
    @staticmethod
    def parse_feed(raw_data: dict[str, Any]) -> tuple[list[InstagramMediaItem], str]:
        items = raw_data.get("items", [])
        parsed_items = []
        for item in items:
            parsed = InstagramMediaItem(
                id=item.get("id", ""),
                pk=item.get("pk", ""),
                code=item.get("code", ""),
                caption=item.get("caption"),
                # None (not 0) preserved when the creator has hidden like
                # counts -- Instagram omits/nulls this key in that case, and
                # InstagramMediaItem.like_count is Optional[int] specifically
                # so downstream (see CreatorStatsService's engagement-rate
                # calc) can exclude these posts rather than counting them as
                # a real zero, which would understate engagement rate. This
                # must match instagram_graph_parser.py's identical
                # `item.get("like_count")` -- the two parsers feed the same
                # InstagramMediaItem shape and this field's None-vs-0
                # distinction has to survive both sources equally.
                like_count=item.get("like_count"),
                # Instagram sometimes sends these keys with an explicit JSON
                # null rather than omitting them (seen on older posts) --
                # `.get(key, default)` only falls back to default when the
                # key is *missing*, so an explicit null sails through as
                # None and fails Pydantic's int validation (these fields,
                # unlike like_count, are non-optional). `or default` catches
                # both cases.
                comment_count=item.get("comment_count") or 0,
                view_count=item.get("view_count") or 0,
                # play_count is frequently sent as an explicit null on
                # reels since Instagram moved the real number to
                # ig_play_count (fb_play_count for cross-posted content) --
                # without this fallback chain every reel view count silently
                # stores as 0.
                play_count=(
                    item.get("play_count")
                    or item.get("ig_play_count")
                    or item.get("fb_play_count")
                    or 0
                ),
                reshare_count=item.get("reshare_count") or 0,
                media_type=item.get("media_type") or 1,
                taken_at=item.get("taken_at") or 0,
                accessibility_caption=item.get("accessibility_caption"),
                is_paid_partnership=item.get("is_paid_partnership") or False,
                product_type=item.get("product_type"),
                music_metadata=item.get("music_metadata"),
                original_height=item.get("original_height"),
                original_width=item.get("original_width"),
                locations=item.get("locations") or [],
                coauthor_producers=item.get("coauthor_producers") or [],
                tagged_usernames=(item.get("fb_user_tags") or {}).get("in") or [],
                counts_disabled=item.get("like_and_view_counts_disabled") or False,
                is_pinned=bool(item.get("timeline_pinned_user_ids")),
            )
            parsed_items.append(parsed)
            
        next_max_id = raw_data.get("next_max_id", "")
        if next_max_id is None:
            next_max_id = ""
        return parsed_items, str(next_max_id)

    @staticmethod
    def _parse_comment_item(raw_comment: dict[str, Any], parent_comment_id: str | None = None) -> InstagramComment:
        user = raw_comment.get("user") or {}
        return InstagramComment(
            comment_id=str(raw_comment.get("pk", "")),
            parent_comment_id=parent_comment_id,
            username=user.get("username", ""),
            full_name=user.get("full_name", ""),
            is_verified=user.get("is_verified", False),
            text=raw_comment.get("text", ""),
            like_count=raw_comment.get("comment_like_count", 0) or 0,
            child_comment_count=raw_comment.get("child_comment_count") or 0,
            created_at=raw_comment.get("created_at", 0) or 0,
            liked_by_creator=bool(raw_comment.get("liked_by_media_coauthors")),
            is_edited=raw_comment.get("is_edited", False),
            reported_as_spam=raw_comment.get("did_report_as_spam", False),
            author_profile_pic_url=user.get("profile_pic_url"),
            author_is_private=user.get("is_private", False),
        )

    @staticmethod
    def parse_comments(connection: dict[str, Any]) -> tuple[list[InstagramComment], str, bool]:
        """Parse a page of top-level comments from the GraphQL Relay
        connection shape ({edges: [{node: ...}], page_info: {...}}) returned
        by InstagramClient.get_media_comments.

        Returns (comments, next_after_cursor, has_more).
        """
        comments = [
            InstagramParser._parse_comment_item(edge.get("node", {}))
            for edge in connection.get("edges", [])
        ]
        page_info = connection.get("page_info") or {}
        has_more = bool(page_info.get("has_next_page"))
        next_cursor = (page_info.get("end_cursor") or "") if has_more else ""
        return comments, next_cursor, has_more

    @staticmethod
    def parse_replies(connection: dict[str, Any], parent_comment_id: str) -> tuple[list[InstagramComment], str, bool]:
        """Parse a page of replies to a single comment from the GraphQL
        Relay connection shape returned by InstagramClient.get_comment_replies.

        Returns (replies, next_after_cursor, has_more).
        """
        replies = [
            InstagramParser._parse_comment_item(edge.get("node", {}), parent_comment_id=parent_comment_id)
            for edge in connection.get("edges", [])
        ]
        page_info = connection.get("page_info") or {}
        has_more = bool(page_info.get("has_next_page"))
        next_cursor = (page_info.get("end_cursor") or "") if has_more else ""
        return replies, next_cursor, has_more
