from typing import Any
from app.schemas.instagram import InstagramUser, InstagramMediaItem


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
                like_count=item.get("like_count", 0),
                comment_count=item.get("comment_count", 0),
                view_count=item.get("view_count", 0),
                play_count=item.get("play_count", 0),
                media_type=item.get("media_type", 1),
                taken_at=item.get("taken_at", 0),
            )
            parsed_items.append(parsed)
            
        next_max_id = raw_data.get("next_max_id", "")
        if next_max_id is None:
            next_max_id = ""
        return parsed_items, str(next_max_id)
