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
