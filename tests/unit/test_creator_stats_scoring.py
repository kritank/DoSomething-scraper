from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.analytics.creator_stats import (
    MIN_POSTS_FOR_OUTLIER,
    OUTLIER_LOOKBACK_POSTS,
    _compute_composite_outlier_score,
    _compute_outlier_and_velocity,
    _compute_outlier_details,
    _compute_vph_current,
    _detect_milestones,
    _PostMetricPoint,
    _select_metric_pair,
    content_format,
)
from app.schemas.creator_stats import GrowthPoint

NOW = datetime(2026, 7, 17, tzinfo=timezone.utc)


def _point(days_ago: float, views=None, likes=None, comments=None) -> _PostMetricPoint:
    return _PostMetricPoint(
        post_id=uuid4(),
        posted_at=NOW - timedelta(days=days_ago),
        title="t",
        permalink=None,
        views=views,
        likes=likes,
        comments=comments,
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


def test_outlier_details_exposes_baseline_median():
    points = [_point(days_ago=100 - i, views=1000) for i in range(MIN_POSTS_FOR_OUTLIER + 2)]
    points.append(_point(days_ago=1, views=5000))
    details = _compute_outlier_details(points, "youtube", NOW)
    detail = details[points[-1].post_id]
    assert detail.outlier_score == 5.0
    assert detail.baseline_median == 1000
    assert details[points[0].post_id].baseline_median is None  # too few priors


def test_engagement_ratio_none_with_too_few_prior_posts():
    points = [_point(days_ago=10 - i, views=1000, likes=50, comments=5) for i in range(MIN_POSTS_FOR_OUTLIER - 1)]
    details = _compute_outlier_details(points, "youtube", NOW)
    assert details[points[-1].post_id].engagement_ratio is None


def test_engagement_ratio_above_baseline():
    points = [
        _point(days_ago=100 - i, views=1000, likes=50, comments=5)
        for i in range(MIN_POSTS_FOR_OUTLIER + 2)
    ]
    # baseline ER = (50+5)/1000 = 0.055; this post has double the engagement rate
    points.append(_point(days_ago=1, views=1000, likes=100, comments=10))
    details = _compute_outlier_details(points, "youtube", NOW)
    assert details[points[-1].post_id].engagement_ratio == 2.0


def test_engagement_ratio_none_when_likes_and_comments_both_missing():
    points = [
        _point(days_ago=100 - i, views=1000, likes=50, comments=5)
        for i in range(MIN_POSTS_FOR_OUTLIER + 2)
    ]
    points.append(_point(days_ago=1, views=1000))  # likes hidden, comments disabled
    details = _compute_outlier_details(points, "youtube", NOW)
    assert details[points[-1].post_id].engagement_ratio is None


def test_vph_current_from_snapshot_delta():
    from datetime import date

    vph = _compute_vph_current(
        current_metric=2400, current_date=date(2026, 7, 17),
        previous_metric=1200, previous_date=date(2026, 7, 16),
    )
    assert vph == 50.0  # 1200 views gained over 24h


def test_vph_current_none_on_negative_delta():
    from datetime import date

    vph = _compute_vph_current(
        current_metric=900, current_date=date(2026, 7, 17),
        previous_metric=1200, previous_date=date(2026, 7, 16),
    )
    assert vph is None


def test_vph_current_none_when_same_day():
    from datetime import date

    vph = _compute_vph_current(
        current_metric=1200, current_date=date(2026, 7, 17),
        previous_metric=1000, previous_date=date(2026, 7, 17),
    )
    assert vph is None


def test_vph_current_none_when_metric_missing():
    from datetime import date

    assert _compute_vph_current(None, date(2026, 7, 17), 1000, date(2026, 7, 16)) is None


def test_composite_score_falls_back_to_baseline_multiple():
    """No velocity or engagement signal available -- score is just the
    multiplier, unchanged (Instagram photo posts, single-snapshot posts)."""
    score = _compute_composite_outlier_score(
        baseline_multiple=3.0, vph_current=None, vph_lifetime=None, engagement_ratio=None
    )
    assert score == 3.0


def test_composite_score_none_without_baseline():
    assert _compute_composite_outlier_score(None, 10.0, 5.0, 1.0) is None


def test_composite_score_boosted_by_accelerating_velocity():
    score = _compute_composite_outlier_score(
        baseline_multiple=2.0, vph_current=400.0, vph_lifetime=100.0, engagement_ratio=None
    )
    assert score > 2.0  # velocity_ratio=4 > 1 boosts the score


def test_composite_score_unaffected_by_decelerating_velocity():
    """A post slowing down below its lifetime average shouldn't be
    penalized -- only acceleration (velocity_ratio > 1) boosts the score."""
    score = _compute_composite_outlier_score(
        baseline_multiple=2.0, vph_current=50.0, vph_lifetime=100.0, engagement_ratio=None
    )
    assert score == 2.0


def test_select_metric_pair_uses_views_by_default():
    assert _select_metric_pair("youtube", 100, 10, 80, 8) == (100, 80)
    assert _select_metric_pair("instagram", 100, 10, 80, 8) == (100, 80)


def test_select_metric_pair_falls_back_to_likes_on_instagram_photo_posts():
    # views == 0 (not None) is Instagram's "no view metric for this post
    # type" signal -- same rule as _PostMetricPoint.outlier_metric.
    assert _select_metric_pair("instagram", 0, 50, 0, 40) == (50, 40)


def test_select_metric_pair_youtube_never_falls_back_to_likes():
    assert _select_metric_pair("youtube", 0, 50, 0, 40) == (0, 0)


def test_composite_score_engagement_clamped():
    score_high = _compute_composite_outlier_score(
        baseline_multiple=2.0, vph_current=None, vph_lifetime=None, engagement_ratio=10.0
    )
    score_low = _compute_composite_outlier_score(
        baseline_multiple=2.0, vph_current=None, vph_lifetime=None, engagement_ratio=0.01
    )
    assert score_high == 2.5  # clamped to 1.25x
    assert score_low == 1.5  # clamped to 0.75x


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
