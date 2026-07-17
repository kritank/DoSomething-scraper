from __future__ import annotations

from app.analytics.earnings import estimate_instagram_earnings, estimate_youtube_earnings


def test_youtube_earnings_none_without_view_history():
    assert estimate_youtube_earnings(None, "US") is None
    assert estimate_youtube_earnings(0, "US") is None


def test_youtube_earnings_uses_country_rpm_and_returns_range():
    estimate = estimate_youtube_earnings(1_000_000, "IN")
    assert estimate is not None
    assert estimate.basis == "monthly_ad_revenue"
    assert estimate.low_usd < estimate.high_usd
    assert estimate.low_usd == round(1_000_000 / 1000 * 0.30, 2)
    assert estimate.high_usd == round(1_000_000 / 1000 * 2.0, 2)


def test_youtube_earnings_falls_back_to_default_rpm_for_unmapped_country():
    mapped = estimate_youtube_earnings(1_000_000, "IN")
    unmapped = estimate_youtube_earnings(1_000_000, "ZZ")
    none_country = estimate_youtube_earnings(1_000_000, None)
    assert unmapped.low_usd != mapped.low_usd
    assert unmapped.low_usd == none_country.low_usd


def test_instagram_earnings_none_when_subscribers_hidden():
    assert estimate_instagram_earnings(100_000, 0.03, subscribers_hidden=True) is None


def test_instagram_earnings_none_for_zero_followers():
    assert estimate_instagram_earnings(0, 0.03, subscribers_hidden=False) is None


def test_instagram_earnings_higher_engagement_raises_estimate():
    low_er = estimate_instagram_earnings(100_000, 0.005, subscribers_hidden=False)
    high_er = estimate_instagram_earnings(100_000, 0.08, subscribers_hidden=False)
    assert low_er.high_usd < high_er.high_usd
    assert low_er.basis == "per_sponsored_post"


def test_instagram_earnings_multiplier_is_clamped():
    extreme_high = estimate_instagram_earnings(100_000, 10.0, subscribers_hidden=False)
    extreme_low = estimate_instagram_earnings(100_000, 0.0001, subscribers_hidden=False)
    capped_high = estimate_instagram_earnings(100_000, 0.06, subscribers_hidden=False)  # 3x multiplier
    floor_low = estimate_instagram_earnings(100_000, 0.01, subscribers_hidden=False)  # 0.5x multiplier
    assert extreme_high.high_usd == capped_high.high_usd
    assert extreme_low.high_usd == floor_low.high_usd


def test_instagram_earnings_defaults_to_neutral_multiplier_when_er_missing():
    estimate = estimate_instagram_earnings(100_000, None, subscribers_hidden=False)
    assert estimate is not None
    assert estimate.low_usd == round(100 * 5.0, 2)
    assert estimate.high_usd == round(100 * 15.0, 2)
