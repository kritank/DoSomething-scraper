from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.analytics.creator_stats import (
    MIN_POSTS_FOR_OUTLIER,
    OUTLIER_LOOKBACK_POSTS,
    _aggregate_format_breakdown,
    _aggregate_posting_times,
    _aggregate_sponsorship_breakdown,
    _bucket_posting_frequency,
    _compute_composite_outlier_score,
    _compute_outlier_and_velocity,
    _compute_outlier_details,
    _compute_vph_current,
    _detect_milestones,
    _FormatRow,
    _InstagramMetricSnapshotRow,
    _interpolate_daily_gaps,
    _PostMetricPoint,
    _reconstruct_daily_views_series,
    _select_metric_pair,
    _SponsorshipRow,
    _strip_phantom_zero_lead,
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
    series = [_gp("2026-01-01", 90_000), _gp("2026-01-02", 160_000)]
    events = _detect_milestones(series)
    labels = {e.label for e in events}
    assert labels == {"Crossed 100K followers", "Crossed 150K followers"}


def test_milestone_not_re_triggered_by_later_drop_and_regrowth():
    """A sub-count that dips below a threshold it already crossed and
    climbs back shouldn't fire the same milestone twice."""
    series = [_gp("2026-01-01", 9_000), _gp("2026-01-02", 11_000), _gp("2026-01-03", 9_800), _gp("2026-01-04", 10_500)]
    events = _detect_milestones(series)
    assert len(events) == 1
    assert events[0].date.isoformat() == "2026-01-02"


def test_phantom_zero_lead_flood_prevented_before_stripping():
    """Documents the actual bug: an unstripped phantom-zero seed point
    makes _detect_milestones treat the very next real point as having
    crossed every threshold between 0 and that value at once -- a flood of
    same-day events, which is what "shot up on first scrape" looked like."""
    series = [_gp("2026-01-01", 0), _gp("2026-01-02", 160_000)]
    events = _detect_milestones(series)
    assert len(events) > 2  # the bug: far more than the 2 real crossings


def test_strip_phantom_zero_lead_removes_seed_point():
    from datetime import date as date_cls

    series = [
        _gp("2026-01-01", 0),
        GrowthPoint(date=date_cls.fromisoformat("2026-01-02"), value=160_000, daily_delta=160_000),
        GrowthPoint(date=date_cls.fromisoformat("2026-01-03"), value=165_000, daily_delta=5_000),
    ]
    stripped = _strip_phantom_zero_lead(series)
    assert [p.date.isoformat() for p in stripped] == ["2026-01-02", "2026-01-03"]
    assert stripped[0].daily_delta is None  # no real "previous day" anymore
    assert stripped[1].daily_delta == 5_000  # untouched, not the stripped point


def test_strip_phantom_zero_lead_fixes_the_flood():
    series = [_gp("2026-01-01", 0), _gp("2026-01-02", 160_000)]
    events = _detect_milestones(_strip_phantom_zero_lead(series))
    assert events == []  # first (only) point after stripping -- nothing to compare against


def test_strip_phantom_zero_lead_strips_small_jump_too():
    """Regression test: no tracked account genuinely has 0 followers
    (this function's own docstring), regardless of how small the account
    is -- a hardcoded >=1000 threshold previously left the phantom zero
    in place for a small/new account's very first real (non-zero)
    reading, e.g. a broken 0 snapshot followed by a genuine 450."""
    series = [_gp("2026-01-01", 0), _gp("2026-01-02", 450)]
    stripped = _strip_phantom_zero_lead(series)
    assert [p.date.isoformat() for p in stripped] == ["2026-01-02"]
    assert stripped[0].daily_delta is None


def test_strip_phantom_zero_lead_leaves_all_zero_series_alone():
    """No positive value anywhere yet to confirm the leading zero was
    phantom rather than real -- nothing to strip."""
    series = [_gp("2026-01-01", 0), _gp("2026-01-02", 0)]
    assert _strip_phantom_zero_lead(series) == series


def test_strip_phantom_zero_lead_noop_without_leading_zero():
    series = [_gp("2026-01-01", 9_000), _gp("2026-01-02", 11_000)]
    assert _strip_phantom_zero_lead(series) == series


def test_strip_phantom_zero_lead_noop_for_short_series():
    assert _strip_phantom_zero_lead([]) == []


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def test_bucket_posting_frequency_weekly_groups_same_week():
    # 2026-01-05 (Mon) and 2026-01-07 (Wed) share the Monday-01-05 bucket;
    # 2026-01-12 (Mon) starts a new week.
    posted_ats = [_dt("2026-01-05T10:00:00"), _dt("2026-01-07T22:00:00"), _dt("2026-01-12T00:00:00")]
    points = _bucket_posting_frequency(posted_ats, bucket="week")
    assert [(p.date.isoformat(), p.post_count) for p in points] == [
        ("2026-01-05", 2),
        ("2026-01-12", 1),
    ]


def test_bucket_posting_frequency_daily_keeps_days_separate():
    posted_ats = [_dt("2026-01-05T01:00:00"), _dt("2026-01-05T23:00:00"), _dt("2026-01-06T00:00:00")]
    points = _bucket_posting_frequency(posted_ats, bucket="day")
    assert [(p.date.isoformat(), p.post_count) for p in points] == [
        ("2026-01-05", 2),
        ("2026-01-06", 1),
    ]


def test_bucket_posting_frequency_empty_input():
    assert _bucket_posting_frequency([], bucket="week") == []


def test_aggregate_posting_times_counts_and_picks_best():
    # 2026-01-05 is a Monday (weekday()==0); 2026-01-07 is a Wednesday (2).
    posted_ats = [
        _dt("2026-01-05T09:00:00"),
        _dt("2026-01-05T09:30:00"),
        _dt("2026-01-07T14:00:00"),
    ]
    dist = _aggregate_posting_times(posted_ats)
    assert dist.weekday_counts[0] == 2  # Monday
    assert dist.weekday_counts[2] == 1  # Wednesday
    assert dist.hour_counts[9] == 2
    assert dist.hour_counts[14] == 1
    assert dist.best_weekday == 0
    assert dist.best_hour == 9
    assert dist.total_posts == 3
    assert dist.hourly_weekday_matrix[0][9] == 2
    assert dist.hourly_weekday_matrix[2][14] == 1


def test_aggregate_posting_times_empty_input():
    dist = _aggregate_posting_times([])
    assert dist.total_posts == 0
    assert dist.best_weekday is None
    assert dist.best_hour is None
    assert dist.weekday_counts == [0] * 7
    assert dist.hour_counts == [0] * 24


def _sr(format="long_form", sponsored=False, views=None, likes=None, comments=None):
    return _SponsorshipRow(
        format=format, is_paid_partnership=sponsored, views=views, likes=likes, comments=comments
    )


def test_sponsorship_breakdown_splits_organic_and_sponsored():
    rows = [
        _sr(sponsored=False, views=1000, likes=100, comments=10),
        _sr(sponsored=False, views=2000, likes=200, comments=20),
        _sr(sponsored=True, views=5000, likes=500, comments=50),
    ]
    out = _aggregate_sponsorship_breakdown(rows, days=90)
    assert out.window_days == 90
    assert out.organic.post_count == 2
    assert out.organic.avg_views == 1500.0
    assert out.organic.avg_likes == 150.0
    assert out.organic.avg_comments == 15.0
    assert out.sponsored.post_count == 1
    assert out.sponsored.avg_views == 5000.0


def test_sponsorship_breakdown_crossed_with_format():
    rows = [
        _sr(format="long_form", sponsored=False, views=1000, likes=100, comments=10),
        _sr(format="long_form", sponsored=True, views=4000, likes=400, comments=40),
        _sr(format="short_form", sponsored=False, views=2000, likes=200, comments=20),
    ]
    out = _aggregate_sponsorship_breakdown(rows, days=90)
    by_format = {f.format: f for f in out.formats}
    assert set(by_format) == {"long_form", "short_form"}
    assert by_format["long_form"].organic.post_count == 1
    assert by_format["long_form"].organic.avg_views == 1000.0
    assert by_format["long_form"].sponsored.post_count == 1
    assert by_format["long_form"].sponsored.avg_views == 4000.0
    assert by_format["short_form"].organic.post_count == 1
    assert by_format["short_form"].sponsored.post_count == 0
    assert by_format["short_form"].sponsored.avg_views is None
    # Overall aggregates across both formats regardless of the split.
    assert out.organic.post_count == 2
    assert out.sponsored.post_count == 1


def test_sponsorship_breakdown_falls_back_to_likes_when_views_unavailable():
    # Instagram photo posts: views is None/0, likes is the usable metric --
    # same rule as FormatStats.avg_views / _PostMetricPoint.outlier_metric.
    rows = [_sr(sponsored=True, views=0, likes=300, comments=30)]
    out = _aggregate_sponsorship_breakdown(rows, days=28)
    assert out.sponsored.avg_views == 300.0
    assert out.sponsored.avg_likes == 300.0


def test_sponsorship_breakdown_empty_input():
    out = _aggregate_sponsorship_breakdown([], days=90)
    assert out.organic.post_count == 0
    assert out.organic.avg_views is None
    assert out.sponsored.post_count == 0
    assert out.sponsored.avg_views is None
    for f in out.formats:
        assert f.organic.post_count == 0
        assert f.sponsored.post_count == 0


def _fr(format="long_form", views=None, likes=None, comments=None):
    return _FormatRow(format=format, views=views, likes=likes, comments=comments)


def test_format_breakdown_engagement_rate_is_mean_of_per_post_rates():
    # Post A: (100+10)/1000 = 0.11; Post B: (300+30)/3000 = 0.11 -- same
    # rate despite very different scale, so the average should be exactly
    # 0.11, not skewed toward the larger post the way a
    # sum(likes+comments)/sum(views) aggregate would be.
    rows = [
        _fr(views=1000, likes=100, comments=10),
        _fr(views=3000, likes=300, comments=30),
    ]
    out = _aggregate_format_breakdown(rows, days=28)
    long_form = next(f for f in out.formats if f.format == "long_form")
    assert long_form.avg_engagement_rate == 0.11


def test_format_breakdown_engagement_rate_not_dominated_by_viral_post():
    # A viral outlier (views=1,000,000, low relative engagement) shouldn't
    # drag a bucket of otherwise-consistent posts' average down toward its
    # own ratio -- confirms this is an average of per-post rates, not
    # total_likes+total_comments/total_views.
    rows = [
        _fr(views=1000, likes=200, comments=20),  # rate 0.22
        _fr(views=1000, likes=200, comments=20),  # rate 0.22
        _fr(views=1_000_000, likes=1000, comments=0),  # rate 0.001
    ]
    out = _aggregate_format_breakdown(rows, days=28)
    long_form = next(f for f in out.formats if f.format == "long_form")
    # Aggregate ratio would be ~0.0024; average-of-rates should sit much
    # closer to the two consistent posts' 0.22.
    assert long_form.avg_engagement_rate > 0.1


def test_format_breakdown_engagement_rate_falls_back_to_likes_when_views_unavailable():
    rows = [_fr(views=0, likes=100, comments=10)]
    out = _aggregate_format_breakdown(rows, days=28)
    long_form = next(f for f in out.formats if f.format == "long_form")
    assert long_form.avg_engagement_rate == round(110 / 100, 4)


def test_format_breakdown_engagement_rate_none_without_usable_data():
    rows = [_fr(views=0, likes=0, comments=0)]
    out = _aggregate_format_breakdown(rows, days=28)
    long_form = next(f for f in out.formats if f.format == "long_form")
    assert long_form.avg_engagement_rate is None


def test_format_breakdown_engagement_rate_crossed_with_format():
    rows = [
        _fr(format="long_form", views=1000, likes=100, comments=0),
        _fr(format="short_form", views=1000, likes=500, comments=0),
    ]
    out = _aggregate_format_breakdown(rows, days=28)
    by_format = {f.format: f for f in out.formats}
    assert by_format["long_form"].avg_engagement_rate == 0.1
    assert by_format["short_form"].avg_engagement_rate == 0.5


def test_format_breakdown_empty_input():
    out = _aggregate_format_breakdown([], days=28)
    for f in out.formats:
        assert f.post_count == 0
        assert f.avg_views is None
        assert f.avg_engagement_rate is None


def _isr(post_id, day: str, views=None, likes=None):
    return _InstagramMetricSnapshotRow(
        post_id=post_id, scraped_at=date.fromisoformat(day), views=views, likes=likes
    )


def test_reconstruct_daily_views_forward_fills_and_sums_across_posts():
    post_a, post_b = uuid4(), uuid4()
    rows = [
        _isr(post_a, "2026-01-01", views=1000),
        _isr(post_b, "2026-01-01", views=500),
        _isr(post_b, "2026-01-02", views=600),
        # post_a has no 2026-01-02 snapshot -- must forward-fill its 1000.
        _isr(post_a, "2026-01-03", views=1100),
        _isr(post_b, "2026-01-03", views=700),
    ]
    points = _reconstruct_daily_views_series({}, rows)
    by_date = {p.date.isoformat(): p for p in points}
    assert by_date["2026-01-01"].value == 1500  # 1000 + 500
    assert by_date["2026-01-02"].value == 1600  # 1000 (forward-filled) + 600
    assert by_date["2026-01-03"].value == 1800  # 1100 + 700
    assert by_date["2026-01-01"].daily_delta is None  # first point, no prior day
    assert by_date["2026-01-02"].daily_delta == 100
    assert by_date["2026-01-03"].daily_delta == 200


def test_reconstruct_daily_views_uses_baseline_for_preexisting_post():
    post_a = uuid4()
    baseline = {post_a: 5000}  # last known value from before the window
    rows = [_isr(post_a, "2026-01-01", views=5200)]
    points = _reconstruct_daily_views_series(baseline, rows)
    assert points[0].value == 5200
    # No daily_delta on the very first emitted point regardless of baseline
    # (there's no prior *point* to diff against, even though there's a
    # prior *value*) -- matches every other series' "first point has no
    # delta" convention.
    assert points[0].daily_delta is None


def test_reconstruct_daily_views_new_post_jumps_from_full_value():
    post_a = uuid4()
    # No baseline entry at all -- post_a is brand new inside the window.
    rows = [_isr(post_a, "2026-01-01", views=100), _isr(post_a, "2026-01-02", views=250)]
    points = _reconstruct_daily_views_series({}, rows)
    assert points[0].value == 100
    assert points[1].value == 250
    assert points[1].daily_delta == 150


def test_reconstruct_daily_views_falls_back_to_likes_when_views_unavailable():
    post_a = uuid4()
    rows = [_isr(post_a, "2026-01-01", views=0, likes=42)]
    points = _reconstruct_daily_views_series({}, rows)
    assert points[0].value == 42


def test_reconstruct_daily_views_empty_input():
    assert _reconstruct_daily_views_series({}, []) == []
    assert _strip_phantom_zero_lead([_gp("2026-01-01", 0)]) == [_gp("2026-01-01", 0)]


def test_reconstruct_daily_views_spreads_delta_across_gap_days():
    """Regression test: Instagram scraping is opportunistic, not
    guaranteed-daily -- a 4-day gap in snapshots previously vanished
    entirely (no points emitted for days 2-4) and dumped the whole 4-day
    delta onto day 5's single point, which _get_earnings_series then
    reported as a single day's earnings spike with $0 on the skipped
    days. Points must now be emitted for every calendar day in the
    window, with the total delta spread evenly across the gap."""
    post_a = uuid4()
    rows = [
        _isr(post_a, "2026-01-01", views=100_000),
        # gap: 2026-01-02, 03, 04 have no snapshot at all
        _isr(post_a, "2026-01-05", views=140_000),
    ]
    points = _reconstruct_daily_views_series({}, rows)
    by_date = {p.date.isoformat(): p for p in points}

    # One point per calendar day, not just the two days with real data.
    assert sorted(by_date) == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]

    # 40,000 views over 4 days = 10,000/day, spread evenly rather than a
    # single 40,000 spike on 01-05 with 0 on the days in between.
    assert by_date["2026-01-01"].daily_delta is None
    assert by_date["2026-01-02"].daily_delta == 10_000
    assert by_date["2026-01-03"].daily_delta == 10_000
    assert by_date["2026-01-04"].daily_delta == 10_000
    assert by_date["2026-01-05"].daily_delta == 10_000

    # Interpolated cumulative totals in between, exact endpoints preserved.
    assert by_date["2026-01-01"].value == 100_000
    assert by_date["2026-01-02"].value == 110_000
    assert by_date["2026-01-03"].value == 120_000
    assert by_date["2026-01-04"].value == 130_000
    assert by_date["2026-01-05"].value == 140_000

    # Deltas sum exactly to the real total delta across the gap -- no
    # rounding drift lost or double-counted.
    assert sum(p.daily_delta for p in points if p.daily_delta is not None) == 40_000


def test_interpolate_daily_gaps_single_point_has_no_delta():
    points = _interpolate_daily_gaps([date(2026, 1, 1)], [500])
    assert len(points) == 1
    assert points[0].value == 500
    assert points[0].daily_delta is None


def test_interpolate_daily_gaps_empty_input():
    assert _interpolate_daily_gaps([], []) == []


def test_interpolate_daily_gaps_dense_series_is_unchanged():
    dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
    values = [100, 150, 260]
    points = _interpolate_daily_gaps(dates, values)
    assert [p.value for p in points] == [100, 150, 260]
    assert [p.daily_delta for p in points] == [None, 50, 110]


def test_interpolate_daily_gaps_uneven_gap_rounds_without_losing_total():
    # 3-day gap, delta not evenly divisible by 3 -- rounding must not
    # cause the reconstructed deltas to over/undercount the real total.
    dates = [date(2026, 1, 1), date(2026, 1, 4)]
    values = [1000, 1010]  # +10 over 3 days = 3.33/day
    points = _interpolate_daily_gaps(dates, values)
    assert len(points) == 4
    deltas = [p.daily_delta for p in points if p.daily_delta is not None]
    assert sum(deltas) == 10
    assert points[-1].value == 1010
