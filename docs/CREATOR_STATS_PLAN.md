# Creator Stats — vidiq-style analytics for tracked channels/accounts

Goal: for every tracked influencer (YouTube channel or Instagram account), show a
vidiq-style stats profile (reference: https://vidiq.com/youtube-stats/channel/@desimusicfactoryyt/):
headline counts, 7/28-day growth, engagement rate, estimated earnings, per-video/post
performance (outlier score, velocity), and rank within our tracked universe.

**Key insight: no scraper changes are needed.** Every metric below is derived from
data the scrapers already write daily — `profile_snapshots` (followers/subs, total
views, post count per day) and `post_metrics_snapshots` (likes/comments/views per
post per day). This is analytics + API + UI work only. The single deferred exception
is true hourly views-per-hour (Phase 5, optional).

Read `docs/YOUTUBE_SCRAPER_DESIGN.md` first for existing conventions (NULL-vs-0
semantics, platform column, snapshot cadence).

---

## Data foundation (already exists — do not modify)

- `ProfileSnapshot` (`app/models/snapshot.py`): one row per influencer per day.
  `followers` (= YT subscribers), `posts`, `total_views` (YT only, NULL for IG),
  `subscribers_hidden`, `platform_metadata` (JSONB: YT country, publishedAt, topics).
- `PostMetricsSnapshot` (`app/models/snapshot.py:93`): one row per post per day.
  `likes`/`comments`/`views` are **NULL when the platform hides them** (hidden likes,
  disabled comments, media with no view metric). Never coalesce NULL to 0 in averages —
  exclude those posts from the aggregate instead.
- `Post` (`app/models/post.py`): `posted_at`, `influencer_id`, `title`, `permalink`,
  `product_type`, `platform_metadata`.
- `Influencer` (`app/models/influencer.py`): `platform` ("instagram" | "youtube"),
  `category_id`, `handle`.
- `AnalyticsCache` (`app/models/analytics_cache.py`): existing generic cache table —
  inspect it and reuse for expensive computations (rankings) instead of adding a new table.

### Known data caveats (encode these in code comments and UI copy)

1. YouTube `subscriberCount` is rounded by the API to 3 significant figures →
   sub deltas on big channels move in coarse steps (e.g. −100K). Instagram follower
   counts are exact. Don't "fix" this; just render honestly.
2. Growth windows need history: an influencer tracked for < N days can't show an
   N-day delta. Return the partial window with an `actual_window_days` field rather
   than erroring or extrapolating.
3. `ProfileSnapshot.scraped_at` is a `Date` — at most one point per day. All deltas
   are day-granularity.
4. If `subscribers_hidden` is true, suppress subscriber-derived metrics (growth,
   ER denominator) rather than showing 0.

---

## Phase 1 — Backend: growth & summary stats service

### New file `app/analytics/creator_stats.py`

`class CreatorStatsService` taking an `AsyncSession` (mirror `CategoryAggregator`'s
constructor pattern in `app/benchmark/category_aggregator.py`).

Methods:

1. `async def get_summary(influencer_id) -> CreatorSummary`
   - Latest `ProfileSnapshot` row → current followers/subs, total_views, post count.
   - From `Influencer` + `platform_metadata` → platform, handle, country,
     channel/account age (YT `publishedAt`).
   - Growth deltas for 7 and 28 days: `latest.followers - snapshot_at(latest.scraped_at - N days).followers`
     (use the closest snapshot ≤ target date; report `actual_window_days`).
   - **Views in window**:
     - YouTube: delta of `ProfileSnapshot.total_views` over the window (channel-level counter).
     - Instagram (`total_views` is NULL): sum per-post view deltas over the window from
       `PostMetricsSnapshot` joined to `Post` on `influencer_id`
       (`latest_in_window − earliest_in_window` per post, plus full latest value for posts
       created inside the window). Fall back to likes when `views` is NULL for a post type.
   - Posting frequency: posts with `posted_at` in last 28 days ÷ 4 → per-week rate.

2. `async def get_growth_series(influencer_id, days, metric) -> list[GrowthPoint]`
   - `metric ∈ {followers, total_views, posts}`; returns `(date, value, daily_delta)`
     straight from `profile_snapshots` ordered by `scraped_at`, window-capped.
     Use a SQL `lag()` window function, not Python loops.

3. `async def get_engagement_rate(influencer_id, last_n_posts=12) -> EngagementOut`
   - Last N posts by `posted_at`; for each take its **latest** `PostMetricsSnapshot`.
   - `ER = avg(likes + comments) / current followers` (skip posts with NULL likes;
     report `sample_size`). Return NULL if followers hidden/zero.

### SQL performance

Check existing indexes in `alembic/versions/`. If missing, add one Alembic migration:
- `ix_profile_snapshots_influencer_scraped (influencer_id, scraped_at)`
- `ix_post_metrics_snapshots_post_scraped (post_id, scraped_at)`
- `ix_posts_influencer_posted (influencer_id, posted_at)`

This is the only migration in Phases 1–4.

### Schemas

New `app/schemas/creator_stats.py` with Pydantic models: `CreatorSummary`,
`GrowthPoint`, `EngagementOut`, plus Phase 2/3 models below. Follow conventions of
existing `app/schemas/` files. Every derived metric that can be unavailable is
`Optional` with `None` meaning "not computable", never 0.

---

## Phase 2 — Backend: per-post performance & earnings

### Extend `app/analytics/creator_stats.py`

4. `async def get_post_performance(influencer_id, limit=20) -> list[PostPerformance]`
   For each of the last `limit` posts:
   - Latest snapshot metrics (views/likes/comments, NULL-safe).
   - **Outlier score** (vidiq's "2x / 100x" badge): `post_views / rolling_median_views`
     where the median is over the channel's previous ~30 posts *excluding this post*
     (fall back to likes for IG posts without views). NULL if fewer than 5 prior posts.
   - **Velocity (VPH proxy)**: only for fresh posts — YT: `posted_at` within 7 days,
     IG: within 48h — `latest views (or likes) ÷ hours since posted_at`. NULL otherwise.
     Label it `velocity_per_hour` and note in the schema docstring it's a
     lifetime-average proxy, not a true instantaneous VPH (that's Phase 5).

### New file `app/analytics/earnings.py`

Config-driven estimator returning a **range** `(low_usd, high_usd)`, never a single number:
- YouTube: `views_28d × RPM_range / 1000`. RPM table as a module-level dict keyed by
  country code with a default, e.g. `{"IN": (0.30, 2.0), "US": (2.0, 7.0), "_default": (0.5, 3.0)}`.
- Instagram: estimated sponsored-post price: `followers / 1000 × base_rate ×
  er_multiplier`, base_rate ≈ (5, 15) USD per 1K followers, `er_multiplier =
  clamp(ER / 0.02, 0.5, 3.0)` (2% ER = neutral).
- Constants live in `app/analytics/earnings.py` with sources in comments; no settings/env
  plumbing needed. Return `None` when inputs are missing (no views history, hidden subs).

### Phase 2 tests

`tests/analytics/test_creator_stats.py`, `tests/analytics/test_earnings.py` — follow the
existing test setup in `tests/` (fixtures, async session). Cover: partial windows,
NULL likes exclusion, hidden subscribers, outlier with <5 posts, IG vs YT views paths.

---

## Phase 3 — Backend: rankings + API endpoints

### Rankings (in `creator_stats.py`)

5. `async def get_rankings(influencer_id) -> RankingsOut`
   Rank among **our tracked influencers** (be explicit in naming/UI — this is not a
   global vidiq-style rank): same `platform`, ranked by current followers and by
   28-day view growth; overall and within the influencer's `category_id`. Tracked set
   is small → compute with one window-function query per request; if it measurably slows,
   cache in `AnalyticsCache` with a 1-hour TTL (follow that model's existing usage).

### New router `app/api/v1/creator_stats.py`

Mount under the existing v1 registration (see how `influencers.py`/`benchmarks.py`
routers are included; same auth dependency as `app/api/v1/influencers.py`):

- `GET /api/v1/influencers/{influencer_id}/stats` → `CreatorStatsOut`
  (composite: summary + engagement + earnings + rankings — the profile page's single fetch).
- `GET /api/v1/influencers/{influencer_id}/growth?days=90&metric=followers` → series.
- `GET /api/v1/influencers/{influencer_id}/posts/performance?limit=20` → list.

404 if influencer doesn't exist; 200 with `None` fields if it exists but has no
snapshots yet (UI shows "collecting data…").

---

## Phase 4 — Dashboard UI (dashboard/, React 19 + Vite + Tailwind v4 + recharts v3 + zustand)

### New service `dashboard/src/services/creatorStatsService.js`

Mirror `influencerService.js` style: `getCreatorStats(id)`, `getGrowthSeries(id, days, metric)`,
`getPostPerformance(id, limit)` via the shared `apiClient`.

### New page `dashboard/src/pages/CreatorProfile.jsx`, route `influencers/:influencerId`

Add `<Route path="influencers/:influencerId" element={<CreatorProfile />} />` in
`dashboard/src/App.jsx`; make rows in `dashboard/src/pages/Influencers.jsx` link to it.
Reuse `PlatformBadge`, `Skeleton`, `EmptyState`, `Card`-style patterns from
`components/common/`, and platform-aware labels via `utils/platform.js`
("Subscribers" vs "Followers").

Layout (top → bottom):
1. **Header**: handle, platform badge, category, country, account age.
2. **Stat tile row**: followers/subs (with 28d delta chip, green/red), total views
   (YT) or 28d views (IG), post/video count, engagement rate, posting frequency.
   Deltas show "—" (not 0) when window history is insufficient.
3. **Growth chart**: recharts line/area chart of the growth series; metric toggle
   (followers | views) and range toggle (30/90/365d). Follow structure of existing
   `components/charts/PerformanceChart.jsx`. New file
   `components/charts/GrowthChart.jsx`.
4. **Earnings card**: range ("$X – $Y est. monthly" for YT, "per sponsored post" for
   IG) with an explicit "estimate" disclaimer line.
5. **Rankings card**: "#3 of 47 tracked YouTube channels" + "#1 in <category>".
   Always say "tracked" — never imply a global rank.
6. **Recent posts table**: thumbnail/title (permalink link), posted date, views,
   likes, comments, outlier badge ("3.2×", highlighted when ≥ 2×), velocity/hr for
   fresh posts. Reuse table patterns from `pages/Content.jsx`.

Number formatting: compact ("34.1M", "11.5B") — add `dashboard/src/utils/format.js`
if no helper exists yet.

Loading/empty states: skeleton tiles while fetching; if `stats` fields are null
(no snapshots yet), show `EmptyState` with "Data is being collected — check back after
the first scrape completes."

---

## Phase 5 (optional, separate PR — do NOT build unless asked) — true hourly VPH for YouTube

Only if the Phase 2 velocity proxy proves insufficient:
- New table `post_metrics_hourly` (post_id FK, `scraped_at: DateTime`, views) via Alembic.
- New scheduler job in `app/scheduler/runner.py` (pattern: existing
  `snapshot_credential_health`) enqueuing an hourly "hot videos" job per YouTube
  influencer: batch recent (≤7 days) video IDs through `YouTubeClient.get_videos`
  (1 quota unit per 50 videos — negligible).
- VPH = delta between consecutive hourly rows.
- **Explicitly out of scope for Instagram** — hourly scraping multiplies block risk
  on the credential pool.

---

## Implementation order & verification

Build Phases 1→4 in order; each phase should land compiling + tested before the next.

1. Phase 1 + migration → verify: `pytest tests/analytics/` green; hit
   `/stats`-precursor queries against a dev DB with real snapshot rows.
2. Phase 2 → unit tests green, including NULL-metric edge cases.
3. Phase 3 → `curl` all three endpoints for one YT and one IG influencer; confirm
   404/empty behavior.
4. Phase 4 → `npm run dev` in `dashboard/`, open an influencer with ≥28 days of
   snapshots and one added yesterday; verify tiles, chart toggles, empty states, and
   that Instagram and YouTube profiles both render with correct labels.

Non-goals: global (off-platform) rankings, competitor discovery, keyword/SEO tools,
historical backfill of snapshots (history accrues from daily scrapes going forward).
