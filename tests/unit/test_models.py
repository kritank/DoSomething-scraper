import pytest

from app.models.category import Category
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.raw_response import RawResponse
from app.models.scrape_job import ScrapeJob
from app.models.feature_store import FeatureStore
from app.models.benchmark import CategoryBenchmark
from app.models.recommendation import Recommendation
from app.models.youtube_api_key import YouTubeApiKey


def test_models_can_be_imported():
    """Verify that all ORM models can be imported successfully."""
    assert Category.__tablename__ == "categories"
    assert Influencer.__tablename__ == "influencers"
    assert Post.__tablename__ == "posts"
    assert RawResponse.__tablename__ == "raw_responses"
    assert ScrapeJob.__tablename__ == "scrape_jobs"
    assert FeatureStore.__tablename__ == "feature_store"
    assert CategoryBenchmark.__tablename__ == "category_benchmarks"
    assert Recommendation.__tablename__ == "recommendations"
    assert YouTubeApiKey.__tablename__ == "youtube_api_keys"


def test_influencer_platform_defaults_to_instagram_column():
    """platform has a DB-side server_default, not a Python-side default --
    confirms the column exists and is configured the way
    InfluencerRepo.create() (which always sets it explicitly) expects."""
    column = Influencer.__table__.columns["platform"]
    assert column.server_default.arg == "instagram"
    assert column.nullable is False


def test_post_metrics_snapshot_engagement_columns_are_nullable():
    """likes/comments/reposts must be nullable -- YouTube has no public
    share count at all, and hides likes/comments per-video. NULL means
    "not available", never a fabricated 0 (see PostMetricsSnapshot)."""
    from app.models.snapshot import PostMetricsSnapshot

    for column_name in ("likes", "comments", "reposts"):
        assert PostMetricsSnapshot.__table__.columns[column_name].nullable is True


def test_comment_ids_widened_for_youtube_reply_ids():
    from app.models.comment import Comment

    assert Comment.__table__.columns["comment_id"].type.length == 128
    assert Comment.__table__.columns["parent_comment_id"].type.length == 128
