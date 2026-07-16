import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.post import Post


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # String(128) not (64) -- YouTube reply IDs are "parentId.childId" and
    # can exceed 64 characters combined.
    comment_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # Null for top-level comments; set to the parent's comment_id for a reply.
    parent_comment_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    username: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_from_creator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    # Platform-stable author identifier (YouTube author channel ID). Display
    # names aren't unique on YouTube, so is_from_creator there compares this
    # against Influencer.platform_user_id, not username. Null for Instagram
    # rows, which compare usernames instead (see JobProcessor._comment_row).
    author_external_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    author_profile_pic_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    child_comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    liked_by_creator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reported_as_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    commented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    post: Mapped["Post"] = relationship("Post", backref="comments")

    def __repr__(self) -> str:
        return f"<Comment id={self.id} post={self.post_id} comment_id={self.comment_id}>"
