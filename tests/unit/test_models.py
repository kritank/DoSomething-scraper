import pytest

from app.models.category import Category
from app.models.influencer import Influencer
from app.models.post import Post
from app.models.raw_response import RawResponse
from app.models.scrape_job import ScrapeJob
from app.models.feature_store import FeatureStore
from app.models.benchmark import CategoryBenchmark
from app.models.recommendation import Recommendation


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
