from __future__ import annotations

from datetime import date, datetime, timezone

from app.analytics.creator_stats import (
    _aggregate_comment_engagement,
    _aggregate_performance_decay,
    _bucket_engagement_trend,
    _CommentEngagementRow,
    _DecayRow,
    _EngagementTrendRow,
)

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def test_engagement_trend_averages_rate_per_bucket():
    rows = [
        _EngagementTrendRow(posted_at=datetime(2026, 7, 6, tzinfo=timezone.utc), likes=100, comments=0),
        _EngagementTrendRow(posted_at=datetime(2026, 7, 7, tzinfo=timezone.utc), likes=200, comments=0),
    ]
    points = _bucket_engagement_trend(rows, followers=1000, bucket="week")
    assert len(points) == 1
    assert points[0].post_count == 2
    # (0.1 + 0.2) / 2
    assert points[0].avg_engagement_rate == 0.15


def test_engagement_trend_daily_buckets_stay_separate():
    rows = [
        _EngagementTrendRow(posted_at=datetime(2026, 7, 6, tzinfo=timezone.utc), likes=100, comments=0),
        _EngagementTrendRow(posted_at=datetime(2026, 7, 7, tzinfo=timezone.utc), likes=200, comments=0),
    ]
    points = _bucket_engagement_trend(rows, followers=1000, bucket="day")
    assert len(points) == 2
    assert points[0].date == date(2026, 7, 6)
    assert points[1].date == date(2026, 7, 7)


def test_engagement_trend_excludes_likes_hidden_posts_from_rate_but_counts_post():
    rows = [_EngagementTrendRow(posted_at=datetime(2026, 7, 6, tzinfo=timezone.utc), likes=None, comments=None)]
    points = _bucket_engagement_trend(rows, followers=1000, bucket="day")
    assert points[0].post_count == 1
    assert points[0].avg_engagement_rate is None


def test_engagement_trend_empty_input():
    assert _bucket_engagement_trend([], followers=1000, bucket="week") == []


def test_performance_decay_buckets_by_age_and_averages_velocity():
    rows = [
        _DecayRow(hours_since_posted=0.5, velocity_per_hour=200.0),  # 0-1h
        _DecayRow(hours_since_posted=0.5, velocity_per_hour=100.0),  # 0-1h
        _DecayRow(hours_since_posted=200.0, velocity_per_hour=10.0),  # 7-14d
    ]
    out = _aggregate_performance_decay(rows, days=90)
    first_bucket = next(p for p in out.points if p.bucket_label == "0-1h")
    assert first_bucket.sample_size == 2
    assert first_bucket.avg_velocity_per_hour == 150.0
    later_bucket = next(p for p in out.points if p.bucket_label == "7-14d")
    assert later_bucket.sample_size == 1
    assert later_bucket.avg_velocity_per_hour == 10.0


def test_performance_decay_far_future_lands_in_catchall_bucket():
    rows = [_DecayRow(hours_since_posted=1000.0, velocity_per_hour=5.0)]
    out = _aggregate_performance_decay(rows, days=90)
    tail_bucket = next(p for p in out.points if p.bucket_label == "30d+")
    assert tail_bucket.sample_size == 1


def test_performance_decay_empty_bucket_has_none_average():
    out = _aggregate_performance_decay([], days=90)
    assert all(p.avg_velocity_per_hour is None and p.sample_size == 0 for p in out.points)


def test_comment_engagement_computes_rates_overall_and_by_format():
    rows = [
        _CommentEngagementRow(format="long_form", is_from_creator=True, is_verified=False, child_comment_count=2, like_count=4),
        _CommentEngagementRow(format="long_form", is_from_creator=False, is_verified=True, child_comment_count=0, like_count=0),
        _CommentEngagementRow(format="short_form", is_from_creator=False, is_verified=False, child_comment_count=1, like_count=2),
    ]
    out = _aggregate_comment_engagement(rows, days=90, posts_with_comments=2)
    assert out.posts_with_comments == 2
    assert out.overall.comment_count == 3
    assert out.overall.creator_reply_rate == round(1 / 3, 4)
    assert out.overall.verified_commenter_rate == round(1 / 3, 4)

    long_form = next(f for f in out.formats if f.format == "long_form")
    assert long_form.comment_count == 2
    assert long_form.creator_reply_rate == 0.5
    assert long_form.avg_child_comment_count == 1.0
    assert long_form.avg_likes_per_comment == 2.0

    short_form = next(f for f in out.formats if f.format == "short_form")
    assert short_form.comment_count == 1
    assert short_form.creator_reply_rate == 0.0


def test_comment_engagement_empty_bucket_has_none_rates():
    out = _aggregate_comment_engagement([], days=90, posts_with_comments=0)
    assert out.overall.comment_count == 0
    assert out.overall.creator_reply_rate is None
    assert out.overall.avg_likes_per_comment is None
