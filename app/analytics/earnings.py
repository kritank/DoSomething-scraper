"""Estimated-earnings heuristics for the creator-stats profile page.

These are rough, industry-rule-of-thumb estimates (the same kind vidiq/
Social Blade show), not real revenue figures -- callers must always render
them as a range with an "estimate" disclaimer, never a single number. See
docs/CREATOR_STATS_PLAN.md Phase 2.
"""

from __future__ import annotations

from app.schemas.creator_stats import EarningsEstimate

# YouTube: (low, high) USD RPM (revenue per 1000 views) by channel country.
# Rough 2025-era AdSense benchmarks -- India/APAC music/entertainment
# content sits well below US/EU CPMs. "_default" covers unmapped/unknown
# countries with a conservative global-blend range.
_YOUTUBE_RPM_BY_COUNTRY: dict[str, tuple[float, float]] = {
    "US": (2.0, 7.0),
    "GB": (1.5, 5.0),
    "CA": (1.5, 5.0),
    "AU": (1.5, 5.0),
    "IN": (0.30, 2.0),
    "_default": (0.5, 3.0),
}

# Instagram: (low, high) USD per 1,000 followers for a single sponsored
# post, before the engagement-rate adjustment below.
_INSTAGRAM_BASE_RATE_PER_1K_FOLLOWERS: tuple[float, float] = (5.0, 15.0)

# Engagement rate treated as "neutral" (multiplier = 1.0) when estimating
# sponsored-post price -- roughly the typical ER for a mid-size account.
_INSTAGRAM_NEUTRAL_ER = 0.02
_INSTAGRAM_ER_MULTIPLIER_MIN = 0.5
_INSTAGRAM_ER_MULTIPLIER_MAX = 3.0


def youtube_rpm_range(country: str | None) -> tuple[float, float]:
    """(low, high) USD RPM for a channel's country -- exposed separately
    from estimate_youtube_earnings so the growth chart's daily earnings
    band (app.analytics.creator_stats.get_growth_series) can apply the
    same per-day RPM without going through the 28d-views-only estimator."""
    return _YOUTUBE_RPM_BY_COUNTRY.get((country or "").upper(), _YOUTUBE_RPM_BY_COUNTRY["_default"])


def estimate_youtube_earnings(views_28d: int | None, country: str | None) -> EarningsEstimate | None:
    """Monthly ad-revenue estimate from trailing-28-day views. None if we
    don't have enough view history yet (see CreatorStatsService.get_summary)."""
    if views_28d is None or views_28d <= 0:
        return None
    low_rpm, high_rpm = youtube_rpm_range(country)
    return EarningsEstimate(
        low_usd=round(views_28d / 1000 * low_rpm, 2),
        high_usd=round(views_28d / 1000 * high_rpm, 2),
        basis="monthly_ad_revenue",
    )


def estimate_instagram_earnings(
    followers: int, engagement_rate: float | None, subscribers_hidden: bool
) -> EarningsEstimate | None:
    """Estimated price for a single sponsored post. None when followers are
    hidden -- there's no honest base to estimate from."""
    if subscribers_hidden or followers <= 0:
        return None

    er_multiplier = 1.0
    if engagement_rate is not None and engagement_rate > 0:
        er_multiplier = max(
            _INSTAGRAM_ER_MULTIPLIER_MIN,
            min(_INSTAGRAM_ER_MULTIPLIER_MAX, engagement_rate / _INSTAGRAM_NEUTRAL_ER),
        )

    low_rate, high_rate = _INSTAGRAM_BASE_RATE_PER_1K_FOLLOWERS
    followers_k = followers / 1000
    return EarningsEstimate(
        low_usd=round(followers_k * low_rate * er_multiplier, 2),
        high_usd=round(followers_k * high_rate * er_multiplier, 2),
        basis="per_sponsored_post",
    )
