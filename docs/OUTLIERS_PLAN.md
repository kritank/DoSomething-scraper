# Outliers v2 — vidIQ-parity outlier detection & cross-creator discovery

Reference: https://vidiq.com/features/outliers/ — vidIQ defines an Outlier as "a
video performing significantly better than a channel's usual average — more
views, higher velocity, and stronger audience engagement," surfaces them in a
**cross-channel discovery feed**, and scores them with a composite **Outlier
Score** ("views, velocity, and performance vs. a channel's usual baseline"),
plus **Views Per Hour (VPH)** for real-time momentum. Their filters: channel
size, publish date, video length, Video/Shorts toggle, sort by Outlier Score
or VPH, keyword (and thumbnail) search.

## What we already have (v1, shipped in creator stats)

`app/analytics/creator_stats.py`:

- **Outlier multiplier** — `outlier_metric / median(prior posts)` over a
  30-post rolling lookback (`OUTLIER_LOOKBACK_POSTS`), minimum 5 prior posts
  (`MIN_POSTS_FOR_OUTLIER`). `outlier_metric` = views, falling back to likes
  for Instagram photo posts (views==0 ≡ NULL rule). This *is* vidIQ's
  "performance multiplier vs channel baseline."
- **Velocity/hour** — lifetime-average views÷age, but only while a post is
  "fresh" (7d YouTube / 48h Instagram).
- **Format filter + top sort** — `GET /influencers/{id}/posts/performance?
  format=&sort=top`, ≥2× badge in `PostsTable.jsx`, `top_post` key events.

All computed **on the fly, for one creator at a time**, and only visible
inside that creator's profile page.

## Gap analysis vs vidIQ

| vidIQ capability | Us | Gap |
|---|---|---|
| Multiplier vs channel baseline | ✅ rolling-median multiplier | none |
| Video/Shorts toggle | ✅ `content_format` filter | none |
| **Cross-channel discovery feed** | ❌ per-creator only | **the headline gap** |
| **True VPH (current momentum)** | ⚠️ lifetime avg, fresh posts only | we have daily `PostMetricsSnapshot` rows — can compute real deltas, at any age |
| **Composite Outlier Score** | ❌ multiplier only | blend multiplier + velocity + engagement |
| Channel-size filter | ❌ | data exists (`ProfileSnapshot.followers`) |
| Publish-date filter | ❌ | data exists (`posts.posted_at`, indexed) |
| Video-length filter | ❌ | data exists (YT `platform_metadata.duration_s`, IG `feature_store.reel_duration_s`) |
| Keyword search | ❌ | data exists (`posts.title`, `posts.caption`, `hashtags`) |
| Thumbnail/visual search | ❌ | out of scope (needs embeddings; Phase 5 note only) |

**No scraper changes are needed.** Everything below derives from data already
being collected. One migration (Phase 1).

Conventions to preserve (from v1): NULL = "not computable", never fabricated 0;
views==0 on Instagram ≡ NULL; copy always says "tracked creators", never
implies a global/all-of-YouTube rank (unlike vidIQ we only see our own
universe — the UI must say so).

---

## Phase 1 — Persist per-post outlier metrics

On-the-fly scoring is fine for one creator; a cross-creator feed filtered and
sorted by score cannot recompute rolling medians over every tracked account
per request. Persist scores once, query them cheaply.

### 1a. Migration: `post_outlier_metrics` table

One row per post (upserted), not per-day — history stays in
`post_metrics_snapshots`:

```
post_id            UUID PK/FK posts(id) ON DELETE CASCADE
outlier_score      FLOAT NULL      -- composite (Phase 2); starts = multiplier
baseline_multiple  FLOAT NULL      -- v1 multiplier, kept as its own column
vph_current        FLOAT NULL      -- true VPH from latest snapshot delta
vph_lifetime       FLOAT NULL      -- metric / hours-since-posted
engagement_ratio   FLOAT NULL      -- post ER vs channel's rolling median ER
baseline_median    FLOAT NULL      -- denominator, for explainability tooltips
computed_at        TIMESTAMPTZ NOT NULL
```

Partial index for the feed: `(outlier_score DESC) WHERE outlier_score IS NOT
NULL`, plus the filter columns live on joins (`posts.posted_at`,
`influencers.platform`).

Why a new table and not `feature_store`: feature_store rows are written at
extraction time and are static per post; outlier metrics are re-written every
snapshot cycle and are NULL-heavy early in a post's life. Different write
cadence → different table.

### 1b. Compute job

- Extract v1's scoring into pure functions (they already are:
  `_compute_outlier_and_velocity`) and share them between the profile
  endpoint and the batch job — one formula, two consumers.
- Hook: after each successful profile scrape (where we already write
  `PostMetricsSnapshot` rows in `JobProcessor._record_metrics_snapshot`),
  recompute that influencer's recent posts (last `OUTLIER_LOOKBACK_POSTS` +
  new ones) and upsert. Piggybacking on the scrape cycle means scores are
  exactly as fresh as the data, with no separate scheduler entry.
- Backfill script `scripts/backfill_outlier_metrics.py` (same shape as
  `scripts/backfill_profile_pics.py`) to populate history once.
- `get_post_performance` keeps computing live (it needs per-request `now` for
  velocity) — no behavior change for the profile page in this phase.

## Phase 2 — Better signals: true VPH + composite score

### 2a. True VPH from snapshot deltas

`vph_current = (latest.views − previous.views) / hours between the two
snapshots`, using the two most recent `PostMetricsSnapshot` rows (dedup
same-day by `created_at DESC`, as v1 does). Falls back to likes-delta on
Instagram under the same views==0 rule. Only one snapshot yet → fall back to
`vph_lifetime`. Negative deltas (platform corrections) → NULL, not negative.

This removes the "fresh window" restriction: a 2-year-old video suddenly
picking up 5k views/hour is precisely the outlier vidIQ's VPH catches and our
lifetime average hides.

### 2b. Engagement ratio

`post ER = (likes + comments) / outlier_metric`; channel baseline ER = rolling
median over the same 30-post lookback. `engagement_ratio = post ER / baseline
ER`. NULL when either side lacks data (YouTube hidden likes, etc.).

### 2c. Composite Outlier Score — implemented

Mirrors vidIQ's "views, velocity, and performance vs. baseline":

```
velocity_ratio = vph_current / vph_lifetime   # this post's own average pace, NULL-safe
outlier_score  = baseline_multiple
                 × (1 + 0.5·log2(velocity_ratio))   # only when velocity_ratio > 1
                 × clamp(engagement_ratio, 0.75, 1.25)  # mild engagement nudge
```

Velocity is self-relative (a post's current pace vs. its *own* lifetime
average) rather than vph_current-vs-cross-post-median: always defined once
both vph figures exist, avoids a second full-lookback pass just to build a
fresh-post velocity distribution, and still captures "this is accelerating."
`_compute_composite_outlier_score` in `app/analytics/creator_stats.py`.
Properties verified by `tests/unit/test_creator_stats_scoring.py`: (1)
reduces to `baseline_multiple` when velocity/engagement are NULL, so
Instagram photo posts and single-snapshot posts still score; (2) only
*accelerating* posts (velocity_ratio > 1) get boosted, decelerating ones are
left alone; (3) engagement is clamped to [0.75, 1.25] so it nudges rather
than dominates.

Keep exposing `baseline_multiple` separately — the "3.2×" framing is the
explainable number; the composite drives ranking.

## Phase 3 — Cross-creator discovery: extend the existing Content page

**No new page or router.** `dashboard/src/pages/Content.jsx` (backed by
`GET /admin/posts` → `PostRepo.list_posts`, `app/api/v1/admin.py:382`) is
already a cross-creator post browser with influencer/category/platform
filters, sort, and pagination — the exact shell vidIQ's discovery feed needs.
A parallel `/outliers` page + endpoint would duplicate it. Extend instead:

`PostRepo.list_posts` (`app/repositories/post_repo.py`):
- LEFT JOIN `post_outlier_metrics` (Phase 1) on `post_id`.
- New optional filters: `min_score` (default off — existing ≥2× badge
  threshold as the UI's quick-filter value), `duration_min_s` /
  `duration_max_s` (YT `platform_metadata.duration_s`, IG
  `feature_store.reel_duration_s`), `followers_min` / `followers_max` (join
  latest `ProfileSnapshot`).
- New `sort` values: `outlier_score`, `vph` (alongside existing
  `posted_at` etc.).
- `PostOut`/`PostListOut` schemas gain `outlier_score`, `baseline_multiple`,
  `vph_current` (additive, NULLable — existing consumers unaffected).

`Content.jsx` UI additions:
- Outlier score badge column, reusing `PostsTable.jsx`'s ≥2× green-badge
  styling and `infoTip` tooltip pattern.
- Min-score quick filter (e.g. a "2×+" toggle) and `outlier_score`/`vph`
  entries in the existing sort dropdown.
- Duration and follower-count range filters alongside the existing
  influencer/category/platform selectors.
- Small copy note near the filter bar: scores compare each post to **its own
  channel's** baseline, within **tracked creators only** — never a
  platform-wide rank.

Profile-page `PostsTable` swaps to the persisted columns once Phase 2 lands
(columns already exist there; just change the data source from live
computation to the table).

## Phase 5 — Later / explicitly out of scope now

- **Thumbnail similarity search** — needs image embeddings + pgvector;
  revisit only if there's real demand.
- **Niche-relative scoring** (outlier vs category baseline, not just own
  channel) — `app/benchmark/category_aggregator.py` already aggregates by
  category; a `score vs category median` variant slots into the same table
  as one more column.
- **Alerts** — "creator X just posted a 5× outlier" notification hook on the
  Phase 1b compute job.

## Test plan

- Unit: composite-score pure function (NULL fallbacks, monotonicity,
  Instagram likes path), VPH delta (single snapshot, same-day dupes,
  negative delta) — extend `tests/unit/test_creator_stats_scoring.py`.
- Integration: `/outliers` filter combinations against seeded fixtures;
  upsert idempotency of the compute hook.
- Verify parity: profile page `outlier_score` (live) vs persisted
  `baseline_multiple` agree for the same post/date.

## Suggested order

Phase 1 → 2 are backend-only and low-risk. Phase 3 is a single PR (repo
filters/sort + `Content.jsx` UI together — no standalone endpoint with no
consumer). Each phase is a separate PR.
