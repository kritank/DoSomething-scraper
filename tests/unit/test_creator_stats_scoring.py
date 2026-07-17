from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.analytics.creator_stats import (
    MIN_POSTS_FOR_OUTLIER,
    OUTLIER_LOOKBACK_POSTS,
    _compute_outlier_and_velocity,
    _detect_milestones,
    _PostMetricPoint,
    content_format,
)
from app.schemas.creator_stats import GrowthPoint

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _point(days_ago: float, views=None, likes=None) -> _PostMetricPoint:
    return _PostMetricPoint(
        post_id=uuid4(),
        posted_at=NOW - timedelta(days=days_ago),
        title="t",
        permalink=None,
        views=views,
        likes=likes,
        comments=None,
    )


def test_outlier_score_none_with_too_few_prior_posts():
    points = [_point(days_ago=10 - i, views=1000) for i in range(MIN_POSTS_FOR_OUTLIER - 1)]
    scores = _compute_outlier_and_velocity(points, "youtube", NOW)
    # last point has only (MIN_POSTS_FOR_OUTLIER - 2) prior posts -- below threshold
    assert scores[points[-1].post_id][0] is None


def test_outlier_score_computed_once_enough_history():
    points = [_point(days_ago=100 - i, views=1000) for i in range(MIN_POSTS_FOR_OUTLIER + 2)]
    points.append(_point(days_ago=1, views=5000))
    scores = _compute_outlier_and_velocity(points, "youtube", NOW)
    outlier, _ = scores[points[-1].post_id]
    assert outlier == 5.0  # 5000 / median(1000...) == 5x


def test_outlier_uses_likes_when_views_missing_instagram():
    points = [_point(days_ago=100 - i, likes=200) for i in range(MIN_POSTS_FOR_OUTLIER + 2)]
    points.append(_point(days_ago=1, likes=1000))
    scores = _compute_outlier_and_velocity(points, "instagram", NOW)
    outlier, _ = scores[points[-1].post_id]
    assert outlier == 5.0


def test_outlier_lookback_is_capped():
    """A huge spike far in the past shouldn't distort the median forever --
    only the last OUTLIER_LOOKBACK_POSTS prior posts count."""
    points = [_point(days_ago=1000, views=1_000_000)]
    points += [_point(days_ago=500 - i, views=100) for i in range(OUTLIER_LOOKBACK_POSTS + 5)]
    points.append(_point(days_ago=1, views=300))
    scores = _compute_outlier_and_velocity(points, "youtube", NOW)
    outlier, _ = scores[points[-1].post_id]
    assert outlier == 3.0  # 300 / 100, the ancient 1M spike is out of window


def test_velocity_only_for_fresh_youtube_posts():
    fresh = _point(days_ago=2, views=4800)
    stale = _point(days_ago=30, views=4800)
    scores = _compute_outlier_and_velocity([fresh, stale], "youtube", NOW)
    assert scores[fresh.post_id][1] == 100.0  # 4800 views / 48 hours
    assert scores[stale.post_id][1] is None


def test_velocity_uses_shorter_window_for_instagram():
    within_window = _point(days_ago=1, likes=240)
    outside_window = _point(days_ago=3, likes=240)
    scores = _compute_outlier_and_velocity([within_window, outside_window], "instagram", NOW)
    assert scores[within_window.post_id][1] == 10.0  # 240 likes / 24 hours
    assert scores[outside_window.post_id][1] is None


def test_velocity_none_when_metric_missing():
    point = _point(days_ago=1, views=None, likes=None)
    scores = _compute_outlier_and_velocity([point], "youtube", NOW)
    assert scores[point.post_id] == (None, None)


def test_content_format_youtube():
    assert content_format("youtube", "video") == "long_form"
    assert content_format("youtube", "short") == "short_form"
    assert content_format("youtube", "live") == "live"
    assert content_format("youtube", None) == "long_form"


def test_content_format_instagram():
    assert content_format("instagram", "clips") == "short_form"
    assert content_format("instagram", "feed") == "long_form"
    assert content_format("instagram", "carousel_container") == "long_form"
    assert content_format("instagram", "igtv") == "long_form"
    assert content_format("instagram", None) == "long_form"


def _gp(day: str, value: int) -> GrowthPoint:
    from datetime import date as date_cls

    return GrowthPoint(date=date_cls.fromisoformat(day), value=value)


def test_milestone_detected_on_crossing():
    series = [_gp("2026-01-01", 9_500), _gp("2026-01-02", 10_500)]
    events = _detect_milestones(series)
    assert len(events) == 1
    assert events[0].label == "Crossed 10K followers"
    assert events[0].date.isoformat() == "2026-01-02"


def test_milestone_none_without_crossing():
    series = [_gp("2026-01-01", 9_000), _gp("2026-01-02", 9_500)]
    assert _detect_milestones(series) == []


def test_milestone_none_for_single_point():
    assert _detect_milestones([_gp("2026-01-01", 10_000)]) == []


def test_milestone_multiple_thresholds_in_one_jump():
    series = [_gp("2026-01-01", 90_000), _gp("2026-01-02", 1_200_000)]
    events = _detect_milestones(series)
    labels = {e.label for e in events}
    assert labels == {"Crossed 100K followers", "Crossed 500K followers", "Crossed 1M followers"}


def test_milestone_not_re_triggered_by_later_drop_and_regrowth():
    """A sub-count that dips below a threshold it already crossed and
    climbs back shouldn't fire the same milestone twice."""
    series = [_gp("2026-01-01", 9_000), _gp("2026-01-02", 11_000), _gp("2026-01-03", 9_800), _gp("2026-01-04", 10_500)]
    events = _detect_milestones(series)
    assert len(events) == 1
    assert events[0].date.isoformat() == "2026-01-02"
